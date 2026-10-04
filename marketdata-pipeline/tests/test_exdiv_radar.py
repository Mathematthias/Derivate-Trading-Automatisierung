"""Ex-Tag-Radar (vorwärts) im BRIEFING-DIGEST — 2026-10-04.

Anlass: SBLK-Position #11 AV. Der Ex-Abschlag von 0,90 USD (≈3 % vom Kurs)
frisst rund die Hälfte des Abstands zum Stop. V1.2 (Note #67) schaut nur
rückwärts; dieser Block meldet den NÄCHSTEN Ex-Tag für Positionen und
Watchlist-Zeilen, solange noch Zeit für eine Entscheidung ist.
"""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd

from digest_renderer import (EXDIV_RADAR_DAYS, _exdiv_radar,
                             build_briefing_digest)
from market_data import TickerSnapshot, _compute_ex_dividend_fields

HEUTE = dt.date(2026, 10, 4)

# Echte SBLK-Historie (Ex-Tage/Beträge laut dividendhistory.org, 2026-10-04)
SBLK_EX = {
    "2025-03-04": 0.09, "2025-06-06": 0.05, "2025-08-28": 0.05,
    "2025-12-05": 0.11, "2026-03-09": 0.37, "2026-06-12": 0.50,
    "2026-08-21": 0.90,
}


def _snap(sym: str, ex: dict, price: float, atr: float = 0.95,
          bis: str = "2026-10-02") -> TickerSnapshot:
    idx = pd.bdate_range("2024-10-01", bis)
    df = pd.DataFrame(
        {"Close": [price] * len(idx),
         "Dividends": [ex.get(d.date().isoformat(), 0.0) for d in idx]},
        index=idx,
    )
    s = TickerSnapshot(symbol=sym, timestamp=dt.datetime(2026, 10, 2),
                       price=price, prev_close=price)
    s.atr14 = atr
    _compute_ex_dividend_fields(s, df)
    return s


def _result(sym: str, direction: str = "LONG", name: str | None = None):
    entry = SimpleNamespace(symbol=sym, name=name or sym, direction=direction,
                            expiry_date=None, triggers=[])
    return SimpleNamespace(entry=entry, trigger_results=[], note=None,
                           overall_status="active")


# --- Schätzung ------------------------------------------------------------

def test_sblk_saisonale_schaetzung_trifft_den_vorjahrestermin():
    s = _snap("SBLK", SBLK_EX, 29.785)
    # Kadenz allein hätte 2026-11-20 gesagt; der Vorjahrestermin 2025-12-05
    # (+365 d = Samstag) wird auf Freitag 2026-12-04 gezogen.
    assert s.next_ex_div_date == "2026-12-04"
    assert s.next_ex_div_source == "saisonal"
    assert s.div_cadence_days == 91


def test_ttm_ist_gezahlt_nicht_hochgerechnet():
    s = _snap("SBLK", SBLK_EX, 29.785)
    assert s.div_ttm_count == 4                      # Dez, Mär, Jun, Aug
    assert abs(s.div_ttm - 1.88) < 1e-9              # 0,11+0,37+0,50+0,90
    assert abs(s.div_yield_ttm_pct - 1.88 / 29.785 * 100) < 1e-9


def test_regelmaessiger_ausschuetter_bleibt_bei_kadenz():
    ex = {"2025-01-15": 0.5, "2025-04-16": 0.5, "2025-07-16": 0.5,
          "2025-10-15": 0.5, "2026-01-14": 0.5, "2026-04-15": 0.5,
          "2026-07-15": 0.5}
    s = _snap("REG", ex, 50.0)
    assert s.next_ex_div_source == "kadenz"
    assert s.next_ex_div_date == "2026-10-14"


def test_schaetzung_nie_am_wochenende():
    s = _snap("SBLK", SBLK_EX, 29.785)
    assert dt.date.fromisoformat(s.next_ex_div_date).weekday() < 5


# --- Radar ----------------------------------------------------------------

def test_position_im_fenster_wird_gemeldet():
    snaps = {"SBLK": _snap("SBLK", SBLK_EX, 29.785)}
    r = _result("SBLK", "POSITION-MONITOR (LONG)",
                "Star Bulk Carriers [MONITOR #11 AV]")
    rad = _exdiv_radar(snaps, [r], {}, dt.date(2026, 11, 20))
    assert len(rad) == 1
    z = rad[0]
    assert z["rolle"] == "position" and z["tage"] == 14
    assert z["ex_next"] == "2026-12-04" and z["ex_src"] == "saisonal"
    assert z["amt_last"] == 0.9
    assert z["abschlag_pct"] == round(0.9 / 29.785 * 100, 2)   # 3,02
    assert z["abschlag_atr"] == round(0.9 / 0.95, 2)


def test_ausserhalb_des_fensters_schweigt():
    snaps = {"SBLK": _snap("SBLK", SBLK_EX, 29.785)}
    rad = _exdiv_radar(snaps, [_result("SBLK")], {}, HEUTE)  # 61 Tage
    assert rad == []
    assert EXDIV_RADAR_DAYS == 21


def test_vergangene_schaetzung_faellt_raus():
    snaps = {"SBLK": _snap("SBLK", SBLK_EX, 29.785)}
    rad = _exdiv_radar(snaps, [_result("SBLK")], {}, dt.date(2026, 12, 7))
    assert rad == []


def test_ohne_dividende_kein_eintrag():
    s = _snap("NODIV", {}, 10.0)
    rad = _exdiv_radar({"NODIV": s}, [_result("NODIV")], {}, HEUTE)
    assert rad == []


def test_positionen_vor_watchlist_und_bucket_wird_mitgegeben():
    a = _snap("AAA", SBLK_EX, 30.0)
    b = _snap("BBB", SBLK_EX, 30.0)
    ra = _result("AAA", "LONG")
    rb = _result("BBB", "POSITION-MONITOR (LONG)")
    rad = _exdiv_radar({"AAA": a, "BBB": b}, [ra, rb],
                       {"very_close": [ra]}, dt.date(2026, 11, 25))
    assert [z["symbol"] for z in rad] == ["BBB", "AAA"]
    assert rad[1]["bucket"] == "very_close"
    assert rad[0]["bucket"] is None


def test_short_richtung_wird_erkannt():
    s = _snap("SSS", SBLK_EX, 30.0)
    rad = _exdiv_radar({"SSS": s}, [_result("SSS", "SHORT (Breakdown)")], {},
                       dt.date(2026, 11, 25))
    assert rad[0]["dir"] == "SHORT"


def test_digest_traegt_das_feld():
    raw = build_briefing_digest({}, [], [], [],
                                dt.datetime(2026, 10, 4, 8, 0,
                                            tzinfo=dt.timezone.utc))
    assert json.loads(raw)["exdiv_radar"] == []


def test_digest_end_to_end_mit_position():
    """Durch build_briefing_digest (inkl. Bucket-Klassifikation), nicht nur
    durch die Hilfsfunktion."""
    s = _snap("SBLK", SBLK_EX, 29.785)
    r = _result("SBLK", "POSITION-MONITOR (LONG)",
                "Star Bulk Carriers [MONITOR #11 AV]")
    raw = build_briefing_digest({"SBLK": s}, [r], [], [],
                                dt.datetime(2026, 11, 20, 8, 0,
                                            tzinfo=dt.timezone.utc))
    d = json.loads(raw)
    assert d["schema"] == "briefing-digest/v3"
    assert [z["symbol"] for z in d["exdiv_radar"]] == ["SBLK"]
    assert d["exdiv_radar"][0]["rolle"] == "position"
    assert d["exdiv_radar"][0]["bucket"] == "far"
