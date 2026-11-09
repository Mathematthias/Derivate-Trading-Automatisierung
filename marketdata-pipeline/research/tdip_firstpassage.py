"""Was kommt zuerst: weiter runter oder hoch? Messung 2026-11-09 (User-Frage zu MU und Tech-Werten).

Ereignis je Episode (neu scharf nach Erholung ueber -5 %): erster Schluss, der die Bedingung erfuellt.
Nur Schlusskurse, dividendenbereinigt, keine Kosten. Einzelaktien mit Survivorship-Bias (heutige Gewinner): echte Quoten eher schlechter.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from tdip_schwellen import AKTIEN, ETF_TECH, IDX, dd_von, ereignisse, lade, p, q, tab  # noqa: E402


def vorlauf(c):
    arr = c.to_numpy()
    idm = c.rolling(252, min_periods=60).apply(lambda v: len(v) - 1 - int(np.argmax(v)), raw=True).to_numpy()
    out = np.full(len(arr), np.nan)
    for i, a2 in enumerate(idm):
        if not np.isnan(a2):
            pk = i - int(a2)
            if pk >= 252:
                out[i] = arr[pk] / arr[pk - 252] - 1
    return pd.Series(out, index=c.index)


def erst(c, i, up, dn, n=126):
    for k in range(i + 1, min(i + n + 1, len(c))):
        r = c[k] / c[i] - 1
        if r >= up:
            return "up"
        if r <= dn:
            return "dn"
    return "kein"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/out")
    a = ap.parse_args()
    px = lade()
    for _ in range(3):
        fehlt = [t for t in IDX + AKTIEN if px[t].dropna().shape[0] < 300]
        if not fehlt:
            break
        print("fehlt, neuer Versuch:", fehlt, flush=True)
        time.sleep(30)
        px = lade()
    fehlt = [t for t in IDX + AKTIEN if px[t].dropna().shape[0] < 300]
    if set(fehlt) & {"SPY", "XLK", "SMH"}:
        raise SystemExit(f"Kernwerte fehlen: {fehlt}")
    AKT = [t for t in AKTIEN if t not in fehlt]
    ETFS = [t for t in ETF_TECH if t not in fehlt]
    C = {t: px[t].dropna() for t in IDX + AKTIEN if t not in fehlt}
    DD = {t: dd_von(C[t])[0] for t in C}
    spy = DD["SPY"]
    V = {t: vorlauf(C[t]) for t in AKT}

    min_h = 126

    def ev(tickers, schw, r21, lauf=False, nur_tech=None):
        out = []
        for t in tickers:
            c = C[t]
            bed = (c / c.shift(21) - 1) <= r21
            if lauf:
                bed = bed & (V[t] >= 0.5)
            if nur_tech is not None:
                s = spy.reindex(c.index) > -0.10
                bed = bed & (s if nur_tech else ~s)
            for i in ereignisse(DD[t], schw, bed):
                if i + min_h < len(c):
                    out.append((c.to_numpy(), i, t, c.index[i]))
        return out

    GR = {
        "Aktien −30 %, 21T ≤ −20 %": lambda: ev(AKT, -0.30, -0.20),
        "… nach Lauf ≥ +50 %": lambda: ev(AKT, -0.30, -0.20, lauf=True),
        "… nach Lauf, nur Tech (SPY besser −10 %)": lambda: ev(AKT, -0.30, -0.20, lauf=True, nur_tech=True),
        "… nach Lauf, breit (SPY −10 % oder tiefer)": lambda: ev(AKT, -0.30, -0.20, lauf=True, nur_tech=False),
        "Aktien −40 %, 21T ≤ −25 %, nach Lauf": lambda: ev(AKT, -0.40, -0.25, lauf=True),
        "Tech-ETFs −15 %, 21T ≤ −12 %": lambda: ev(ETFS, -0.15, -0.12),
        "SMH −30 %, 21T ≤ −15 %": lambda: ev(["SMH"], -0.30, -0.15),
    }
    L = ["# Was kommt zuerst: weiter fallen oder steigen? (Messung 2026-11-09)\n",
         f"Daten bis {px.index[-1].date()}, Schlusskurse. Einzelaktien mit Survivorship-Bias: Die 32 Werte sind heutige Gewinner, echte Quoten eher schlechter. "
         "Ereignisse ballen sich in wenigen Krisen, deshalb ist auch die Zahl der Quartale angegeben.\n",
         f"Fehlende Werte im Lauf: {fehlt or 'keine'}.\n"]
    z1, z2, z3 = [], [], []
    PAARE = [(0.15, -0.15), (0.20, -0.20), (0.30, -0.15), (0.30, -0.30), (0.50, -0.25)]
    for nm, f in GR.items():
        e = f()
        if not e:
            continue
        ab2003 = [x for x in e if x[3] >= pd.Timestamp("2003-01-01")]
        for lab, ee in ((nm, e), (nm + " (ab 2003)", ab2003)):
            if not ee:
                continue
            qs = len({f"{d.year}Q{d.quarter}" for _, _, _, d in ee})
            mae = {h: np.array([c[i + 1:i + h + 1].min() / c[i] - 1 for c, i, _, _ in ee]) for h in (20, 60, 126)}
            mfe = {h: np.array([c[i + 1:i + h + 1].max() / c[i] - 1 for c, i, _, _ in ee]) for h in (20, 60, 126)}
            end = np.array([c[i + 126] / c[i] - 1 for c, i, _, _ in ee])
            tief_tag = np.array([int(np.argmin(c[i + 1:i + 127])) + 1 for c, i, _, _ in ee])
            z1.append([lab, len(ee), qs, p(float(np.median(mae[20]))), p(float(np.median(mae[60]))), p(float(np.median(mae[126]))), q(float((mae[126] <= -0.10).mean())), q(float((mae[126] <= -0.20).mean())),
                       q(float((mae[126] <= -0.30).mean())), int(np.median(tief_tag))])
            z2.append([lab, len(ee), p(float(np.median(mfe[20]))), p(float(np.median(mfe[126]))), q(float((mfe[126] >= 0.20).mean())), q(float((mfe[126] >= 0.30).mean())), q(float((mfe[126] >= 0.50).mean())),
                       p(float(np.median(end))), q(float((end > 0).mean()))])
            row = [lab]
            for up, dn in PAARE:
                r = [erst(c, i, up, dn) for c, i, _, _ in ee]
                row.append(f"{q(np.mean([x == 'up' for x in r]))} / {q(np.mean([x == 'dn' for x in r]))}")
            z3.append(row)
    L += ["## Wie viel fiel es danach noch? (ab Einstiegsschluss, 126 Tage)\n",
          tab(["Gruppe", "n", "Quartale", "median Tief 20T", "60T", "126T", "≥ 10 % tiefer", "≥ 20 % tiefer", "≥ 30 % tiefer", "Tag des Tiefs (Median)"], z1), "\n"]
    L += ["## Wie viel stieg es danach? (126 Tage)\n",
          tab(["Gruppe", "n", "median Hoch 20T", "median Hoch 126T", "≥ +20 %", "≥ +30 %", "≥ +50 %", "Rendite nach 126T (Median)", "pos."], z2), "\n"]
    L += ["## Was kam zuerst? (rauf / runter, Rest: keins binnen 126 Tagen)\n",
          tab(["Gruppe"] + [f"+{int(u * 100)} / {int(d * 100)} %" for u, d in PAARE], z3), "\n"]
    # Ein Monat (21 Handelstage)
    min_h = 21
    z4, z5 = [], []
    for nm, f in GR.items():
        e = f()
        for lab, ee in ((nm, e), (nm + " (ab 2003)", [x for x in e if x[3] >= pd.Timestamp("2003-01-01")])):
            if not ee:
                continue
            qs = len({f"{d.year}Q{d.quarter}" for _, _, _, d in ee})
            mae = np.array([c[i + 1:i + 22].min() / c[i] - 1 for c, i, _, _ in ee])
            mfe = np.array([c[i + 1:i + 22].max() / c[i] - 1 for c, i, _, _ in ee])
            end = np.array([c[i + 21] / c[i] - 1 for c, i, _, _ in ee])
            z4.append([lab, len(ee), qs, p(float(np.median(end))), p(float(np.mean(end))), q(float((end > 0).mean())), q(float((end >= 0.10).mean())), q(float((end <= -0.10).mean())),
                       q(float((mae <= -0.05).mean())), q(float((mae <= -0.10).mean())), q(float((mae <= -0.15).mean())), q(float((mae <= -0.20).mean())),
                       q(float((mfe >= 0.05).mean())), q(float((mfe >= 0.10).mean())), q(float((mfe >= 0.15).mean())), q(float((mfe >= 0.20).mean()))])
            row = [lab]
            for up, dn in ((0.05, -0.05), (0.10, -0.10), (0.15, -0.15), (0.20, -0.20)):
                r = [erst(c, i, up, dn, 21) for c, i, _, _ in ee]
                row.append(f"{q(np.mean([x == 'up' for x in r]))} / {q(np.mean([x == 'dn' for x in r]))} / {q(np.mean([x == 'kein' for x in r]))}")
            z5.append(row)
    L += ["## Ein Monat (21 Handelstage)\n",
          tab(["Gruppe", "n", "Quartale", "Median Ende", "Ø Ende", "pos.", "Ende ≥ +10 %", "Ende ≤ −10 %", "Tief ≤ −5 %", "≤ −10 %", "≤ −15 %", "≤ −20 %", "Hoch ≥ +5 %", "≥ +10 %", "≥ +15 %", "≥ +20 %"], z4), "\n",
          "Was kam binnen 21 Tagen zuerst (rauf / runter / keins):\n",
          tab(["Gruppe", "5 %", "10 %", "15 %", "20 %"], z5), "\n"]
    jetzt = []
    for t in AKT + ["SMH", "XLK"]:
        c = C[t]
        r21 = c.iloc[-1] / c.iloc[-22] - 1
        jetzt.append([t, f"{c.iloc[-1]:.2f}", p(DD[t].iloc[-1]), p(r21), "ja" if DD[t].iloc[-1] <= -0.30 and r21 <= -0.20 else ""])
    L += ["## Heute\n", tab(["Wert", "Schluss", "zum Hoch", "21 Tage", "erfüllt −30 % und 21T ≤ −20 %"], sorted(jetzt, key=lambda x: x[2])), "\n"]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "TDIP_FIRSTPASSAGE.md").write_text("\n".join(L), encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
