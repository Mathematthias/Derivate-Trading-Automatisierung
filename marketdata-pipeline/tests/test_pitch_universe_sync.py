"""Tests für den Pitch/Universe-Sync im Tier-A-Lauf (2026-09-15).

ANLASS — der Digest war in sich inkonsistent, und zwar doppelt:

(1) FELDLÜCKE. `build_pitches_payload` schrieb bewusst kein ATR/OHLC ("Entry/
    SL/TP bleiben chart-zu-verifizieren"). Solange Pitches aus dem Tier-A-
    Universum kamen, fiel das nicht auf — der `universe`-Block trug die Zahlen.
    Nach der Erweiterung auf ~500 Scan-Symbole standen am 2026-09-15 6 von 10
    Pitches ohne Kurs, ATR, Earnings und bar_date im Digest: nicht rechenbar,
    weder SL noch Stückzahl noch R:R noch Fächer-Prüfung.

(2) ZEITVERSATZ, der gefährlichere Teil. Der Merge lief HINTER dem Pull und zog
    die jüngste PITCHES-Datei unverändert ein. Tier B läuft zwischen 11:30 und
    18:00 nicht — der EU-Block war im 15:32-Digest fast vier Stunden alt. Vier
    Symbole standen in beiden Blöcken DESSELBEN Digests mit zwei verschiedenen
    Kursen (bis 1,15 % Abweichung), und nichts sagte, welcher wann galt.

FIX: `load_merged_pitches` läuft vor `build_pull_universe`, die Symbole gehen in
den Pull. Damit ist der Pitch-Satz taggleich mit dem Rest — und die Feld-
Erweiterung im Payload ist nur noch der Fallback für ein im Pull ausgefallenes
Symbol.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

import marketdata_sync as ms  # noqa: E402
from filter_engine import build_pitches_payload, CandidateMatch  # noqa: E402


@pytest.fixture
def config():
    cfg_path = os.path.join(_HERE, "..", "config", "filter_config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class FakeSnap:
    symbol: str
    price: float
    ema20: float
    atr14: float
    move_30d_pct: float
    rsi14: float = 50.0
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None
    last_bar_date: Optional[str] = None
    next_earnings_date: Optional[str] = None


def _match(symbol, bucket, price, ema20, atr14, move30, **kw):
    snap = FakeSnap(symbol=symbol, price=price, ema20=ema20, atr14=atr14,
                    move_30d_pct=move30, **kw)
    return CandidateMatch(symbol=symbol, bucket=bucket, snapshot=snap,
                          score=0.0, summary="")


def _fake_files(eu=None, us=None):
    """Ersetzt read_latest_json_file durch eine Tabelle Prefix -> JSON-dict."""
    table = {"PITCHES-EU-": eu, "PITCHES-US-": us}

    def _reader(drive_service, folder_id, prefix):
        return table.get(prefix)

    return _reader


EU_FILE = {
    "generated": "2026-09-15T11:35:00+02:00",
    "ranked": [
        {"symbol": "TLX.DE", "lane": "trend", "rrprox": 2.15},
        {"symbol": "PGHN.SW", "lane": "counter", "rrprox": 4.86},
    ],
    "grinders": [],
    "grinders_total": 0,
}
US_FILE = {
    "generated": "2026-09-15T14:33:00+02:00",
    "ranked": [
        {"symbol": "TGT", "lane": "trend", "rrprox": 1.88},
        {"symbol": "HON", "lane": "counter", "rrprox": 4.30},
    ],
    "grinders": [{"symbol": "AD.AS", "tempo": 1.2}],
    "grinders_total": 3,
}


class TestLoadMergedPitches:

    def test_merged_und_quotiert(self, config, monkeypatch):
        monkeypatch.setattr(ms, "read_latest_json_file", _fake_files(EU_FILE, US_FILE))
        b = ms.load_merged_pitches(None, "folder", config)
        assert {p["symbol"] for p in b["pitches"]} == {"TLX.DE", "PGHN.SW", "TGT", "HON"}
        assert b["meta"]["total_by_tier"] == {"EU": 0, "US": 3}

    def test_as_of_wird_je_quelldatei_gesetzt(self, config, monkeypatch):
        """Ohne as_of wäre ein künftiger Zeitversatz wieder unsichtbar."""
        monkeypatch.setattr(ms, "read_latest_json_file", _fake_files(EU_FILE, US_FILE))
        b = ms.load_merged_pitches(None, "folder", config)
        by = {p["symbol"]: p["as_of"] for p in b["pitches"]}
        assert by["TLX.DE"] == "2026-09-15T11:35:00+02:00"
        assert by["TGT"] == "2026-09-15T14:33:00+02:00"

    def test_vorhandenes_as_of_gewinnt(self, config, monkeypatch):
        eu = {"generated": "2026-09-15T11:35:00+02:00",
              "ranked": [{"symbol": "X.DE", "lane": "trend", "rrprox": 2.0,
                          "as_of": "2026-09-15T09:00:00+02:00"}],
              "grinders": [], "grinders_total": 0}
        monkeypatch.setattr(ms, "read_latest_json_file", _fake_files(eu, None))
        b = ms.load_merged_pitches(None, "folder", config)
        assert b["pitches"][0]["as_of"] == "2026-09-15T09:00:00+02:00"

    def test_fehlende_files_kippen_nichts(self, config, monkeypatch):
        """Noch kein B/C-Lauf → leere Listen, Digest läuft ohne Pitches."""
        monkeypatch.setattr(ms, "read_latest_json_file", _fake_files(None, None))
        b = ms.load_merged_pitches(None, "folder", config)
        assert b["pitches"] == [] and b["grinders"] == []

    def test_ranked_fehlt_im_file(self, config, monkeypatch):
        monkeypatch.setattr(ms, "read_latest_json_file", _fake_files({"generated": "x"}, None))
        b = ms.load_merged_pitches(None, "folder", config)
        assert b["pitches"] == []


class TestPitchSymbols:

    def test_extrahiert_symbole(self):
        b = {"pitches": [{"symbol": "AAA"}, {"symbol": "BBB"}]}
        assert ms.pitch_symbols(b) == {"AAA", "BBB"}

    def test_none_und_leer(self):
        assert ms.pitch_symbols(None) == set()
        assert ms.pitch_symbols({"pitches": []}) == set()

    def test_ignoriert_kaputte_zeilen(self):
        b = {"pitches": [{"symbol": "AAA"}, {"symbol": None}, {}, "murks"]}
        assert ms.pitch_symbols(b) == {"AAA"}


class TestPullVerdrahtung:
    """Die Logik aus main(): Pitch-Symbole rein, Ethik gewinnt, nicht doppelt scannen.

    main() selbst ist ohne Drive nicht aufrufbar; geprüft wird die Mengenlogik,
    die dort steht — sie ist der eigentliche Fix.
    """

    def _verdrahten(self, all_symbols, excluded, excluded_cat, bundle):
        extra = ms.pitch_symbols(bundle) - excluded
        all_symbols |= extra
        excluded_cat |= extra
        return all_symbols, excluded_cat

    def test_pitch_symbole_landen_im_pull(self):
        alle, cat = self._verdrahten({"SAP.DE"}, set(), set(), {"pitches": [{"symbol": "TGT"}]})
        assert "TGT" in alle

    def test_ethik_gewinnt_gegen_pitch(self):
        """Ein ethik-ausgeschlossenes Symbol wird nie gepullt — auch nicht gerankt."""
        alle, cat = self._verdrahten({"SAP.DE"}, {"RHM.DE"}, set(),
                                     {"pitches": [{"symbol": "RHM.DE"}, {"symbol": "TGT"}]})
        assert "RHM.DE" not in alle and "TGT" in alle

    def test_pitch_symbole_nicht_doppelt_gescannt(self):
        """Sonst erschiene derselbe Wert zweimal: als Pitch und als Universe-Match."""
        alle, cat = self._verdrahten({"SAP.DE"}, set(), set(), {"pitches": [{"symbol": "TGT"}]})
        assert "TGT" in cat

    def test_watchlist_symbol_als_pitch_ist_kein_konflikt(self):
        """TLX.DE stand am 2026-09-15 als Watchlist-Zeile UND im Pitch-Block."""
        alle, cat = self._verdrahten({"TLX.DE"}, set(), set(), {"pitches": [{"symbol": "TLX.DE"}]})
        assert alle == {"TLX.DE"} and cat == {"TLX.DE"}


class TestPayloadFallbackFelder:

    def _universe(self):
        return [_match("AAA", "long_trend_pullback", 100, 99.5, 5.0, +8.0,
                       high_20d=115, last_bar_date="2026-09-15",
                       next_earnings_date="2026-11-12")]

    def test_atr_bar_date_earnings_im_payload(self, config):
        p = build_pitches_payload(self._universe(), config, source_tag="EU")[0]
        assert p["atr"] == pytest.approx(5.0)
        assert p["bar_date"] == "2026-09-15"
        assert p["earn_next"] == "2026-11-12"

    def test_fehlende_felder_werden_none_nicht_fehler(self, config):
        m = _match("BBB", "long_trend_pullback", 100, 99.5, 5.0, +8.0, high_20d=115)
        p = build_pitches_payload([m], config, source_tag="EU")[0]
        assert p["bar_date"] is None and p["earn_next"] is None

    def test_atr_ist_pflicht_fuer_die_rechenbarkeit(self, config):
        """Die Kernzusage: ein Pitch trägt jetzt die Größe, ohne die nichts geht."""
        for p in build_pitches_payload(self._universe(), config, source_tag="EU"):
            assert p["atr"] is not None


class TestSyncKontrolle:
    """Ein Pitch-Symbol ohne Snapshot darf den Lauf nicht kippen — aber auffallen."""

    def test_fehlendes_symbol_wird_erkannt(self):
        pitches = [{"symbol": "TGT"}, {"symbol": "WEG.WEG"}]
        snapshots = {"TGT": object()}
        fehlend = sorted(p["symbol"] for p in pitches
                         if p.get("symbol") and p["symbol"] not in snapshots)
        assert fehlend == ["WEG.WEG"]

    def test_alles_synchron_meldet_nichts(self):
        pitches = [{"symbol": "TGT"}]
        snapshots = {"TGT": object()}
        fehlend = [p["symbol"] for p in pitches if p["symbol"] not in snapshots]
        assert fehlend == []


class TestPitchDedupe:
    """Ein Symbol, ein Pitch — Befund aus dem ersten Lauf nach dem Merge-Fix.

    Am 2026-09-15 17:02 stand SY1.DE zweimal im Pitch-Block (as_of 16:57 und
    16:59, identische Zahlen). Die Grinder haben seit dem 2026-09-08 einen
    Dedupe, die Pitches nicht — obwohl dort dasselbe Argument gilt und bei
    einer Quote von 6/4 jedes Duplikat einen von zehn Plaetzen frisst.
    """

    def test_duplikat_wird_entfernt(self):
        p = [{"symbol": "SY1.DE", "rrprox": 1.66, "lane": "trend"},
             {"symbol": "SY1.DE", "rrprox": 1.66, "lane": "trend"},
             {"symbol": "DHR", "rrprox": 1.66, "lane": "trend"}]
        out = ms.dedupe_pitches(p)
        assert [x["symbol"] for x in out] == ["SY1.DE", "DHR"]

    def test_bestes_rrprox_gewinnt(self):
        p = [{"symbol": "X", "rrprox": 1.2, "tier": "EU"},
             {"symbol": "X", "rrprox": 2.4, "tier": "US"}]
        out = ms.dedupe_pitches(p)
        assert len(out) == 1 and out[0]["rrprox"] == 2.4 and out[0]["tier"] == "US"

    def test_reihenfolge_der_ersten_vorkommen_bleibt(self):
        p = [{"symbol": "A", "rrprox": 1.0}, {"symbol": "B", "rrprox": 9.0},
             {"symbol": "A", "rrprox": 5.0}]
        assert [x["symbol"] for x in ms.dedupe_pitches(p)] == ["A", "B"]

    def test_leer_und_kaputt(self):
        assert ms.dedupe_pitches([]) == []
        assert ms.dedupe_pitches(["murks", {}, {"symbol": None}]) == []

    def test_dedupe_laeuft_vor_der_quote(self, config, monkeypatch):
        """In der anderen Reihenfolge belegen Duplikate noch Plaetze."""
        viele = [{"symbol": f"T{i}", "lane": "trend", "rrprox": 2.0 - i * 0.1} for i in range(6)]
        eu = {"generated": "2026-09-15T16:59:00+02:00",
              "ranked": [{"symbol": "DUP", "lane": "trend", "rrprox": 5.0}] + viele,
              "grinders": [], "grinders_total": 0}
        us = {"generated": "2026-09-15T16:57:00+02:00",
              "ranked": [{"symbol": "DUP", "lane": "trend", "rrprox": 5.0}],
              "grinders": [], "grinders_total": 0}
        monkeypatch.setattr(ms, "read_latest_json_file", _fake_files(eu, us))
        b = ms.load_merged_pitches(None, "folder", config)
        syms = [p["symbol"] for p in b["pitches"]]
        assert syms.count("DUP") == 1
        assert b["pitch_duplicates_removed"] == 1
        # Quote trend=6: DUP + die fünf besten T-Werte, T5 faellt raus
        assert len(syms) == 6 and "T5" not in syms
