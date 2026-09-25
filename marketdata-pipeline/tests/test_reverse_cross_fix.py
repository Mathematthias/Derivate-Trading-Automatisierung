"""Regression 2026-09-25: Engulfing ohne Farbpruefung + RSI-Cross als Zustand.

Anlass: Im Digest 2026-09-25 16:02 trugen 9 von 150 Werten gleichzeitig
reverse_bullish=True und reverse_bearish=True, jedes Mal mit der Begruendung
"Bullish-Engulfing; Shooting-Star (Wick x %, Close-Pos y %)". BIIB wurde im
Morning-Check daraufhin als 4h-bestaetigter Long gelesen — die Kerze war ein
Shooting Star am Hoch.

Die Kerzen unten sind aus den Wick-/Close-Pos-Werten der Digest-Begruendungen
REKONSTRUIERT (gruener Mini-Koerper, Close ueber dem Open der roten Vorkerze). Rohe
OHLC-Werte der Faelle liegen nicht vor.
"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from intraday_4h import compute_4h, detect_reverse, rsi_cross_state
from digest_renderer import _compact_snap  # noqa: F401  (Importpruefung)


def _c(rows):
    return pd.DataFrame(rows, index=pd.DatetimeIndex(
        [pd.Timestamp("2026-09-24 09:30") + timedelta(hours=4 * i)
         for i in range(len(rows))]))


def _star_nach_roter_vorkerze(upper_wick, close_pos, rng=4.0, low=224.0):
    """Mini-Koerper am unteren Rand, lange obere Wick, Close ueber dem Open
    einer roten Vorkerze. Wick + Close-Pos = 100 % in allen fuenf Digest-
    Faellen heisst: Close ist die KOERPEROBERKANTE -> gruener Mini-Koerper
    (bzw. Doji)."""
    c = low + close_pos * rng
    h = low + rng
    o = c - 0.02 * rng                  # gruener Mini-Koerper
    po = c - 0.3                        # rote Vorkerze, Open UNTER dem Close
    prev = {"Open": po, "High": po + 0.2, "Low": po - 2.0, "Close": po - 1.5}
    cur = {"Open": o, "High": h, "Low": low, "Close": c}
    return _c([prev, cur])


# Werte aus reverse_reason im Digest 2026-09-25 16:02
FAELLE = [
    ("BIIB", 0.74, 0.26), ("GIVN.SW", 0.70, 0.30), ("TLX.DE", 0.89, 0.11),
    ("NG.L", 0.88, 0.12), ("SIX2.DE", 0.70, 0.30),
]


class TestEngulfingFarbe:
    @pytest.mark.parametrize("sym,wick,cpos", FAELLE)
    def test_star_ist_nicht_mehr_bullish(self, sym, wick, cpos):
        bull, bear, why = detect_reverse(_star_nach_roter_vorkerze(wick, cpos))
        assert bull is False, f"{sym}: Star-Kerze darf nicht bullisch sein"
        assert bear is True and "Shooting-Star" in why
        assert "Bullish-Engulfing" not in why

    def test_alte_logik_haette_beides_gemeldet(self):
        """Dokumentiert den Fehler: die Vorbedingung der alten Formel ist erfuellt."""
        df = _star_nach_roter_vorkerze(0.74, 0.26)
        po, pc = df["Open"].iloc[-2], df["Close"].iloc[-2]
        c = df["Close"].iloc[-1]
        assert pc < po and c > po            # alte bull_eng-Bedingung = True

    def test_rote_kerze_ist_nie_bullish_engulfing(self):
        df = _c([
            {"Open": 100, "High": 100.5, "Low": 97, "Close": 97.5},    # rot
            {"Open": 102, "High": 102.2, "Low": 100.4, "Close": 100.6},  # rot, > prev Open
        ])
        bull, bear, why = detect_reverse(df)
        assert bull is False
        assert why is None or "Bullish-Engulfing" not in why

    def test_gruene_kerze_ist_nie_bearish_engulfing(self):
        df = _c([
            {"Open": 98, "High": 101, "Low": 97.5, "Close": 100.5},    # gruen
            {"Open": 96.0, "High": 97.8, "Low": 95.8, "Close": 97.6},   # gruen, < prev Open
        ])
        bull, bear, why = detect_reverse(df)
        assert bear is False
        assert why is None or "Bearish-Engulfing" not in why

    def test_echtes_bullish_engulfing_bleibt(self):
        df = _c([
            {"Open": 100, "High": 100.5, "Low": 97, "Close": 97.5},
            {"Open": 97.4, "High": 101.2, "Low": 97.2, "Close": 101.0},
        ])
        bull, bear, why = detect_reverse(df)
        assert bull is True and bear is False and "Bullish-Engulfing" in why

    def test_widerspruch_ergibt_kein_signal(self):
        """Gruener Koerper umschliesst einen winzigen roten Vorkoerper, sitzt
        aber unten in einer Kerze mit langer oberer Wick: Bullish-Engulfing
        UND Shooting-Star zugleich -> beide False."""
        df = _c([
            {"Open": 100.2, "High": 100.4, "Low": 99.9, "Close": 100.0},  # rot, winzig
            {"Open": 99.9, "High": 103.0, "Low": 99.5, "Close": 100.3},   # gruen
        ])
        bull, bear, why = detect_reverse(df)
        assert (bull, bear) == (False, False)
        assert why.startswith("Widerspruch")

    def test_nie_beide_flags(self):
        rng = np.random.default_rng(7)
        for _ in range(2000):
            o1, c1, o2, c2 = rng.uniform(95, 105, 4)
            h1, l1 = max(o1, c1) + rng.uniform(0, 3), min(o1, c1) - rng.uniform(0, 3)
            h2, l2 = max(o2, c2) + rng.uniform(0, 3), min(o2, c2) - rng.uniform(0, 3)
            df = _c([{"Open": o1, "High": h1, "Low": l1, "Close": c1},
                     {"Open": o2, "High": h2, "Low": l2, "Close": c2}])
            bull, bear, _ = detect_reverse(df)
            assert not (bull and bear)


class TestRsiCrossState:
    def test_frischer_cross_nach_oben(self):
        rsi = pd.Series([40, 42, 45, 52])
        sig = pd.Series([48, 48, 48, 48])
        assert rsi_cross_state(rsi, sig) == ("above", 0)

    def test_alter_cross_wird_gezaehlt(self):
        rsi = pd.Series([40, 52, 55, 58, 60, 61])
        sig = pd.Series([48] * 6)
        assert rsi_cross_state(rsi, sig) == ("above", 4)

    def test_cross_nach_unten(self):
        rsi = pd.Series([60, 58, 50, 45])
        sig = pd.Series([52, 52, 52, 52])
        assert rsi_cross_state(rsi, sig) == ("below", 1)

    def test_kein_wechsel(self):
        assert rsi_cross_state(pd.Series([55, 56, 57]), pd.Series([50, 50, 50])) == (None, None)

    def test_nan_und_gleichstand_werden_uebersprungen(self):
        rsi = pd.Series([np.nan, 45, 50, 53])
        sig = pd.Series([np.nan, 48, 50, 48])
        assert rsi_cross_state(rsi, sig) == ("above", 0)

    def test_fehlende_daten(self):
        assert rsi_cross_state(None, None) == (None, None)

    def test_compute_4h_liefert_cross_felder(self):
        idx = pd.date_range("2026-08-03 09:00", periods=60 * 9, freq="h")
        idx = idx[(idx.hour >= 9) & (idx.hour < 18) & (idx.dayofweek < 5)]
        n = len(idx)
        base = 100 + np.sin(np.arange(n) / 15.0) * 5
        df = pd.DataFrame({"Open": base, "High": base + 0.5,
                           "Low": base - 0.5, "Close": base + 0.1}, index=idx)
        ind = compute_4h(df)
        assert ind.rsi_cross_dir in ("above", "below")
        assert isinstance(ind.rsi_cross_bars_ago, int) and ind.rsi_cross_bars_ago >= 0
        d = ind.as_dict()
        assert "rsi_cross_dir" in d and "rsi_cross_bars_ago" in d
