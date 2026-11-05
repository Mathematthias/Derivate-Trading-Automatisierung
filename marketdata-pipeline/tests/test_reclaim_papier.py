"""Papierspur Reclaim EMA200 (v84) — ohne Netz."""
import numpy as np
import pandas as pd

import reclaim_papier as rp
import state_yaml


def _tage(n=260, start=100.0):
    idx = pd.bdate_range("2025-11-03", periods=n)
    c = np.linspace(start, start * 1.3, n)
    # letzter Abschnitt faellt an die EMA200 und dreht
    c[-16:-6] = np.linspace(c[-17], c[-17] * 0.93, 10)
    c[-6:] = np.linspace(c[-7], c[-7] * 1.03, 6)
    df = pd.DataFrame({"Close": c}, index=idx)
    df["Open"] = df["Close"].shift(1).fillna(df["Close"])
    df["High"] = df[["Open", "Close"]].max(axis=1) * 1.01
    df["Low"] = df[["Open", "Close"]].min(axis=1) * 0.99
    return df[["Open", "High", "Low", "Close"]]


def _stunden(tag, muster):
    zeiten = pd.date_range(f"{tag} 09:00", periods=len(muster), freq="h")
    z = pd.DataFrame(muster, columns=["Open", "High", "Low", "Close"], index=zeiten)
    z["Volume"] = 100
    return z


def test_kandidat_und_plan_l25():
    d1 = _tage()
    tage = rp.kandidaten_tage(d1)
    assert tage, "Touch und Schluss ueber EMA200 muessen einen Kandidaten liefern"
    ts = tage[-1]
    p = rp.plan(d1, ts, float(d1.loc[ts, "Close"]))
    assert abs(p["SL"] - min(p["Entry"] - 1.5 * p["ATR"], p["TIW"] - 0.30 * p["ATR"])) < 0.001
    assert p["TIW"] < p["EMA200"]
    assert p["Stack"] in ("bullish", "neutral", "bearish")


def test_reststueck_ist_kein_block():
    vor = [[100, 100.5, 98, 98.5]] * 4 + [[98.5, 99, 96, 96.5]] * 4
    tag = [[96.5, 97, 96, 96.2]] * 8 + [[96.2, 96.3, 95.5, 96.25]]   # Stunde 9 faellt allein in einen Block
    h1 = pd.concat([_stunden("2026-09-17", vor), _stunden("2026-09-18", tag)])
    assert rp.umkehr_block(h1, pd.Timestamp("2026-09-18").date()) is None


def test_echter_block_wird_erkannt():
    vor = [[100, 100.5, 98, 98.5]] * 4 + [[98.5, 99, 96, 96.5]] * 4
    tag = [[96.5, 96.6, 90, 96.0], [96.0, 96.5, 95.9, 96.4], [96.4, 96.6, 96.2, 96.5], [96.5, 96.7, 96.3, 96.6]]
    h1 = pd.concat([_stunden("2026-09-17", vor), _stunden("2026-09-18", tag)])
    u = rp.umkehr_block(h1, pd.Timestamp("2026-09-18").date())
    assert u is not None and "Hammer" in u[1]


def _weg(werte):
    idx = pd.bdate_range("2026-09-21", periods=len(werte))
    return pd.DataFrame(werte, columns=["Open", "High", "Low", "Close"], index=idx)


ROW = {"Datum": "2026-09-18", "Entry": 100, "SL": 95, "R": 5, "TP1": 110}


def test_stop_gewinnt_am_selben_tag():
    a = rp.ausgang(ROW, _weg([[100, 111, 94, 105]]))
    assert a["Exit_Grund"] == "Stop" and a["Ergebnis_R"] == -1.0 and a["TP1_Hit"] == "nein"


def test_gap_unter_stop_zaehlt_eroeffnung():
    a = rp.ausgang(ROW, _weg([[92, 93, 91, 92]]))
    assert a["Exit"] == 92 and a["Ergebnis_R"] == -1.6


def test_zeitstopp_nach_20_tagen():
    a = rp.ausgang(ROW, _weg([[101, 112, 100, 108]] * 25))
    assert a["Exit_Grund"] == "Zeit" and a["Ergebnis_R"] == 1.6 and a["TP1_Hit"] == "ja"


def test_offen_bleibt_offen():
    a = rp.ausgang(ROW, _weg([[101, 102, 100, 101]] * 3))
    assert a["Status"] == "offen" and "Ergebnis_R" not in a


def test_sperre_je_symbol(monkeypatch):
    rows = [{"Datum": "2026-09-18", "Symbol": "X", "Status": "offen"}]
    d1 = _tage()
    monkeypatch.setattr(rp, "kandidaten_tage", lambda _: [pd.Timestamp("2026-09-22")])
    monkeypatch.setattr(rp, "umkehr_block", lambda *_: (100.0, "Hammer"))
    assert rp.scan(rows, ["X"], lambda s: d1, lambda s: d1) == 0


def test_render_nennt_schwelle():
    rows = [{"Status": "geschlossen", "Ergebnis_R": "1.5", "Stack": "neutral", "TP1_ok": "nein", "TP1_Hit": "ja"}
            for _ in range(20)]
    t = rp.render(rows)
    assert "n >= 20" in t and "Stack neutral" in t and "TP1 unter 1,3 R" in t


def _state():
    return {"watchlist": {"entries": [
        {"symbol": "ABC", "status": "archiviert", "trade_nr": "7", "legs": [{"label": "A", "text": "ARCHIVIERT."}]},
        {"symbol": "XYZ", "status": "archiviert", "trade_nr": "8", "legs": [{"label": "A", "text": "RE-EVAL: 1D-Schluss >9"}]},
        {"symbol": "VET", "status": "archiviert", "trade_nr": "9", "notes": "Kein Re-Eval (User)",
         "legs": [{"label": "A", "text": "ARCHIVIERT."}]},
    ]}, "radar": {}, "thesen": {}}


def test_reeval_auto_setzt_lesbare_bedingung():
    s = _state()
    state_yaml.apply_actions(s, [{"op": "watchlist.reeval_auto", "symbol": "ABC", "trade_nr": 7,
                                  "reeval_op": ">", "reeval_level": 136.0, "reeval_note": "Auto nach Exit"}])
    t = s["watchlist"]["entries"][0]["legs"][0]["text"]
    assert state_yaml._leg_reeval(t) == {"op": ">", "level": 136.0}


def test_reeval_auto_respektiert_bestand_und_veto():
    s = _state()
    log = state_yaml.apply_actions(s, [
        {"op": "watchlist.reeval_auto", "symbol": "XYZ", "trade_nr": "8", "reeval_op": ">", "reeval_level": 1},
        {"op": "watchlist.reeval_auto", "symbol": "VET", "trade_nr": "9", "reeval_op": ">", "reeval_level": 1},
    ])
    assert all("uebersprungen" in z for z in log)
    assert s["watchlist"]["entries"][1]["legs"][0]["text"] == "RE-EVAL: 1D-Schluss >9"
