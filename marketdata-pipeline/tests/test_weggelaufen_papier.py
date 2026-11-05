"""Papier-Spur „bestaetigt, aber weggelaufen“ (User-Entscheid B, 2026-11-05) — offline mit synthetischen Kerzen."""
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import weggelaufen_papier as wp

NY = "America/New_York"
TEXT = ("nach 2026-11-02 TREND-PULLBACK-LONG: Touch EMA20-1D -0,30/+0,50 ATR [pullback] + 4h-Bullish-Reverse-Close (MANUELL). "
        "Einstieg Live nach Schluss der 4h-Bestaetigungskerze, ueber 666,00$ kein Entry (TP1 < 1,3 R). "
        "SL = MIN(Entry-1,5xATR ; TIW-0,30xATR). TIW = 1D-Schluss unter EMA50-1D -0,30 ATR. "
        "TP1 721,22$ [stark: Woche, 52W] 1/3 raus.")
TAG = date(2026, 11, 4)


def _daily(signal_low=645.0, signal_high=676.0):
    days = pd.bdate_range(end=TAG - timedelta(days=1), periods=80)
    d = pd.DataFrame({"Open": 650.0, "High": 660.0, "Low": 640.0, "Close": 650.0}, index=days)
    d.loc[pd.Timestamp(TAG)] = [662.0, signal_high, signal_low, 675.0]
    return d


def _h1(rows):
    idx = [pd.Timestamp(datetime.combine(t, datetime.strptime(h, "%H:%M").time()), tz=NY) for t, h, *_ in rows]
    return pd.DataFrame([{"Open": o, "High": hi, "Low": lo, "Close": c} for *_, o, hi, lo, c in rows], index=idx)


def _signal_tag_bars():
    vortag = TAG - timedelta(days=1)
    rows = [(vortag, f"{h:02d}:30", 650, 655, 648, 652) for h in range(9, 16)]
    rows += [(TAG, "09:30", 662, 663, 655, 656), (TAG, "10:30", 656, 657, 650, 651),
             (TAG, "11:30", 651, 652, 646, 647), (TAG, "12:30", 647, 648, 645, 646),
             (TAG, "13:30", 646, 660, 645.5, 659), (TAG, "14:30", 659, 670, 658, 669), (TAG, "15:30", 669, 676, 668, 675)]
    return rows


def _zeile():
    return wp.Zeile("DE", True, "trend_pullback", TEXT, date(2026, 11, 2))


def test_signal_weggelaufen_mit_l25_und_grenze():
    f = wp.finde_signal(_zeile(), TAG, _daily(), _h1(_signal_tag_bars()))
    assert f is not None and f.Art == "weggelaufen"
    assert f.Entry == 675 and f.Zone_OG == pytest.approx(650 + 0.5 * f.ATR, abs=0.01)
    assert f.Abstand_Zone_ATR > 0 and f.Hinter_Grenze == "ja" and f.Grenze == 666.0
    tiw = 650 - 0.3 * f.ATR
    assert f.SL == pytest.approx(min(675 - 1.5 * f.ATR, tiw - 0.3 * f.ATR), abs=0.01)
    assert f.RR_TP1 == pytest.approx((721.22 - 675) / (675 - f.SL), abs=0.01)


def test_bestaetigung_in_der_zone_ist_kein_fall():
    rows = _signal_tag_bars()[:-2] + [(TAG, "14:30", 659, 659.5, 657, 658.0)]
    assert wp.finde_signal(_zeile(), TAG, _daily(), _h1(rows)) is None


def test_ohne_touch_kein_fall():
    assert wp.finde_signal(_zeile(), TAG, _daily(signal_low=665.0), _h1(_signal_tag_bars())) is None


def test_verfolgung_tp1_und_zone_spaeter():
    f = wp.finde_signal(_zeile(), TAG, _daily(), _h1(_signal_tag_bars()))
    nach = [(TAG + timedelta(days=1), "09:30", 675, 676, 655, 660),     # zurueck in die Zone
            (TAG + timedelta(days=1), "10:30", 660, 700, 659, 699),
            (TAG + timedelta(days=4), "09:30", 699, 722, 698, 721)]   # TP1
    h = _h1(_signal_tag_bars() + nach)
    wp.verfolge(f, h, TAG + timedelta(days=4))
    assert f.Status == "zu" and f.Ergebnis == "TP1" and f.R == f.RR_TP1
    assert f.Zone_spaeter == (TAG + timedelta(days=1)).isoformat() and f.R_ab_Zone is not None
    assert f.MAE_R > 0


def test_verfolgung_stop_zuerst():
    f = wp.finde_signal(_zeile(), TAG, _daily(), _h1(_signal_tag_bars()))
    nach = [(TAG + timedelta(days=1), "09:30", 675, 730, 600, 610)]
    wp.verfolge(f, _h1(_signal_tag_bars() + nach), TAG + timedelta(days=1))
    assert f.Ergebnis == "Stop" and f.R == -1.0


def test_ohne_touch_race_fall():
    z = wp.Zeile("RACE.MI", True, "breakout_retest",
                  "BREAKOUT-RETEST-LONG: Touch 354,85-359,96€ [pullback]. TIW = 1D-Schluss unter 359,35€. TP1 377,50€ [stark: Woche, 52W].",
                  TAG)
    d = _daily()
    d.loc[pd.Timestamp(TAG)] = [369, 375, 364, 368]
    d.loc[pd.Timestamp(TAG + timedelta(days=1))] = [369, 381, 368, 380]
    f = wp.ohne_touch(z, d)
    assert f is not None and f.Art == "ohne Touch" and f.Zone_UG == 354.85


def test_csv_roundtrip(tmp_path):
    f = wp.finde_signal(_zeile(), TAG, _daily(), _h1(_signal_tag_bars()))
    p = tmp_path / "w.csv"
    rows = wp.upsert(p, [f])
    g = wp._fall_aus_row(rows[0])
    assert g.Entry == f.Entry and g.Status == "offen"
    assert "weggelaufen" in wp.zusammenfassung(rows)


def test_lauf_ein_offener_trade_je_zeile_und_nicht_vor_anlage(tmp_path, monkeypatch):
    z = wp.Zeile("DE", True, "trend_pullback", TEXT, TAG)
    monkeypatch.setattr(wp, "zeilen_aus_state", lambda d: [z])
    rows2 = _signal_tag_bars() + [(r[0] + timedelta(days=1), *r[1:]) for r in _signal_tag_bars() if r[0] == TAG]
    d = _daily()
    d.loc[pd.Timestamp(TAG + timedelta(days=1))] = [662.0, 676.0, 645.0, 675.0]
    faelle, _ = wp.lauf(str(tmp_path), [TAG - timedelta(days=1), TAG, TAG + timedelta(days=1)],
                        daily_fn=lambda s: d, h1_fn=lambda s: _h1(rows2), csv_path=tmp_path / "w.csv")
    w = [f for f in faelle if f.Art == "weggelaufen"]
    assert [f.Signal_Datum for f in w] == [TAG.isoformat()]


def test_ohne_touch_nicht_wenn_kurs_bei_anlage_schon_ueber_tp1():
    z = wp.Zeile("SMIN.L", True, "trend_pullback", "Touch 25,51-25,94 [pullback]. TIW = 1D-Schluss unter 25,42. TP1 26,98 [stark: Mehrfach].", TAG)
    d = _daily()
    d.loc[pd.Timestamp(TAG)] = [27.0, 27.3, 26.9, 27.16]
    assert wp.ohne_touch(z, d) is None
