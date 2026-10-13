"""Fehlender Vortagesbalken — Ursache und Reparatur (2026-10-13).

Diagnose (Branch diag/vortagesbalken, Rohantwort v8/chart um 12:21 UTC):
Yahoo lieferte fuer SAP.DE, ABBN.SW, RACE.MI und SMIN.L den 12.10. mit
Zeitstempel, aber OHLCV = null; EURUSD=X fehlte der 12.10. ganz. Die 1h-Reihe
desselben Tages war vollstaendig. Das Muster wiederholte sich Di-Fr (07.10.,
08.10., 12.10.) von etwa Mitternacht bis in den Nachmittag. Vor Handelsbeginn
fehlte der Vortag am ENDE der Reihe — `prev_luecke` sah dort nichts.
"""
import os
import sys
from datetime import date

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from digest_renderer import _compact_snap  # noqa: E402
from market_data import (  # noqa: E402
    _compute_snapshot,
    _tagesbalken_aus_1h,
    fehlende_werktage,
    repair_missing_daily_bars,
)

HEUTE = date(2026, 10, 13)

# SAP.DE 1h am 2026-10-12 (Diagnose-Lauf, Close je Stunde, Ortszeit)
SAP_H1_1012 = [
    ("09:00", 190.58, 192.94, 0), ("10:00", 192.94, 192.08, 76794),
    ("11:00", 192.12, 192.42, 62013), ("12:00", 192.36, 194.02, 178022),
    ("13:00", 194.08, 193.94, 118959), ("14:00", 193.92, 194.32, 49375),
    ("15:00", 194.34, 194.72, 448431), ("16:00", 194.70, 193.86, 232807),
    ("17:00", 193.86, 194.72, 112630),
]


def _daily(dates, closes):
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    return pd.DataFrame({"Open": closes, "High": [c * 1.01 for c in closes],
                         "Low": [c * 0.99 for c in closes], "Close": closes,
                         "Adj Close": closes, "Volume": [1_000_000.0] * len(closes),
                         "Dividends": 0.0, "Stock Splits": 0.0}, index=idx)


def _hist(ende_tage):
    dates = list(pd.bdate_range("2026-07-01", "2026-10-09").strftime("%Y-%m-%d"))
    closes = [180.0 + i * 0.05 for i in range(len(dates))]
    for d, c in ende_tage:
        dates.append(d)
        closes.append(c)
    return _daily(dates, closes)


def _h1(tag, rows):
    idx = pd.DatetimeIndex([pd.Timestamp(f"{tag} {t}") for t, *_ in rows])
    return pd.DataFrame({
        "Open": [o for _, o, _, _ in rows],
        "High": [max(o, c) + 0.5 for _, o, c, _ in rows],
        "Low": [min(o, c) - 0.5 for _, o, c, _ in rows],
        "Close": [c for _, _, c, _ in rows],
        "Volume": [float(v) for *_, v in rows],
    }, index=idx)


def _batch(per_symbol: dict) -> pd.DataFrame:
    return pd.concat(per_symbol, axis=1, names=["Ticker", "Price"])


class TestFehlendeWerktage:

    def test_luecke_mitten_drin(self):
        df = _hist([("2026-10-13", 194.76)])          # nach Handelsbeginn
        assert fehlende_werktage(df, HEUTE) == [date(2026, 10, 12)]

    def test_luecke_am_ende_vor_handelsbeginn(self):
        df = _hist([])                                 # 08:03: letzter Balken 09.10.
        assert fehlende_werktage(df, HEUTE) == [date(2026, 10, 12)]

    def test_lueckenlos_us_vor_open(self):
        df = _hist([("2026-10-12", 340.97)])
        assert fehlende_werktage(df, HEUTE) == []

    def test_montag_morgens_ist_freitag_da(self):
        df = _hist([])
        assert fehlende_werktage(df, date(2026, 10, 12)) == []

    def test_alte_luecken_bleiben_unberuehrt(self):
        df = _daily(["2026-09-01", "2026-09-02"], [1.0, 1.0])
        # Grenze 13.10. - 7 Tage = 06.10. (exklusiv): nur 07.-12.10. werden versucht
        assert fehlende_werktage(df, HEUTE, max_tage=7) == [date(2026, 10, d) for d in (7, 8, 9, 12)]


class TestTagesbalkenAus1h:

    def test_sap_1012(self):
        b = _tagesbalken_aus_1h(_h1("2026-10-12", SAP_H1_1012), date(2026, 10, 12))
        assert b["Open"] == 190.58
        assert b["Close"] == 194.72          # = yfinance repair=True und letzter 1h-Schluss
        assert b["Volume"] == sum(v for *_, v in SAP_H1_1012)

    def test_teiltag_wird_nicht_eingesetzt(self):
        assert _tagesbalken_aus_1h(_h1("2026-10-12", SAP_H1_1012[:2]), date(2026, 10, 12)) is None

    def test_feiertag_ohne_1h(self):
        assert _tagesbalken_aus_1h(_h1("2026-10-12", SAP_H1_1012), date(2026, 10, 9)) is None


class TestReparatur:

    def test_eu_nach_open_luecke_geschlossen(self):
        dfs = {"SAP.DE": _hist([("2026-10-13", 194.76)]), "AAPL": _hist([("2026-10-12", 340.97)])}
        calls = []

        def dl(syms):
            calls.append(list(syms))
            return _batch({"SAP.DE": _h1("2026-10-12", SAP_H1_1012)})

        out = repair_missing_daily_bars(dfs, HEUTE, dl)
        assert calls == [["SAP.DE"]]                   # nur betroffene Ticker
        assert out == {"SAP.DE": ["2026-10-12"]}
        s = _compute_snapshot("SAP.DE", dfs["SAP.DE"])
        assert s.prev_bar_date == "2026-10-12" and s.prev_luecke is False
        assert s.prev_close == 194.72
        assert round(s.change_pct, 3) == round((194.76 / 194.72 - 1) * 100, 3)

    def test_vor_open_letzter_balken_ist_vortag(self):
        dfs = {"SAP.DE": _hist([])}
        repair_missing_daily_bars(dfs, HEUTE, lambda syms: _batch({"SAP.DE": _h1("2026-10-12", SAP_H1_1012)}))
        s = _compute_snapshot("SAP.DE", dfs["SAP.DE"])
        assert s.last_bar_date == "2026-10-12" and s.price == 194.72

    def test_ohne_luecke_kein_download(self):
        dfs = {"AAPL": _hist([("2026-10-12", 340.97)])}

        def dl(_):
            raise AssertionError("kein Call erwartet")

        assert repair_missing_daily_bars(dfs, HEUTE, dl) == {}

    def test_fx_zeile_fehlt_ganz(self):
        fx = [(f"{h:02d}:00", 1.12, 1.12 - h * 0.0002, 0) for h in range(24)]
        dfs = {"EURUSD=X": _hist([("2026-10-13", 1.1193)])}
        out = repair_missing_daily_bars(dfs, HEUTE, lambda s: _batch({"EURUSD=X": _h1("2026-10-12", fx)}))
        assert out == {"EURUSD=X": ["2026-10-12"]}
        assert dfs["EURUSD=X"].loc["2026-10-12", "Close"] == fx[-1][2]

    def test_1h_leer_luecke_bleibt_und_wird_geflaggt(self):
        dfs = {"SAP.DE": _hist([("2026-10-13", 194.76)])}
        out = repair_missing_daily_bars(dfs, HEUTE, lambda s: _batch({"SAP.DE": _h1("2026-10-12", [])}))
        assert out == {}
        s = _compute_snapshot("SAP.DE", dfs["SAP.DE"])
        assert s.prev_luecke is True and s.change_pct is None

    def test_digest_markiert_rekonstruktion(self):
        dfs = {"SAP.DE": _hist([("2026-10-13", 194.76)])}
        out = repair_missing_daily_bars(dfs, HEUTE, lambda s: _batch({"SAP.DE": _h1("2026-10-12", SAP_H1_1012)}))
        s = _compute_snapshot("SAP.DE", dfs["SAP.DE"])
        s.rekonstruiert = tuple(out["SAP.DE"])
        d = _compact_snap(s)
        assert d["rekonstruiert"] == ["2026-10-12"] and "prev_luecke" not in d
