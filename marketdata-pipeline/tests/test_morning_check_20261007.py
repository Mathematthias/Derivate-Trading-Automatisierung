"""Befunde aus dem Morning Check 2026-10-07.

1. Fehlender Vortagesbalken: Um 10:02 CEST hatten alle EU-Ticker den laufenden
   07.10.-Balken, aber nicht den 06.10. prev_close war damit der Schluss vom
   05.10.; chg und gap waren falsch (JEN +0,47 % statt -3,3 %), und der
   Carry-Forward der Filter-Engine haette den 05.10. als „letzten Schluss" gelesen.
2. Frische: ^VIX trug schon den 07.10.-Balken und schob die ganze US-Gruppe auf
   „latest 07.10." — 76 US-Ticker standen als stale statt pre_session.
3. Zustands-Metadaten: Der Morning Check sah geparkte aktive Zeilen (VOS.DE)
   und naeherrueckende Re-Evals archivierter Zeilen nicht; dafuer traegt
   watchlist_meta jetzt `tiw` und `reeval`.
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

import state_yaml as sy  # noqa: E402
from digest_renderer import _compact_snap, _data_freshness  # noqa: E402
from market_data import _compute_snapshot, _werktag_fehlt  # noqa: E402


def _df(dates, closes):
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    return pd.DataFrame({"Open": closes, "High": [c * 1.01 for c in closes],
                         "Low": [c * 0.99 for c in closes], "Close": closes,
                         "Volume": [1_000_000] * len(closes)}, index=idx)


class TestWerktagFehlt:

    def test_lueckenlos(self):
        assert not _werktag_fehlt("2026-10-06", "2026-10-07")

    def test_wochenende_ist_keine_luecke(self):
        assert not _werktag_fehlt("2026-10-02", "2026-10-05")

    def test_fehlender_dienstag(self):
        assert _werktag_fehlt("2026-10-05", "2026-10-07")

    def test_ohne_daten(self):
        assert not _werktag_fehlt(None, "2026-10-07")


class TestPrevLuecke:

    def _jen(self, mit_06):
        dates = list(pd.bdate_range("2026-08-01", "2026-10-05").strftime("%Y-%m-%d"))
        closes = [40.0 + i * 0.01 for i in range(len(dates))]
        dates[-1], closes[-1] = "2026-10-05", 42.30
        if mit_06:
            dates.append("2026-10-06"); closes.append(43.96)
        dates.append("2026-10-07"); closes.append(42.50)
        return _compute_snapshot("JEN.DE", _df(dates, closes))

    def test_luecke_unterdrueckt_chg_und_flaggt(self):
        s = self._jen(mit_06=False)
        assert s.prev_luecke is True
        assert s.prev_bar_date == "2026-10-05"
        assert s.change_pct is None
        d = _compact_snap(s)
        assert d["chg"] is None and d["prev_luecke"] is True
        assert "gap" not in d

    def test_ohne_luecke_wie_bisher(self):
        s = self._jen(mit_06=True)
        assert s.prev_luecke is False
        assert round(s.change_pct, 2) == round((42.50 / 43.96 - 1) * 100, 2)
        d = _compact_snap(s)
        assert d["prev_close"] == 43.96 and d["prev_bar_date"] == "2026-10-06"
        assert "prev_luecke" not in d


class TestFrischeModus:

    TS = datetime(2026, 10, 7, 8, 2, tzinfo=timezone.utc)   # 10:02 CEST

    def test_vix_voraus_kippt_us_nicht(self):
        uni = {s: {"bar_date": "2026-10-06"} for s in ("AAPL", "WMT", "LLY", "^GSPC")}
        uni["^VIX"] = {"bar_date": "2026-10-07"}
        uni.update({s: {"bar_date": "2026-10-07"} for s in ("SIE.DE", "JEN.DE", "G1A.DE")})
        uni["ACT.DE"] = {"bar_date": "2026-10-05"}
        r = _data_freshness(uni, self.TS)
        assert r["groups"]["US"]["latest"] == "2026-10-06"
        assert r["pre_session"] == ["US"]
        assert r["stale"] == ["ACT.DE"]

    def test_haengender_einzelfeed_bleibt_stale(self):
        uni = {s: {"bar_date": "2026-10-07"} for s in ("SIE.DE", "JEN.DE", "G1A.DE")}
        uni["ACT.DE"] = {"bar_date": "2026-10-05"}
        assert _data_freshness(uni, self.TS)["stale"] == ["ACT.DE"]


class TestMetaTiwReeval:

    def test_tiw_und_reeval(self):
        block = {"entries": [
            {"symbol": "VOS.DE", "status": "archiviert", "legs": [{"label": "A", "gate": "🔴",
             "text": "ARCHIVIERT 2026-10-07 - TIW 51,15 per Schluss gebrochen. RE-EVAL: 1D-Schluss <50,02€ + Vol >Avg-20d."}]},
            {"symbol": "HOLN.SW", "status": "aktiv", "legs": [{"label": "A", "gate": "🟡",
             "text": "nach 2026-10-07 BREAKDOWN-RETEST-SHORT: Touch 62,86–64,93€ [pullback]. TIW = 1D-Schluss ueber 64,10€. TP1 60,10€."}]},
            {"symbol": "EQIX", "status": "archiviert", "legs": [{"label": "A", "gate": "🔴",
             "text": "ARCHIVIERT - kein Entry-Trigger. RE-EVAL: 1D-Schluss >1.065,00$ + Vol >Avg-20d."}]},
        ]}
        m = {x["symbol"]: x for x in sy.watchlist_meta(block)}
        assert m["VOS.DE"]["reeval"] == {"op": "<", "level": 50.02}
        assert m["HOLN.SW"]["tiw"] == {"seite": "ueber", "level": 64.1}
        assert m["HOLN.SW"]["reeval"] is None
        assert m["EQIX"]["reeval"] == {"op": ">", "level": 1065.0}

    def test_reeval_in_worten_wird_nicht_geraten(self):
        block = {"entries": [{"symbol": "X", "status": "archiviert", "legs": [{"label": "A", "gate": "🔴",
                  "text": "RE-EVAL bei Entscheidung ueber das Angebot."}]}]}
        assert sy.watchlist_meta(block)[0]["reeval"] is None
