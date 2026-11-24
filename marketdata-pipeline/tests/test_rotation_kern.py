"""Kern-Rotation (Neuaufstellung A+, 2026-11-07)."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src import rotation_kern as rk


def _closes(n=300, drifts=None):
    idx = pd.bdate_range("2025-01-01", periods=n)
    drifts = drifts or {"A": 0.002, "B": 0.001, "C": -0.001, "D": 0.0005, "E": -0.002}
    return pd.DataFrame({s: 100 * np.exp(np.cumsum(np.full(n, d))) for s, d in drifts.items()}, index=idx)


def test_scores_und_auswahl_mit_absolutfilter():
    sc = rk.scores(_closes(), [63, 126, 252])
    assert list(sc.sort_values(ascending=False).index[:2]) == ["A", "B"]
    assert rk.auswahl(sc, 4, True) == ["A", "B", "D"]          # C, E negativ -> Cash
    assert rk.auswahl(sc, 4, False) == ["A", "B", "D", "C"]


def test_zu_kurze_historie_ist_nan():
    sc = rk.scores(_closes(n=100), [63, 126, 252])
    assert sc.isna().all()


def test_monatsletzter():
    assert rk.ist_monatsletzter(date(2026, 11, 30))            # Montag, letzter Wochentag
    assert not rk.ist_monatsletzter(date(2026, 11, 27))
    assert rk.ist_monatsletzter(date(2026, 10, 30))            # Freitag, 31. ist Samstag


def test_plan_kauf_verkauf_cash():
    akt = rk.plan(["A", "C"], ["A", "B", "D"], 8000, 4, {"B": {"isin": "X"}})
    by = {(a["aktion"], a["signal"]) for a in akt}
    assert ("verkaufen", "C") in by and ("halten", "A") in by and ("kaufen", "B") in by
    cash = [a for a in akt if a["aktion"] == "cash"][0]
    assert cash["ziel_eur"] == 2000.0
    assert [a for a in akt if a["signal"] == "B"][0]["isin"] == "X"


def test_backtest_waehlt_den_starken_wert():
    r = rk.backtest(_closes(n=600), 1, True, [63, 126, 252], 0.0, start="2025-01-01")
    assert r.sum() > 0


def test_config_ethik_und_isins():
    cfg = yaml.safe_load((Path(__file__).parent.parent / "config" / "rotation_kern.yaml").read_text())
    sig = [u["signal"] for u in cfg["universum"]]
    assert not {"XLI", "EWG"} & set(sig)
    assert len(sig) == len(set(sig)) and all(len(u["isin"]) == 12 for u in cfg["universum"])


def test_thesen_preise_marken():
    from src import thesen_preise as tp
    idx = pd.bdate_range("2025-01-01", periods=300)
    c = pd.Series(np.r_[np.linspace(100, 200, 250), np.linspace(200, 158, 50)], index=idx)
    th = {"thesen": [{"id": "TDIP", "spur": "thesen", "verdikt": "spielen",
                      "karte": {"preis_falsifikat": {"symbol": "XLK", "op": "<", "level": 130},
                                "einstieg": {"symbol": "XLK", "op": "<", "level": 160}}},
                     {"id": "ALT", "spur": "thesen", "verdikt": "verworfen", "karte": {}}]}
    r = tp.pruefe(th, lambda s: c)
    x = r["TDIP"]["XLK"]
    assert x["einstieg"]["erreicht"] and not x["preis_falsifikat"]["erreicht"]
    assert x["hoch_52w"] == 200.0 and x["abstand_hoch_pct"] == -21.0
    assert "ALT" not in r


def test_thesen_preise_klebrig_und_freigabe():
    from src import thesen_preise as tp
    idx = pd.bdate_range("2025-01-01", periods=300)
    tief = pd.Series(np.r_[np.linspace(100, 200, 250), np.linspace(200, 158, 50)], index=idx)
    erholt = tief.copy(); erholt.iloc[-1] = 170.0
    karte = {"preis_falsifikat": {"symbol": "XLK", "op": "<", "level": 130},
             "einstieg": {"symbol": "XLK", "op": "<", "level": 160}}
    th = {"thesen": [{"id": "T", "spur": "thesen", "verdikt": "spielen", "karte": dict(karte)},
                     {"id": "V", "spur": "thesen", "verdikt": "freigabe", "karte": dict(karte)}]}
    r1 = tp.pruefe(th, lambda s: tief)
    tag = r1["T"]["XLK"]["datum"]
    assert r1["T"]["XLK"]["einstieg"]["erstmals"] == tag and "V" in r1
    # Kurs springt zurueck ueber die Marke: erstmals bleibt stehen
    r2 = tp.pruefe(th, lambda s: erholt, r1)
    e = r2["T"]["XLK"]["einstieg"]
    assert not e["erreicht"] and e["erstmals"] == tag
    assert r2["T"]["XLK"]["preis_falsifikat"]["erstmals"] is None
    # Position eingetragen: Einstieg erledigt
    th["thesen"][0]["karte"]["position"] = {"datum": "2026-11-10", "betrag_eur": 800}
    r3 = tp.pruefe(th, lambda s: erholt, r2)
    assert r3["T"]["XLK"]["einstieg"]["erstmals"] is None
    # Level geaendert: alte Ausloesung gilt nicht fuer die neue Marke
    th["thesen"][1]["karte"]["einstieg"] = {"symbol": "XLK", "op": "<", "level": 150}
    r4 = tp.pruefe(th, lambda s: erholt, r2)
    assert r4["V"]["XLK"]["einstieg"]["erstmals"] is None


def _fake_download(fehler_bulk: set, fehler_einzeln: dict):
    """Bulk-Download liefert Symbole aus fehler_bulk nicht; Einzelversuche scheitern
    fehler_einzeln[s]-mal, danach kommen Daten."""
    idx = pd.bdate_range("2025-01-01", periods=300)
    zaehler = {}

    def dl(symbole, **kw):
        if len(symbole) == 1:
            s = symbole[0]
            zaehler[s] = zaehler.get(s, 0) + 1
            if zaehler[s] <= fehler_einzeln.get(s, 0):
                return pd.DataFrame()
            ok = [s]
        else:
            ok = [s for s in symbole if s not in fehler_bulk]
        cols = pd.MultiIndex.from_product([ok, ["Close"]])
        return pd.DataFrame(np.full((len(idx), len(ok)), 100.0), index=idx, columns=cols)
    return dl


def test_lade_holt_fehlende_symbole_einzeln_nach():
    dl = _fake_download({"XLB"}, {"XLB": 1})
    closes = rk._lade(["XLV", "XLB", "XLF"], download=dl, pause_s=0)
    assert set(closes.columns) == {"XLV", "XLB", "XLF"}
    assert rk.fehlende_daten(closes, ["XLV", "XLB", "XLF"]) == []


def test_lade_meldet_dauerhaft_fehlende():
    dl = _fake_download({"XLB"}, {"XLB": 99})
    closes = rk._lade(["XLV", "XLB", "XLF"], download=dl, pause_s=0)
    assert rk.fehlende_daten(closes, ["XLV", "XLB", "XLF"]) == ["XLB"]


def test_kein_signal_bei_fehlenden_daten(tmp_path, monkeypatch):
    closes = _closes(drifts={"XLV": 0.002, "XLF": 0.001})
    monkeypatch.setattr(rk, "_lade", lambda syms, **kw: closes)
    st = tmp_path / "rotation_kern.json"
    st.write_text('{"bestand": ["XLV", "XLB"], "historie": []}', encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(yaml.safe_dump({"top_n": 2, "absolutfilter": True, "lookbacks_ht": [63, 126, 252],
                                   "kapital_eur": 4000, "kosten_je_seite": 0.001,
                                   "universum": [{"signal": s, "name": s, "isin": "X"} for s in ("XLV", "XLF", "XLB")]}),
                   encoding="utf-8")
    assert rk.main(["--cfg", str(cfg), "--state-dir", str(tmp_path), "--force"]) == 1
    assert '"bestand": ["XLV", "XLB"]' in st.read_text(encoding="utf-8")   # unveraendert
    assert rk.main(["--cfg", str(cfg), "--state-dir", str(tmp_path)]) in (0, 1)
