"""Score-Kalibrierung L12/L23 (2026-10-09): Baender, Wilson, Spearman, Sizing-Gegenrechnung."""
from __future__ import annotations

import score_kalibrierung as sk


def _csv(tmp_path, rows):
    p = tmp_path / "trade_audit.csv"
    head = "TradeID,Symbol,Richtung,Kauf,Verkauf,EntryU,SL_U,R,Einstiegsart,Score,Sizing_Pct,Score_Quelle\n"
    p.write_text(head + "".join(rows), encoding="utf-8")
    return p


def test_baender_und_gegenrechnung(tmp_path):
    p = _csv(tmp_path, [
        "D-1,A,Long,2026-01-01,2026-01-05,10,9,-1.0,Markt,5.0,1.0,Entry\n",
        "D-2,B,Long,2026-01-01,2026-01-05,10,9,2.0,Markt,6.0,2.0,Entry\n",
        "D-3,C,Long,2026-01-01,2026-01-05,10,9,3.0,Markt,6.5,3.0,Entry\n",
        "D-4,D,Long,2026-01-01,,10,9,,Markt,6.5,3.0,Entry\n",           # offen -> zaehlt nicht
        "D-5,E,Long,2026-01-01,2026-01-05,10,9,-1.0,Markt,,1.0,\n",      # ohne Score
    ])
    res = sk.auswerten(sk.lade(p, None))
    assert res["trades"] == 4 and res["gescort"] == 3 and not res["urteil_moeglich"]
    b = {x["band"]: x for x in res["baender"]}
    assert b["5,0-5,5 (1 %)"]["n"] == 1 and b[">= 6,5 (3 %)"]["treffer"] == 1
    assert res["summe_flat_r"] == 4.0
    assert res["summe_score_sizing_r"] == -1.0 + 2 * 2.0 + 3 * 3.0
    assert res["spearman"] is not None and res["spearman"] > 0.9
    txt = sk.render(res, "2026-10-09")
    assert "Kein Urteil (L28)" in txt and "Spearman" in txt


def test_wilson_bekannte_werte():
    lo, hi = sk.wilson(5, 20)
    assert round(lo * 100, 1) == 11.2 and round(hi * 100, 1) == 46.9


def test_alte_csv_ohne_score_spalten(tmp_path):
    p = tmp_path / "trade_audit.csv"
    p.write_text("TradeID,Symbol,Richtung,Kauf,Verkauf,EntryU,SL_U,R,Einstiegsart\n"
                 "D-1,A,Long,2026-01-01,2026-01-05,10,9,-1.0,Markt\n", encoding="utf-8")
    res = sk.auswerten(sk.lade(p, None))
    assert res["gescort"] == 0 and res["trades"] == 1
