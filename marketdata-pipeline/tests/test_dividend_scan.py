"""DIVIDEND-SCAN (2026-10-04) — Filter, Flags, Klumpen-Bremse, Universum."""
from __future__ import annotations

import datetime as dt
import json

import pytest

import dividend_scan as ds
from market_data import TickerSnapshot

HEUTE = dt.date(2026, 10, 3)


def snap(sym, price=30.0, ema20=29.5, ema50=29.0, ema200=25.0, atr=0.9,
         y=6.3, cnt=4, ttm=None, last=0.90, cad=91, ex_next="2026-12-04",
         ex_src="saisonal", vol=5e6):
    s = TickerSnapshot(symbol=sym, timestamp=dt.datetime(2026, 10, 3),
                       price=price, prev_close=price)
    s.ema20, s.ema50, s.ema200, s.atr14 = ema20, ema50, ema200, atr
    s.div_yield_ttm_pct, s.div_ttm_count = y, cnt
    s.div_ttm = ttm if ttm is not None else (y * price / 100 if y else None)
    s.last_ex_div_amount, s.div_cadence_days = last, cad
    s.next_ex_div_date, s.next_ex_div_source = ex_next, ex_src
    s.volume_eur_avg_20d = vol
    s.distance_from_52w_high_pct = -3.0
    return s


P = dict(ds.DEFAULT_PARAMS)


def test_trend_definition_laesst_pullback_unter_ema20_zu():
    s = snap("A", price=28.8, ema20=29.5, ema50=29.0, ema200=25.0)
    assert ds.trend_intakt(s)               # unter EMA20/50, über EMA200
    assert not ds.trend_intakt(snap("B", price=24.0))          # unter EMA200
    assert not ds.trend_intakt(snap("C", ema50=24.0))           # EMA50 < EMA200


def test_filter_trennt_treffer_und_fallen():
    snaps = {
        "UP": snap("UP"),
        "TRAP": snap("TRAP", price=20.0, ema20=22, ema50=24, ema200=26, y=11.0),
        "LOW": snap("LOW", y=2.0),
        "ILLIQ": snap("ILLIQ", vol=1e5),
        "NODIV": snap("NODIV", y=None, cnt=0),
    }
    res = ds.run_scan(snaps, {}, P, HEUTE)
    assert [r["symbol"] for r in res["treffer"]] == ["UP"]
    assert [r["symbol"] for r in res["ohne_trend"]] == ["TRAP"]
    st = res["stats"]
    assert (st["mit_dividende"], st["rendite_ok"], st["liquide"], st["trend_ok"]) == (4, 3, 2, 1)


def test_sblk_flags_spitze_und_ex_tag():
    # TTM 1,88 auf 29,785 = 6,31 %; letzte 0,90 × 4 = 3,60 → Faktor 1,9.
    s = snap("SBLK", price=29.785, y=6.31, ttm=1.88, last=0.90, cad=91,
             ex_next="2026-10-20")
    r = ds.bewerte(s, {"cluster": "shipping"}, P, HEUTE)
    assert r["fwd_yield"] == round(3.60 / 29.785 * 100, 2)
    assert r["fwd_ttm_ratio"] == round(3.60 / 1.88, 2)
    assert any(f.startswith("Spitze") for f in r["flags"])
    assert any("Ex-Tag in 17 Tagen" in f for f in r["flags"])


def test_kuerzung_wird_geflaggt():
    s = snap("CUT", y=8.0, ttm=2.4, last=0.30, cad=91)   # 1,20 / 2,40 = 0,5
    r = ds.bewerte(s, {}, P, HEUTE)
    assert any(f.startswith("gekürzt") for f in r["flags"])


def test_anker_und_ueberdehnung():
    anker = ds.bewerte(snap("A", price=29.3, ema50=29.0, atr=0.9), {}, P, HEUTE)
    assert any("am Anker" in f for f in anker["flags"])
    weit = ds.bewerte(snap("W", price=33.0, ema20=31.0, atr=0.9), {}, P, HEUTE)
    assert any("überdehnt" in f for f in weit["flags"])


def test_unplausible_rendite_bleibt_aber_mit_flag():
    res = ds.run_scan({"X": snap("X", y=31.0)}, {}, P, HEUTE)
    assert res["treffer"][0]["symbol"] == "X"
    assert any("Daten prüfen" in f for f in res["treffer"][0]["flags"])


def test_klumpen_bremse():
    uni = {f"S{i}": {"name": f"Ship {i}", "cluster": "shipping"} for i in range(5)}
    uni["DTE"] = {"name": "Telekom", "cluster": None}
    snaps = {s: snap(s, y=7.0 + i) for i, s in enumerate(uni)}
    res = ds.run_scan(snaps, uni, P, HEUTE)
    shipping = [r for r in res["treffer"] if r["cluster"] == "shipping"]
    assert len(shipping) == 3
    assert len(res["gekappt"]) == 2
    assert "DTE" in [r["symbol"] for r in res["treffer"]]


def test_ranking_deckelt_die_rendite():
    # 20 % und 13 % zählen beide als 12 % → Nähe zur EMA50 entscheidet.
    snaps = {
        "HOCH": snap("HOCH", y=20.0, price=31.0, ema50=29.0),
        "NAH": snap("NAH", y=13.0, price=29.1, ema50=29.0),
    }
    res = ds.run_scan(snaps, {}, P, HEUTE)
    assert [r["symbol"] for r in res["treffer"]] == ["NAH", "HOCH"]


def test_universum_pool_ergaenzt_und_ethik(tmp_path):
    (tmp_path / "tickers_tier_b.yaml").write_text(
        "categories:\n  dax:\n    Allianz: 'ALV.DE'\n    Rheinmetall: 'RHM.DE'\n",
        encoding="utf-8")
    (tmp_path / "tickers_tier_c.yaml").write_text(
        "categories:\n  ndx:\n    Apple: 'AAPL'\n", encoding="utf-8")
    (tmp_path / "dividend_pool.yaml").write_text(
        "pool:\n  - {symbol: 'ALV.DE', name: 'Allianz', cluster: 'versicherer'}\n"
        "  - {symbol: 'SBLK', name: 'Star Bulk', cluster: 'shipping'}\n",
        encoding="utf-8")
    uni = ds.load_universe(str(tmp_path))
    assert set(uni) == {"ALV.DE", "AAPL", "SBLK"}           # RHM ethik-gesperrt
    assert uni["ALV.DE"]["cluster"] == "versicherer"
    assert uni["ALV.DE"]["quelle"].startswith("tier_b")       # kein Doppel
    assert ds.load_universe(str(tmp_path), nur_pool=True).keys() == {"ALV.DE", "SBLK"}


def test_echte_config_laedt():
    uni = ds.load_universe("./config")
    assert "SBLK" in uni and uni["SBLK"]["cluster"] == "shipping"
    assert "RHM.DE" not in uni
    p = ds.load_params("./config")
    assert p["min_yield_ttm_pct"] == 5.0 and p["max_per_cluster"] == 3


def test_render_md_und_json():
    res = ds.run_scan({"UP": snap("UP")}, {"UP": {"name": "Up AG", "cluster": "x"}},
                      P, HEUTE)
    now = dt.datetime(2026, 10, 3, 6, 15)
    md = ds.render_markdown(res, now)
    assert "DIVIDEND-SCAN" in md and "| UP | Up AG |" in md
    assert "kein Edge" in md
    d = json.loads(ds.render_json(res, now))
    assert d["schema"] == "dividend-scan/v1"
    assert d["treffer"][0]["symbol"] == "UP"
    assert set(d) >= {"generated", "params", "stats", "treffer", "gekappt", "ohne_trend"}


def test_leerer_lauf_ist_gueltig():
    res = ds.run_scan({}, {}, P, HEUTE)
    assert res["treffer"] == [] and "keine" in ds.render_markdown(
        res, dt.datetime(2026, 10, 3))
