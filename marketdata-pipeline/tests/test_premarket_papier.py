"""Papier-Spur Premarket-Limit (2026-11-04): Rechenweg offline gegen synthetische 5m-Kerzen."""
from datetime import date, datetime

import pandas as pd
import pytest

import premarket_papier as pp

TAG = date(2026, 11, 4)


def _kerzen(rows):
    """rows: (HH:MM NY, open, high, low, close) -> DataFrame mit tz-aware Index (NY)."""
    idx = [pd.Timestamp(datetime.combine(TAG, datetime.strptime(t, "%H:%M").time()), tz=pp.NY) for t, *_ in rows]
    return pd.DataFrame([{"Open": o, "High": h, "Low": l, "Close": c} for _, o, h, l, c in rows], index=idx)


PM = [("07:00", 178, 180, 177, 179), ("08:00", 179, 180, 176, 177), ("09:20", 177, 178, 176.5, 177)]


def test_fill_und_ziel_a():
    rth = [("09:30", 179, 179.5, 175.8, 176.5), ("09:35", 176.5, 181, 176.4, 180.5), ("15:55", 185, 188, 184, 187.8)]
    f = pp.bewerte(TAG, "ANET", 164.14, 8.77, _kerzen(PM + rth), "AMC", 5.0)
    assert f.Fill == "ja" and f.Entry == 176.0          # Limit = PM-Tief 176
    assert f.SL == pytest.approx(min(176 - 1.5 * 8.77, 164.14 - 0.3 * 8.77), abs=1e-3)
    assert f.Ergebnis_A == "Ziel" and f.Ziel_A == 180
    assert f.R_A == pytest.approx((180 - 176) / (176 - f.SL), abs=0.01)
    assert f.R_Schluss == pytest.approx((187.8 - 176) / (176 - f.SL), abs=0.01)
    assert f.Gap_ATR == pytest.approx((177 - 164.14) / 8.77, abs=0.01)


def test_fill_und_stop_vor_ziel_in_derselben_kerze():
    rth = [("09:30", 177, 177, 175.9, 176.2), ("09:40", 176, 190, 150, 160), ("15:55", 160, 161, 159, 160)]
    f = pp.bewerte(TAG, "X", 164.14, 8.77, _kerzen(PM + rth), "AMC", 5.0)
    assert f.Fill == "ja" and f.Ergebnis_A == "Stop" and f.R_A == pytest.approx(-1.0, abs=0.01)
    assert f.R_Schluss == pytest.approx(-1.0, abs=0.01) and f.Hinweis == "Stop vor Schluss"


def test_kein_fill_nach_1000_und_markt_spur():
    rth = [("09:30", 179, 182, 177.5, 181), ("10:05", 181, 181, 170, 172), ("15:55", 183, 184, 182, 183)]
    f = pp.bewerte(TAG, "X", 164.14, 8.77, _kerzen(PM + rth), "AMC", 5.0)
    assert f.Fill == "nein" and f.Entry is None and f.Hinweis == "Limit nicht erreicht"
    sl = min(179 - 1.5 * 8.77, 164.14 - 0.3 * 8.77)
    assert f.R_Markt_Schluss == pytest.approx((183 - 179) / (179 - sl), abs=0.01)


def test_gap_open_unter_limit_fuellt_zum_open():
    rth = [("09:30", 175, 177, 174, 176), ("15:55", 178, 179, 177, 178)]
    f = pp.bewerte(TAG, "X", 164.14, 8.77, _kerzen(PM + rth))
    assert f.Entry == 175.0


def test_luecke_zu_klein_kein_fall():
    assert pp.bewerte(TAG, "X", 175.0, 8.77, _kerzen(PM + [("09:30", 177, 178, 176, 177)])) is None


def test_kandidaten_amc_bmo_und_nur_us():
    dg = {"universe": {"ANET": {"earn_last": "2026-11-03"}, "AMGN": {"earn_last": "2026-11-04"},
                       "SAP.DE": {"earn_last": "2026-11-03"}, "MSFT": {"earn_last": "2026-10-28"}}}
    assert pp.kandidaten(dg, TAG, date(2026, 11, 3)) == [("AMGN", "BMO"), ("ANET", "AMC")]


def test_atr_wilder_und_csv_upsert(tmp_path):
    d = pd.DataFrame({"High": [11] * 20, "Low": [9] * 20, "Close": [10] * 20})
    assert pp.atr_wilder(d) == pytest.approx(2.0)
    f = pp.Fall(Datum="2026-11-04", Symbol="ANET", Fill="ja", R_A=0.3)
    p = tmp_path / "pm.csv"
    assert pp.upsert_csv(p, [f]) == 1
    f.R_A = 0.5
    assert pp.upsert_csv(p, [f, pp.Fall(Datum="2026-11-04", Symbol="AMGN")]) == 2
    assert "Ø R" in pp.zusammenfassung(p)


def test_lauf_mit_fakes_filtert_eps():
    dg = {"universe": {"ANET": {"earn_last": "2026-11-03"}, "BAD": {"earn_last": "2026-11-03"}}}
    tage_idx = pd.to_datetime(["2026-10-%02d" % i for i in range(1, 31) if date(2026, 10, i).weekday() < 5]
                              + ["2026-11-02", "2026-11-03", "2026-11-04"])
    daily = pd.DataFrame({"High": 166.0, "Low": 162.0, "Close": 164.14}, index=tage_idx)
    rth = [("09:30", 179, 179.5, 175.8, 176.5), ("15:55", 185, 188, 184, 187.8)]
    faelle, prot = pp.lauf(dg, [TAG], daily_fn=lambda s, t: daily, intra_fn=lambda s: _kerzen(PM + rth),
                           earn_fn=lambda s, t: ("AMC", 5.0) if s == "ANET" else ("AMC", -2.0))
    assert [f.Symbol for f in faelle] == ["ANET"]
    assert any("BAD" in p and "keine guten Zahlen" in p for p in prot)
