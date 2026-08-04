"""Tests für catalyst_calendar_sync.py — keine Netzwerk-Abhängigkeit.

Abgedeckt:
- Deterministische Index-Kalenderregeln (DAX / Nasdaq-100 / MSCI), gegengeprüft
  gegen unabhängig recherchierte Termine vom 2026-08-04
- Seeds-YAML-Parsing inkl. Zeitfenster, Confidence-Default und Fehlertoleranz
- Merge/Dedupe mit Confidence-Rang
- Ethik-Filter (Ticker- und Namens-Pfad)
- Aging (passed / imminent / upcoming) und Renderer-Smoke
- Collector-Kapselung: ein kaputter Collector killt den Lauf nicht
"""

import datetime as dt
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import catalyst_calendar_sync as ccs  # noqa: E402


TODAY = dt.date(2026, 8, 4)
HORIZON = dt.date(2027, 3, 2)


# --------------------------------------------------------------------------
# Deterministische Index-Regeln
# --------------------------------------------------------------------------

def test_index_reviews_treffen_recherchierte_termine():
    """Die Kalenderregeln müssen die am 2026-08-04 unabhängig recherchierten
    Termine exakt reproduzieren — sonst ist die Regel falsch, nicht die Quelle."""
    spans = {e.date_str() for e in ccs.collect_index_reviews(TODAY, HORIZON)}
    assert "2026-09-03 -> 2026-09-21" in spans      # DAX September
    assert "2026-12-11 -> 2026-12-21" in spans      # Nasdaq-100 Jahres-Reko
    assert "2026-08-12 -> 2026-09-01" in spans      # MSCI August
    assert "2026-11-11 -> 2026-12-01" in spans      # MSCI November (Semi-Annual)


def test_index_reviews_sind_verified_und_kategorie_4():
    for e in ccs.collect_index_reviews(TODAY, HORIZON):
        assert e.confidence == "verified"
        assert e.kategorie == ccs.KAT_INDEX
        assert e.collector == "index_reviews"


def test_index_reviews_respektiert_horizont():
    eng = ccs.collect_index_reviews(TODAY, dt.date(2026, 9, 30))
    assert eng, "mindestens der September-DAX-Termin muss drin sein"
    assert all(e.date_from <= dt.date(2026, 9, 30) for e in eng)


def test_nth_business_day_ueberspringt_wochenende():
    # 2026-11-01 ist ein Sonntag -> 1. Arbeitstag ist der 02.11.
    assert ccs._nth_business_day(2026, 11, 1) == dt.date(2026, 11, 2)


def test_nth_weekday_zweiter_freitag():
    assert ccs._nth_weekday(2026, 12, 4, 2) == dt.date(2026, 12, 11)


# --------------------------------------------------------------------------
# Seeds
# --------------------------------------------------------------------------

_SEED_YAML = textwrap.dedent("""
    events:
      - date: 2026-11-10
        kat: 1
        titel: "Chinas SE-Exportkontroll-Aussetzung laeuft aus"
        tickers: "MP, LYC.AX"
        wirkung: "+ Nicht-China-Foerderer"
        quelle: "test"
      - date: 2026-08-21
        date_to: 2026-10-25
        kat: 3
        titel: "Lockup-Tranchen"
        tickers: "SPCX"
        confidence: heuristic
      - date: NICHT-EIN-DATUM
        kat: 1
        titel: "kaputt"
    """)


def _write_seeds(tmp_path):
    p = tmp_path / "seeds.yaml"
    p.write_text(_SEED_YAML, encoding="utf-8")
    return str(p)


def test_seeds_parsen_und_kaputte_zeile_ueberspringen(tmp_path):
    ev = ccs.collect_seeds(_write_seeds(tmp_path), TODAY, HORIZON)
    assert len(ev) == 2, "der Eintrag mit unlesbarem Datum darf den Lauf nicht kippen"
    titel = {e.titel for e in ev}
    assert "kaputt" not in titel


def test_seeds_confidence_default_ist_verified(tmp_path):
    ev = {e.titel: e for e in ccs.collect_seeds(_write_seeds(tmp_path), TODAY, HORIZON)}
    assert ev["Chinas SE-Exportkontroll-Aussetzung laeuft aus"].confidence == "verified"
    assert ev["Lockup-Tranchen"].confidence == "heuristic"


def test_seeds_zeitfenster_wird_uebernommen(tmp_path):
    ev = {e.titel: e for e in ccs.collect_seeds(_write_seeds(tmp_path), TODAY, HORIZON)}
    lock = ev["Lockup-Tranchen"]
    assert lock.date_to == dt.date(2026, 10, 25)
    assert lock.date_str() == "2026-08-21 -> 2026-10-25"


def test_seeds_fehlende_datei_ist_kein_fehler(tmp_path):
    assert ccs.collect_seeds(str(tmp_path / "gibtsnicht.yaml"), TODAY, HORIZON) == []


# --------------------------------------------------------------------------
# Merge / Dedupe / Ethik
# --------------------------------------------------------------------------

def _ev(date, titel, conf="verified", kat=1, tickers=None):
    return ccs.CatalystEvent(date_from=date, kategorie=kat, titel=titel,
                             tickers=tickers or [], confidence=conf)


def test_merge_hoehere_confidence_gewinnt():
    a = _ev(dt.date(2026, 11, 10), "SE-Kontrollen laufen aus", "heuristic")
    b = _ev(dt.date(2026, 11, 10), "SE-Kontrollen laufen aus", "verified")
    out = ccs.merge_events([[a], [b]])
    assert len(out) == 1 and out[0].confidence == "verified"


def test_merge_haelt_verschiedene_kategorien_am_selben_tag_auseinander():
    a = _ev(dt.date(2026, 11, 10), "SE-Kontrollen", kat=ccs.KAT_REGULIERUNG)
    b = _ev(dt.date(2026, 11, 10), "Index-Review", kat=ccs.KAT_INDEX)
    assert len(ccs.merge_events([[a, b]])) == 2


def test_merge_sortiert_nach_datum():
    spaet = _ev(dt.date(2027, 1, 1), "spaet")
    frueh = _ev(dt.date(2026, 9, 1), "frueh")
    assert [e.titel for e in ccs.merge_events([[spaet, frueh]])] == ["frueh", "spaet"]


def test_ethik_filter_ticker():
    blocked = _ev(dt.date(2026, 9, 1), "Beschaffungsprogramm", tickers=["RHM.DE"])
    assert ccs.merge_events([[blocked]]) == []


def test_ethik_filter_name_im_titel():
    blocked = _ev(dt.date(2026, 9, 1), "Grossauftrag fuer Lockheed Martin")
    assert ccs.merge_events([[blocked]]) == []


def test_ethik_filter_laesst_normale_werte_durch():
    ok = _ev(dt.date(2026, 9, 1), "Kapazitaetsauktion", tickers=["ENR.DE", "RWE.DE"])
    assert len(ccs.merge_events([[ok]])) == 1


# --------------------------------------------------------------------------
# Aging
# --------------------------------------------------------------------------

def test_status_aging():
    assert _ev(TODAY - dt.timedelta(days=1), "x").status(TODAY) == "passed"
    assert _ev(TODAY + dt.timedelta(days=3), "x").status(TODAY) == "imminent"
    assert _ev(TODAY + dt.timedelta(days=ccs.IMMINENT_DAYS), "x").status(TODAY) == "imminent"
    assert _ev(TODAY + dt.timedelta(days=ccs.IMMINENT_DAYS + 1), "x").status(TODAY) == "upcoming"


def test_days_until_negativ_bei_vergangenheit():
    assert _ev(TODAY - dt.timedelta(days=5), "x").days_until(TODAY) == -5


# --------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------

def test_render_markdown_zeigt_alle_drei_bloecke():
    evs = [
        _ev(TODAY - dt.timedelta(days=2), "abgelaufen"),
        _ev(TODAY + dt.timedelta(days=5), "einrueckend"),
        _ev(TODAY + dt.timedelta(days=90), "horizont"),
    ]
    md = ccs.render_markdown(evs, dt.datetime(2026, 8, 4, 9, 0), {"horizon": "2027-03-02"})
    assert "Einrueckend" in md and "Horizont" in md and "Abgelaufen" in md
    assert "Ein Termin ist keine These" in md, "die Abgrenzung muss im Output stehen"


def test_render_markdown_markiert_nicht_verifizierte():
    md = ccs.render_markdown([_ev(TODAY + dt.timedelta(days=5), "x", "heuristic")],
                             dt.datetime(2026, 8, 4, 9, 0), {})
    assert "[HEURISTIC]" in md


def test_render_json_schema_und_counts():
    import json
    evs = [_ev(TODAY + dt.timedelta(days=5), "a"), _ev(TODAY + dt.timedelta(days=90), "b")]
    d = json.loads(ccs.render_json(evs, dt.datetime(2026, 8, 4, 9, 0), {"horizon": "2027-03-02"}))
    assert d["schema"] == "catalyst-calendar/v1"
    assert d["counts"] == {"total": 2, "imminent": 1, "upcoming": 1, "passed": 0}
    assert d["events"][0]["kat_label"] == "Regulierung/Frist"


# --------------------------------------------------------------------------
# Kapselung
# --------------------------------------------------------------------------

def test_kaputter_collector_killt_den_lauf_nicht(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise RuntimeError("Endpoint tot")
    monkeypatch.setattr(ccs, "collect_index_reviews", boom)
    events, stats = ccs.run_collect(210, _write_seeds(tmp_path), offline=True)
    assert "FEHLER" in str(stats["collectors"]["index_reviews"])
    assert len(events) == 2, "die Seeds muessen trotzdem durchkommen"


def test_offline_ueberspringt_netz_collectoren(tmp_path):
    _, stats = ccs.run_collect(210, _write_seeds(tmp_path), offline=True)
    assert "federal_register" not in stats["collectors"]
    assert "sec_lockups" not in stats["collectors"]
