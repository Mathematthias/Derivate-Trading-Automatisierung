"""Workflow B (System-Review 2026-10-04): state/*.yaml als Zustand.

Geprueft wird der Vertrag, nicht die Implementierung:
  * YAML-Eintraege ergeben dieselben WatchlistEntry-Objekte, die filter_engine
    bisher aus dem STATE-Doc bekam (Trigger-Grammatik unveraendert).
  * Archivierte Eintraege sind fuer Stufe 1 unsichtbar (alle Legs 🔴).
  * Jede INBOX-Aktion ist idempotent; kaputte Aktionen kippen den Lauf nicht.
  * inbox_apply verarbeitet jede Datei genau einmal.
  * Radar-Fenster und Thesen-Faelligkeit fuer den Digest.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

import state_yaml as sy  # noqa: E402
import inbox_apply as ia  # noqa: E402


def _entry(symbol="SIE.DE", status="aktiv", **kw):
    e = {
        "symbol": symbol, "name": "Siemens AG", "direction": "LONG",
        "klasse": "trend_pullback", "anker": "EMA20", "status": status,
        "added": "2026-09-29", "expiry": "2026-10-19",
        "legs": [
            {"label": "A", "gate": "🟡",
             "text": "nach 2026-09-29 TREND-PULLBACK-LONG: Touch EMA20 ±0,5 ATR [pullback] + 4h-Bullish-Reverse-Close"},
            {"label": "B", "gate": "🔴", "text": "RSI-Cross 50 auf 1D [reverse]"},
        ],
    }
    e.update(kw)
    return e


@pytest.fixture
def state_dir(tmp_path):
    sy.save_state(tmp_path, {
        "watchlist": {"entries": [_entry(), _entry("ZTS", status="archiviert", direction="SHORT")]},
        "radar": {"rows": [
            {"id": "Z5", "date": "2026-10-10", "kat": 1, "ereignis": "Frist X", "werte": "A", "wirkung": "w", "status": "offen"},
            {"id": "Z6", "date": "2026-09-30", "kat": 2, "ereignis": "Alt", "werte": "B", "wirkung": "w", "status": "offen"},
            {"id": "Z7", "date": "2026-10-03", "kat": 3, "ereignis": "Erledigt", "status": "erledigt"},
            {"id": "Z8", "date": "2026-12-24", "kat": 5, "ereignis": "Weit weg", "status": "offen"},
        ]},
        "thesen": {"thesen": [
            {"id": "A", "titel": "AI-Strom", "verdikt": "spielen", "re_check": "2026-10-09", "korb_budget_pct": 4},
            {"id": "X", "titel": "Tot", "verdikt": "verworfen"},
        ]},
    })
    return tmp_path


class TestEntriesFromYaml:

    def test_trigger_grammatik_bleibt(self, state_dir):
        st = sy.load_state(state_dir)
        entries = sy.entries_from_yaml(st["watchlist"])
        sie = next(e for e in entries if e.symbol == "SIE.DE")
        assert sie.direction == "LONG"
        assert sie.status == "aktiv"
        assert sie.status_note == "trend_pullback"
        assert sie.trigger_raw.startswith("🟡 A) nach 2026-09-29 TREND-PULLBACK-LONG")
        assert " · 🔴 B) " in sie.trigger_raw
        assert sie.earliest_date == date(2026, 9, 29)
        assert sie.expiry_date == date(2026, 10, 19)
        assert len(sie.triggers) == 2

    def test_archiviert_hat_nur_rote_legs(self, state_dir):
        st = sy.load_state(state_dir)
        zts = next(e for e in sy.entries_from_yaml(st["watchlist"]) if e.symbol == "ZTS")
        assert "🟡" not in zts.trigger_raw and "🟢" not in zts.trigger_raw
        assert zts.trigger_raw.count("🔴") == 2

    def test_position_bekommt_monitor_token(self, tmp_path):
        st = {"watchlist": {"entries": [
            _entry("DB1.DE", status="position", name="Deutsche Boerse AG (DB1, XETR)", trade_nr="93"),
            _entry("NBIS", status="position", name="Nebius [MONITOR #9 AV]"),
        ]}, "radar": {}, "thesen": {}}
        by = {e.symbol: e for e in sy.entries_from_yaml(st["watchlist"])}
        assert by["DB1.DE"].name == "Deutsche Boerse AG (DB1, XETR) [MONITOR #93]"
        assert by["NBIS"].name == "Nebius [MONITOR #9 AV]"          # nicht doppelt

    def test_leerer_ordner_ist_leerer_zustand(self, tmp_path):
        st = sy.load_state(tmp_path / "nix")
        assert st["watchlist"]["entries"] == [] and st["radar"]["rows"] == []
        assert sy.entries_from_yaml(st["watchlist"]) == []

    def test_save_roundtrip_mit_umlauten_und_emojis(self, state_dir):
        st = sy.load_state(state_dir)
        raw = (state_dir / sy.WATCHLIST_FILE).read_text(encoding="utf-8")
        assert "🟡" in raw and "±0,5 ATR" in raw      # allow_unicode, kein \u-Escape
        assert st["watchlist"]["schema"] == sy.SCHEMA_VERSION
        assert st["watchlist"]["updated"]


class TestApplyActions:
    T = date(2026, 10, 5)

    def test_set_status_archiviert_ist_idempotent(self, state_dir):
        st = sy.load_state(state_dir)
        a = [{"op": "watchlist.set_status", "symbol": "SIE.DE", "status": "archiviert", "reason": "TIW gebrochen"}]
        log1 = sy.apply_actions(st, a, today=self.T)
        snap = json.dumps(st, sort_keys=True, default=str)
        log2 = sy.apply_actions(st, a, today=self.T)
        assert json.dumps(st, sort_keys=True, default=str) == snap
        e = sy._find_entry(st["watchlist"], "sie.de")
        assert e["status"] == "archiviert"
        assert e["archived"] == {"date": "2026-10-05", "reason": "TIW gebrochen"}
        assert log1 == log2

    def test_set_gate_und_expiry(self, state_dir):
        st = sy.load_state(state_dir)
        log = sy.apply_actions(st, [
            {"op": "watchlist.set_gate", "symbol": "SIE.DE", "leg": "b", "gate": "🟢"},
            {"op": "watchlist.set_expiry", "symbol": "SIE.DE", "expiry": "2026-11-01"},
        ], today=self.T)
        e = sy._find_entry(st["watchlist"], "SIE.DE")
        assert e["legs"][1]["gate"] == "🟢"
        assert e["expiry"] == "2026-11-01"
        assert not any(l.startswith("⚠️") for l in log)

    def test_kaputte_aktionen_kippen_nichts(self, state_dir):
        st = sy.load_state(state_dir)
        log = sy.apply_actions(st, [
            {"op": "watchlist.set_gate", "symbol": "NIX", "leg": "A", "gate": "🟢"},     # Symbol fehlt
            {"op": "watchlist.set_gate", "symbol": "SIE.DE", "leg": "Z", "gate": "🟢"},  # Leg fehlt
            {"op": "watchlist.set_gate", "symbol": "SIE.DE", "leg": "A", "gate": "💥"},  # Gate ungueltig
            {"op": "watchlist.set_expiry", "symbol": "SIE.DE", "expiry": "bald"},
            {"op": "watchlist.set_field", "symbol": "SIE.DE", "field": "legs", "value": []},
            {"op": "kaffee.kochen"},
            {"op": "watchlist.set_field", "symbol": "SIE.DE", "field": "treiber", "value": "Q3 2026-11-12"},
        ], today=self.T)
        warn = [l for l in log if l.startswith("⚠️")]
        assert len(warn) == 6
        e = sy._find_entry(st["watchlist"], "SIE.DE")
        assert e["legs"][0]["gate"] == "🟡"           # unveraendert
        assert e["treiber"] == "Q3 2026-11-12"        # die gute Aktion kam durch

    def test_watchlist_add_ersetzt_statt_doppelt(self, state_dir):
        st = sy.load_state(state_dir)
        neu = _entry("GIVN.SW", klasse="breakout_retest")
        sy.apply_actions(st, [{"op": "watchlist.add", "entry": neu}], today=self.T)
        sy.apply_actions(st, [{"op": "watchlist.add", "entry": {**neu, "anker": "Range-Hoch"}}], today=self.T)
        hits = [e for e in st["watchlist"]["entries"] if e["symbol"] == "GIVN.SW"]
        assert len(hits) == 1 and hits[0]["anker"] == "Range-Hoch"
        assert hits[0]["added"] == "2026-09-29"       # aus dem Eintrag, nicht ueberschrieben

    def test_watchlist_add_braucht_legs(self, state_dir):
        st = sy.load_state(state_dir)
        log = sy.apply_actions(st, [{"op": "watchlist.add", "entry": {"symbol": "X"}}], today=self.T)
        assert log[0].startswith("⚠️") and sy._find_entry(st["watchlist"], "X") is None

    def test_radar_add_idempotent_ueber_datum_und_ereignis(self, state_dir):
        st = sy.load_state(state_dir)
        row = {"date": "2026-10-28", "kat": 1, "ereignis": "Q3 GOOGL", "werte": "GOOGL", "wirkung": "x"}
        sy.apply_actions(st, [{"op": "radar.add", "row": row}], today=self.T)
        sy.apply_actions(st, [{"op": "radar.add", "row": dict(row)}], today=self.T)
        hits = [r for r in st["radar"]["rows"] if r["ereignis"] == "Q3 GOOGL"]
        assert len(hits) == 1
        assert hits[0]["id"] == "Z9" and hits[0]["status"] == "offen"

    def test_radar_set_status_und_field(self, state_dir):
        st = sy.load_state(state_dir)
        log = sy.apply_actions(st, [
            {"op": "radar.set_status", "id": "Z5", "status": "erledigt", "note": "lief"},
            {"op": "radar.set_field", "id": "Z8", "field": "date", "value": "2027-01-10"},
            {"op": "radar.set_field", "id": "Z8", "field": "id", "value": "Z99"},
            {"op": "radar.set_status", "id": "Z404", "status": "erledigt"},
        ], today=self.T)
        rows = {r["id"]: r for r in st["radar"]["rows"]}
        assert rows["Z5"]["status"] == "erledigt" and rows["Z5"]["note"] == "lief"
        assert rows["Z8"]["date"] == "2027-01-10"
        assert sum(l.startswith("⚠️") for l in log) == 2

    def test_thesen_update_fuehrt_historie(self, state_dir):
        st = sy.load_state(state_dir)
        sy.apply_actions(st, [
            {"op": "thesen.update", "id": "A", "verdikt": "spielen", "re_check": "2026-10-16", "crowdedness_pp": 4.8},
            {"op": "thesen.update", "id": "N2", "titel": "Neu", "verdikt": "beobachten"},
        ], today=self.T)
        th = {t["id"]: t for t in st["thesen"]["thesen"]}
        assert th["A"]["re_check"] == "2026-10-16" and th["A"]["crowdedness_pp"] == 4.8
        assert th["A"]["historie"][-1]["date"] == "2026-10-05"
        assert th["N2"]["titel"] == "Neu"

    def test_note_add_landet_in_notes(self, state_dir):
        st = sy.load_state(state_dir)
        sy.apply_actions(st, [{"op": "note.add", "kategorie": "INFO", "text": "Hallo"}], today=self.T)
        assert st["_notes"][0]["text"] == "Hallo"


class TestDigestBloecke:
    T = date(2026, 10, 5)

    def test_radar_window(self, state_dir):
        st = sy.load_state(state_dir)
        w = sy.radar_window(st["radar"], self.T, days=28)
        assert [r["id"] for r in w["einrueckend"]] == ["Z5"]        # Z8 zu weit, Z7 erledigt
        assert [r["id"] for r in w["ueberfaellig"]] == ["Z6"]
        assert w["einrueckend"][0]["tage"] == 5 and w["ueberfaellig"][0]["tage"] == -5

    def test_thesen_aktiv_und_faellig(self, state_dir):
        st = sy.load_state(state_dir)
        th = sy.thesen_aktiv(st["thesen"], date(2026, 10, 9))
        assert [t["id"] for t in th] == ["A"]                       # verworfen faellt raus
        assert th[0]["re_check_faellig"] is True
        assert sy.thesen_aktiv(st["thesen"], self.T)[0]["re_check_faellig"] is False

    def test_state_for_digest_hat_alle_bloecke(self, state_dir):
        st = sy.load_state(state_dir)
        d = sy.state_for_digest(st, self.T)
        assert set(d) == {"watchlist", "radar", "thesen", "updated"}
        meta = {m["symbol"]: m for m in d["watchlist"]}
        assert meta["SIE.DE"]["klasse"] == "trend_pullback"
        assert meta["SIE.DE"]["gates"] == ["🟡", "🔴"]
        assert meta["ZTS"]["status"] == "archiviert"
        json.dumps(d)                                               # JSON-faehig fuer den Digest


class TestInboxApply:
    T = date(2026, 10, 5)

    def _inbox(self, tmp_path, name, payload):
        d = tmp_path / "inbox"
        d.mkdir(exist_ok=True)
        (d / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return d

    def test_datei_wird_genau_einmal_angewendet(self, state_dir, tmp_path):
        inbox = self._inbox(tmp_path, "INBOX-thesen-lauf-20261005.json", {
            "schema": 1, "source": "thesen-lauf", "actions": [
                {"op": "thesen.update", "id": "A", "verdikt": "spielen", "re_check": "2026-10-16"},
                {"op": "watchlist.set_expiry", "symbol": "SIE.DE", "expiry": "2026-10-30"},
            ]})
        r1 = ia.apply_inbox(state_dir, ia.iter_local_inbox(inbox), today=self.T)
        assert r1["applied"] == ["INBOX-thesen-lauf-20261005.json"] and r1["changed"]
        r2 = ia.apply_inbox(state_dir, ia.iter_local_inbox(inbox), today=self.T)
        assert r2["skipped"] == ["INBOX-thesen-lauf-20261005.json"] and not r2["changed"]
        st = sy.load_state(state_dir)
        assert sy._find_entry(st["watchlist"], "SIE.DE")["expiry"] == "2026-10-30"
        processed = sy.load_processed(state_dir)
        assert len(processed) == 1 and list(processed.values())[0]["status"] == "ok"

    def test_geaenderte_datei_gleicher_name_zaehlt_als_neu(self, state_dir, tmp_path):
        inbox = self._inbox(tmp_path, "INBOX-x.json", {"schema": 1, "source": "test", "actions": []})
        ia.apply_inbox(state_dir, ia.iter_local_inbox(inbox), today=self.T)
        self._inbox(tmp_path, "INBOX-x.json", {"schema": 1, "source": "test", "actions": [
            {"op": "note.add", "text": "zweite Fassung"}]})
        r = ia.apply_inbox(state_dir, ia.iter_local_inbox(inbox), today=self.T)
        assert r["applied"] == ["INBOX-x.json"]
        assert "zweite Fassung" in (state_dir / sy.NOTES_FILE).read_text(encoding="utf-8")

    def test_kaputte_datei_wird_registriert_nicht_wiederholt(self, state_dir, tmp_path):
        d = tmp_path / "inbox"
        d.mkdir()
        (d / "INBOX-kaputt.json").write_text("{nicht json", encoding="utf-8")
        (d / "INBOX-schema.json").write_text(json.dumps({"schema": 7, "actions": []}), encoding="utf-8")
        r = ia.apply_inbox(state_dir, ia.iter_local_inbox(d), today=self.T)
        assert sorted(r["failed"]) == ["INBOX-kaputt.json", "INBOX-schema.json"]
        assert not r["changed"]
        r2 = ia.apply_inbox(state_dir, ia.iter_local_inbox(d), today=self.T)
        assert len(r2["skipped"]) == 2 and not r2["failed"]
        # Zustand unveraendert
        assert sy.load_state(state_dir)["watchlist"]["entries"][0]["expiry"] == "2026-10-19"

    def test_dry_run_schreibt_nichts(self, state_dir, tmp_path):
        inbox = self._inbox(tmp_path, "INBOX-d.json", {"schema": 1, "source": "test", "actions": [
            {"op": "watchlist.set_expiry", "symbol": "SIE.DE", "expiry": "2026-12-31"}]})
        r = ia.apply_inbox(state_dir, ia.iter_local_inbox(inbox), today=self.T, dry_run=True)
        assert r["applied"] and sy.load_state(state_dir)["watchlist"]["entries"][0]["expiry"] == "2026-10-19"
        assert not (state_dir / sy.PROCESSED_FILE).exists()

    def test_cli_lokal(self, state_dir, tmp_path, capsys):
        inbox = self._inbox(tmp_path, "INBOX-cli.json", {"schema": 1, "source": "test", "actions": [
            {"op": "radar.add", "row": {"date": "2026-10-20", "kat": 1, "ereignis": "CLI", "werte": "", "wirkung": ""}}]})
        rc = ia.main(["--state-dir", str(state_dir), "--inbox-dir", str(inbox), "--today", "2026-10-05"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "angewendet: 1" in out and "radar Z9: neu (2026-10-20)" in out


class TestRepoState:
    """Der eingecheckte Zustand muss ladbar und fuer filter_engine brauchbar sein."""

    REPO_STATE = Path(_HERE).parent / "state"

    def test_watchlist_yaml_laedt_und_parst(self):
        st = sy.load_state(self.REPO_STATE)
        entries = sy.entries_from_yaml(st["watchlist"])
        assert len(entries) >= 40
        aktiv = [e for e in st["watchlist"]["entries"] if e["status"] == "aktiv"]
        assert all(e["klasse"] in sy.KLASSEN for e in st["watchlist"]["entries"])
        assert all(e["status"] in sy.STATUS_WATCHLIST for e in st["watchlist"]["entries"])
        # Gestrichene Klassen duerfen nur noch im Archiv stehen
        assert all(e["status"] == "archiviert" for e in st["watchlist"]["entries"]
                   if e["klasse"] in sy.KLASSEN_GESTRICHEN)
        # Review-Entscheide 2026-10-04 sind drin
        by = {e["symbol"]: e for e in st["watchlist"]["entries"]}
        for sym in ("HLMA.L", "LIN", "HLN.L", "ALC.SW", "ZTS"):
            assert by[sym]["status"] == "archiviert", sym
        # HOLN.SW: der Grinder-Short (Entscheid 2026-10-04) bleibt weg; die Zeile wurde
        # am 2026-10-07 als Breakdown-Retest-Short neu angelegt (User-Entscheid).
        assert not (by["HOLN.SW"]["status"] == "aktiv" and by["HOLN.SW"]["klasse"] == "grinder")
        assert by["GIVN.SW"]["klasse"] == "breakout_retest"
        assert "BREAKOUT-RETEST-LONG" in by["TMO"]["legs"][0]["text"]
        assert len(aktiv) >= 30

    def test_radar_und_thesen_laden(self):
        st = sy.load_state(self.REPO_STATE)
        assert all(r.get("ereignis") for r in st["radar"]["rows"])
        assert all(r["status"] in ("offen", "erledigt", "verworfen", "verschoben") for r in st["radar"]["rows"])
        ids = [t["id"] for t in st["thesen"]["thesen"]]
        assert "A" in ids


def test_leg_tiw_relativ_und_fest():
    """Skill v58 (2026-10-09): relative TIW auf einer EMA, feste TIW unveraendert."""
    from state_yaml import _leg_tiw
    assert _leg_tiw("TIW = 1D-Schluss unter 421,10$ (EMA50-1D = 4h-EMA100).") == {
        "seite": "unter", "level": 421.10}
    assert _leg_tiw("TIW = 1D-Schluss unter EMA50-1D -0,30 ATR. TP1 28,80") == {
        "seite": "unter", "level": None, "anker": "EMA50", "off": -0.3}
    assert _leg_tiw("TIW = 1D-Schluss ueber EMA20-1D. TP1 230,50$") == {
        "seite": "ueber", "level": None, "anker": "EMA20", "off": 0.0}
    assert _leg_tiw("kein Invalidator") is None
