"""Idee 1: Drift nach Kursluecke mit Volumen (PEAD-Naeherung). Reine Messung.

Signal am Schluss von Tag t:
  P1  Eroeffnungsluecke >= 1 ATR(t-1) ueber dem Vortagesschluss, Volumen >= 2x 50-Tage-Schnitt
  P2  P1 und Schluss >= Eroeffnung (Luecke gehalten)
  P3  P2 und Luecke >= 2 ATR
  PE  P2 und Tag t ist ein Earnings-Reaktionstag (nur US-Werte mit Yahoo-Terminen)
Einstieg Eroeffnung t+1, Ausstieg Eroeffnung nach H Handelstagen (20 oder 60),
eine Variante mit Anfangsstop 1,5 ATR unter dem Signalschluss. Kosten 0,10 % je Seite.
R = Ergebnis / (1,5 ATR(t) / Einstieg). Zufall A: gleicher Wert, gleiches Fenster,
gleiche Haltedauer und gleicher Stop, beliebiger Tag (3 je Trade).
Fenster: Entwicklung 2008-2018, Pruefung 2019-heute, letzte 2 Jahre.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from daten import laden

COST = 0.0010
STOP_ATR = 1.5
MIN_RISIKO = 0.005
SEED = 20261112


def vorbereiten(d: pd.DataFrame, earn: list | None) -> dict:
    c = d.Close
    pc = c.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    vol50 = d.Volume.rolling(50).mean().shift(1)
    gap = (d.Open - pc) / atr.shift(1)
    a = {
        "o": d.Open.to_numpy(float), "l": d.Low.to_numpy(float), "c": c.to_numpy(float),
        "atr": atr.to_numpy(float), "dates": d.index.to_numpy(),
        "gap": gap.to_numpy(float),
        "volx": (d.Volume / vol50.replace(0, np.nan)).to_numpy(float),
    }
    e = np.zeros(len(d), bool)
    if earn:
        idx = d.index
        for tag, nach_schluss in earn:
            p = int(idx.searchsorted(tag))
            if p < len(idx) and (idx[p] - tag).days <= 4:
                q = p + 1 if nach_schluss and idx[p] == tag else p
                if q < len(idx):
                    e[q] = True
    a["earn"] = e
    a["hat_earn"] = bool(earn)
    return a


def signal(a: dict, var: str) -> np.ndarray:
    g, vx, o, c = a["gap"], a["volx"], a["o"], a["c"]
    with np.errstate(invalid="ignore"):
        s = (g >= 1) & (vx >= 2)
        if var in ("P2", "P3", "PE"):
            s &= c >= o
        if var == "P3":
            s &= g >= 2
        if var == "PE":
            s &= a["earn"]
    s[:60] = False
    return s


def trade(a: dict, t: int, H: int, mit_stop: bool):
    o, l, c, atr = a["o"], a["l"], a["c"], a["atr"]
    n = len(o)
    ein_i, aus_i = t + 1, t + 1 + H
    if aus_i >= n:
        return None
    ein = o[ein_i]
    risiko = STOP_ATR * atr[t] / ein
    if not (np.isfinite(risiko) and risiko >= MIN_RISIKO):
        return None
    aus, j_aus = o[aus_i], aus_i
    if mit_stop:
        stop = c[t] - STOP_ATR * atr[t]
        for j in range(ein_i, aus_i):
            if o[j] <= stop:
                aus, j_aus = o[j], j
                break
            if l[j] <= stop:
                aus, j_aus = stop, j
                break
    ret = aus / ein - 1 - 2 * COST
    if not np.isfinite(ret):
        return None
    return ret, ret / risiko, j_aus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--cache", default="work/ideen_cache.pkl")
    ap.add_argument("--out", default="research/ideen/out")
    args = ap.parse_args()
    D = laden(Path(args.cfg), Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    earn = D.get("earnings", {})
    A = {s: vorbereiten(d, earn.get(s)) for s, d in D["aktien"].items()}
    letzter = max(pd.Timestamp(a["dates"][-1]) for a in A.values())
    fenster = [("Entwicklung 2008–18", "2008-01-01", "2018-12-31"),
               ("Pruefung 2019–26", "2019-01-01", "2100-01-01"),
               ("letzte 2 J", str((letzter - pd.DateOffset(years=2)).date()), "2100-01-01")]
    varianten = [("P1", 20, False), ("P1", 60, False), ("P2", 20, False), ("P2", 60, False),
                 ("P2", 60, True), ("P3", 60, False), ("PE", 20, False), ("PE", 60, False),
                 ("PE", 60, True)]
    rng = np.random.default_rng(SEED)
    L = ["# Idee 1: Drift nach Kursluecke mit Volumen (PEAD-Naeherung), 2026-11-12\n"]
    mit_e = sum(1 for a in A.values() if a["hat_earn"])
    L.append(f"Daten: Yahoo, {len(A)} Aktien (heutiges Pipeline-Universum, Survivorship-Bias), "
             f"bis {letzter.date()}. Earnings-Termine fuer {mit_e} US-Aktien. Kosten 0,10 % je Seite. "
             "Zufall A = gleicher Wert, gleiches Fenster, gleiche Haltedauer und gleicher Stop, beliebiger Tag.\n")
    L.append("- P1: Luecke >= 1 ATR, Volumen >= 2x Schnitt\n- P2: P1 + Schluss >= Eroeffnung\n"
             "- P3: P2 + Luecke >= 2 ATR\n- PE: P2 an einem Earnings-Reaktionstag (nur US mit Terminen)\n")
    L.append("Hinweis: Der Vorsprung in Prozent ist die belastbarere Zahl. R teilt durch die ATR am Signaltag, "
             "die durch die Luecke selbst aufgeblaeht ist; das drueckt das R der echten Trades gegenueber Zufall.\n")
    L.append("| Variante | Fenster | Trades | Trades/Jahr | Treffer | Ø Trade | Median | Ø R | Zufall Ø Trade | Vorsprung % | Zufall Ø R | Vorsprung R |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    region_rows = []
    for var, H, st in varianten:
        name = f"{var} H{H}{' +Stop' if st else ''}"
        T = []
        for s, a in A.items():
            sig = np.flatnonzero(signal(a, var))
            frei = -1
            for t in sig:
                if t <= frei:
                    continue
                r = trade(a, int(t), H, st)
                if r is None:
                    continue
                T.append((s, pd.Timestamp(a["dates"][t]), r[0], r[1]))
                frei = r[2]
        df = pd.DataFrame(T, columns=["sym", "datum", "ret", "R"])
        if df.empty:
            L.append(f"| {name} | – | 0 | | | | | | | |")
            continue
        for fname, ab, bis in fenster:
            sub = df[(df.datum >= ab) & (df.datum <= bis)]
            if len(sub) < 20:
                continue
            Z = []
            for s, grp in sub.groupby("sym"):
                a = A[s]
                d = a["dates"]
                lo = max(60, int(np.searchsorted(d, np.datetime64(pd.Timestamp(ab)))))
                hi = min(int(np.searchsorted(d, np.datetime64(pd.Timestamp(bis)))), len(d) - H - 2)
                if hi <= lo:
                    continue
                for _ in range(3 * len(grp)):
                    r = trade(a, int(rng.integers(lo, hi)), H, st)
                    if r is not None:
                        Z.append((r[0], r[1]))
            Z = np.array(Z) if Z else np.full((1, 2), np.nan)
            zp, zr = float(Z[:, 0].mean()), float(Z[:, 1].mean())
            jahre = max((min(pd.Timestamp(bis), letzter) - pd.Timestamp(ab)).days / 365.25, 0.5)
            L.append(f"| {name} | {fname} | {len(sub)} | {len(sub) / jahre:.0f} | {(sub.ret > 0).mean() * 100:.0f} % | "
                     f"{sub.ret.mean() * 100:+.2f} % | {sub.ret.median() * 100:+.2f} % | {sub.R.mean():+.2f} | "
                     f"{zp * 100:+.2f} % | {(sub.ret.mean() - zp) * 100:+.2f} % | {zr:+.2f} | {sub.R.mean() - zr:+.2f} |")
        if (var, H, st) == ("P2", 60, False):
            df["region"] = np.where(df.sym.str.contains(r"\."), "EU", "US")
            for rg, sub in df.groupby("region"):
                for fname, ab, bis in fenster[:2]:
                    ss = sub[(sub.datum >= ab) & (sub.datum <= bis)]
                    region_rows.append(f"| {rg} | {fname} | {len(ss)} | {(ss.ret > 0).mean() * 100:.0f} % | "
                                       f"{ss.ret.mean() * 100:+.2f} % | {ss.R.mean():+.2f} |")
            df["jahr"] = df.datum.dt.year
            jahr_rows = [f"| {j} | {len(g)} | {g.ret.mean() * 100:+.2f} % | {g.R.mean():+.2f} |"
                         for j, g in df.groupby("jahr")]
        print(name, len(df), flush=True)
    L.append("\n## P2 H60 nach Region\n")
    L.append("| Region | Fenster | Trades | Treffer | Ø Trade | Ø R |")
    L.append("|---|---|---|---|---|---|")
    L += region_rows
    L.append("\n## P2 H60 nach Jahr (Signaljahr)\n")
    L.append("| Jahr | Trades | Ø Trade | Ø R |")
    L.append("|---|---|---|---|")
    L += jahr_rows
    L.append("\nGrenzen: Survivorship-Bias, Luecke ist nur eine Naeherung fuer Ueberraschungen "
             "(auch News, Uebernahmen), Earnings-Termine nur US und nur so weit Yahoo sie liefert, "
             "keine Steuern, Waehrungen nicht umgerechnet.\n")
    (out / "1_PEAD.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
