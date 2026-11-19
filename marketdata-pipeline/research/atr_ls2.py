"""Hoch-ATR-Signale der Lern-Spur LS-2 (User-Frage 2026-11-19: ANET, NET fallen durch die 6-%-Grenze).

Protokoll (vorher festgelegt, 2026-11-19, keine Nachbesserung nach Ergebnis):
  * Signal wie LS-2 (EMA20 x EMA50 nach oben, Schluss > EMA200, EMA50 > EMA200), ATR% >= 0,5 %,
    OHNE Obergrenze. Die 6-%-Grenze stand in allen Backtests vom 2026-11-07 im Code und wurde nie gemessen.
  * Universum wie im Backtest 2026-11-07 (EUR/USD/CHF) plus NET (Anlass der Frage, fehlt im Lern-Universum).
  * ATR%-Klassen: 0,5-2 / 2-3 / 3-4 / 4-5 / 5-6 / 6-8 / 8-10 / ueber 10, dazu Sammelzeilen <= 6 und > 6.
  * Ausstieg wie live: Stop 1,5 ATR, Chandelier 3 ATR auf Schluss, hoechstens 60 HT.
      A  Einstieg zum Signalschluss (wie alle Backtests 2026-11-07)
      B  Einstieg zur Eroeffnung T+1, Stop vom Signalschluss, R auf das geplante Risiko (wie live seit 2026-11-09)
  * Nullhypothese je Klasse: zufaellige Tage mit Schluss > EMA200 und EMA50 > EMA200 in derselben ATR%-Klasse,
    gleicher Ausstieg A, 3 % Stichprobe, fester Seed. Vorsprung = Signal minus Zufall.
  * Fenster: 2009-2017 (Entdeckung), 2018-2026 (Bestaetigung), letzte 5 J, letzte 2 J.
  * Kriterium "traegt" fuer die Sammelzeile > 6: Vorsprung > 0 in 09-17, 18-26 und 5 J (Variante A)
    UND Variante B in 18-26 nicht mehr als 1 Standardfehler unter der Sammelzeile <= 6.
  * Kosten (Annahme, nicht gemessen): gettex bei SB+ unter 500 EUR Ordervolumen 4 EUR je Seite, darueber 0.
    Einsatz = 50 EUR / (1,5 x ATR%), hoechstens 2.000 EUR. Kosten in R = 8 EUR / 50 EUR, wenn Einsatz < 500.
  Bias: Survivorship (heutige Indexmitglieder) trifft volatile Werte vermutlich staerker, weil gescheiterte
  Hoch-ATR-Werte aus den Indizes fallen. Absolute R zusaetzlich mit ~+0,07 R Simulationsbias.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import _a, ind, laden, tab, universum  # noqa: E402
from slots_risikobudget import pfad  # noqa: E402

EUR = (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".HE", ".VI")
EXTRA = ["NET"]
KLASSEN = [(0.005, 0.02, "0,5-2 %"), (0.02, 0.03, "2-3 %"), (0.03, 0.04, "3-4 %"), (0.04, 0.05, "4-5 %"),
           (0.05, 0.06, "5-6 %"), (0.06, 0.08, "6-8 %"), (0.08, 0.10, "8-10 %"), (0.10, 9.99, "ueber 10 %")]
FEE_SEITE, R_EUR, DECKEL = 4.0, 50.0, 2000.0


def klasse(a: float) -> str | None:
    for lo, hi, name in KLASSEN:
        if lo <= a < hi:
            return name
    return None


def pfad_t1(d, i, mult=3.0, max_ht=60):
    """Einstieg Eroeffnung T+1, Stop vom Signalschluss, R auf das geplante Risiko."""
    O, H, Lo, C, A = _a(d)
    n = len(C)
    s0 = C[i]
    stop = s0 - 1.5 * A[i]
    rp = s0 - stop
    j = i + 1
    if j >= n:
        return np.nan, "offen"
    e = O[j]
    if not np.isfinite(e) or e <= 0:
        return np.nan, "fehlt"
    if e <= stop:
        return 0.0, "gap_unter_stop"
    if Lo[j] <= stop:
        return (stop - e) / rp, "stop"
    hoch = C[j]
    stop = max(stop, hoch - mult * A[j])
    for k in range(2, max_ht + 1):
        j = i + k
        if j >= n:
            return (C[-1] - e) / rp, "offen"
        if Lo[j] <= stop:
            return (min(O[j], stop) - e) / rp, "stop"
        hoch = max(hoch, C[j])
        stop = max(stop, hoch - mult * A[j])
    return (C[i + max_ht] - e) / rp, "zeit"


def signale(dd):
    rows = []
    for s, d in dd.items():
        ueber = d.ema20 > d.ema50
        m = (ueber & ~ueber.shift(fill_value=True) & (d.Close > d.ema200) & (d.ema50 > d.ema200)
             & (d.atrp >= 0.005))
        idx = d.index
        n = len(d)
        for j in np.flatnonzero(m.values):
            if j < 260 or j >= n - 1:
                continue
            a = float(d.atrp.iloc[j])
            r_a, x, _ = pfad(d, j)
            r_b, art_b = pfad_t1(d, j)
            einsatz = min(DECKEL, R_EUR / (1.5 * a))
            rows.append({"Symbol": s, "Datum": idx[j], "ATRp": a, "Klasse": klasse(a),
                         "R_A": r_a, "R_B": r_b, "Art_B": art_b,
                         "offen": (x >= n - 1) and (n - 1 - j < 60),
                         "Einsatz": einsatz,
                         "Kosten_R": (2 * FEE_SEITE / R_EUR) if einsatz < 500 else 0.0,
                         "gap_T1_atr": (d.Open.iloc[j + 1] - d.Close.iloc[j]) / d.atr.iloc[j]})
    return pd.DataFrame(rows)


def zufall(dd, anteil=0.03, seed=23):
    rng = np.random.default_rng(seed)
    rows = []
    for s, d in dd.items():
        ok = ((d.Close > d.ema200) & (d.ema50 > d.ema200) & (d.atrp >= 0.005)).to_numpy()
        kand = np.flatnonzero(ok)
        kand = kand[(kand >= 260) & (kand < len(d) - 1)]
        if not len(kand):
            continue
        for j in rng.choice(kand, size=max(1, int(len(kand) * anteil)), replace=False):
            r, _, _ = pfad(d, int(j))
            a = float(d.atrp.iloc[j])
            rows.append({"Datum": d.index[j], "Klasse": klasse(a), "ATRp": a, "R": r})
    return pd.DataFrame(rows)


def fenster(t, ende):
    return {"09-17": (t.Datum >= "2009-01-01") & (t.Datum < "2018-01-01"),
            "18-26": t.Datum >= "2018-01-01",
            "5J": t.Datum >= ende - pd.DateOffset(years=5),
            "2J": t.Datum >= ende - pd.DateOffset(years=2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache_atr.pkl")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    uni = [s for s in universum(Path(a.cfg)) if "." not in s or s.endswith(EUR) or s.endswith(".SW")]
    uni = list(dict.fromkeys(uni + EXTRA))
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}

    t = signale(dd)
    t = t[(t.Datum >= "2009-01-01") & t.R_A.notna()].copy()
    z = zufall(dd)
    z = z[z.Datum >= "2009-01-01"]
    ende = max(d.index[-1] for d in dd.values())
    ft, fz = fenster(t, ende), fenster(z, ende)
    t_g = t[~t.offen]  # abgeschlossene Trades fuer die Statistik

    gruppen = [(name, t_g.Klasse == name, z.Klasse == name) for _, _, name in KLASSEN]
    gruppen += [("Summe <= 6 % (LS-2)", t_g.ATRp < 0.06, z.ATRp < 0.06),
                ("Summe > 6 %", t_g.ATRp >= 0.06, z.ATRp >= 0.06)]
    sd = t_g.R_A.std()
    rows, krit = {}, {}
    for name, mt, mz in gruppen:
        r = {"n": int(mt.sum()), "Symbole": t_g[mt].Symbol.nunique(), "Ø R A gesamt": t_g.R_A[mt].mean()}
        for fn in ("09-17", "18-26", "5J", "2J"):
            mtf = mt & ft[fn].loc[t_g.index]
            mzf = mz & fz[fn]
            ra, rz = t_g.R_A[mtf].mean(), z.R[mzf].mean()
            r[f"Ø R A {fn}"] = ra
            r[f"Vorspr. {fn}"] = ra - rz if mzf.sum() >= 30 else np.nan
        mb = mt & ft["18-26"].loc[t_g.index]
        r["Ø R B 18-26"] = t_g.R_B[mb].mean()
        r["SE 18-26"] = sd / np.sqrt(max(int(mb.sum()), 1))
        r["Treffer A"] = (t_g.R_A[mt] > 0).mean()
        r["Anteil <= -1,25 R (B)"] = (t_g.R_B[mt] <= -1.25).mean()
        r["Einsatz Median"] = t_g.Einsatz[mt].median()
        r["Kosten R Ø"] = t_g.Kosten_R[mt].mean()
        r["Ø R B 18-26 n. Kosten"] = r["Ø R B 18-26"] - t_g.Kosten_R[mb].mean()
        rows[name] = r
    df = pd.DataFrame(rows).T

    lo = df.loc["Summe <= 6 % (LS-2)"]; hi = df.loc["Summe > 6 %"]
    vorsprung_ok = all((hi[f"Vorspr. {f}"] > 0) for f in ("09-17", "18-26", "5J"))
    b_ok = hi["Ø R B 18-26"] >= lo["Ø R B 18-26"] - hi["SE 18-26"]
    traegt = vorsprung_ok and b_ok

    # Haeufigkeit > 6 % je Woche
    def wochen(sub, jahre):
        w = pd.period_range(ende - pd.DateOffset(years=jahre), ende, freq="W")
        s = sub[sub.Datum >= ende - pd.DateOffset(years=jahre)]
        c = s.groupby(s.Datum.dt.to_period("W")).size().reindex(w, fill_value=0)
        return (c >= 1).mean(), c.mean()
    w5 = wochen(t[t.ATRp >= 0.06], 5); w2 = wochen(t[t.ATRp >= 0.06], 2)

    # juengste Hoch-ATR-Signale (180 Kalendertage), Papier-R zum letzten Schluss
    neu = t[(t.ATRp >= 0.06) & (t.Datum >= ende - pd.Timedelta(days=180))].sort_values("Datum")
    neu = neu[["Symbol", "Datum", "ATRp", "R_A", "R_B", "Art_B", "offen"]].copy()
    neu["Datum"] = neu.Datum.dt.strftime("%Y-%m-%d")
    neu["ATRp"] = (neu.ATRp * 100).round(2)
    neu = neu.set_index("Symbol")

    netz = t[t.Symbol.isin(["NET", "ANET", "CRWD", "PANW"])].copy()
    netz_g = netz[~netz.offen].groupby("Symbol").agg(n=("R_A", "size"), R_A=("R_A", "mean"), R_B=("R_B", "mean"),
                                                     ATRp_med=("ATRp", "median"))
    netz_g["ATRp_med"] = netz_g.ATRp_med * 100

    fm = {c: "{:+.2f}" for c in df.columns if c.startswith("Ø R") or c.startswith("Vorspr")}
    fm.update({"Treffer A": "{:.0%}", "Anteil <= -1,25 R (B)": "{:.0%}", "Einsatz Median": "{:,.0f}",
               "Kosten R Ø": "{:.2f}", "SE 18-26": "{:.2f}", "Symbole": "{:.0f}"})
    L = [f"# Hoch-ATR-Signale LS-2 ({pd.Timestamp.now('UTC'):%Y-%m-%d})\n",
         "Protokoll im Kopf von `research/atr_ls2.py` (vorher festgelegt). Variante A: Einstieg Signalschluss, "
         "B: Eroeffnung T+1 wie live. Vorsprung = Signal minus Zufall in derselben ATR%-Klasse und Trendlage, "
         "Ausstieg A. Statistik nur ueber abgeschlossene Trades.\n",
         f"Signale ab 2009: n = {len(t_g)} abgeschlossen ({len(t) - len(t_g)} offen), Symbole {t.Symbol.nunique()}, "
         f"Standardabweichung je Trade {sd:.2f} R. Datenende {ende:%Y-%m-%d}.\n",
         f"**Kriterium Summe > 6 %: {'TRAEGT' if traegt else 'traegt NICHT'}** "
         f"(Vorsprung in 09-17/18-26/5J > 0: {'ja' if vorsprung_ok else 'nein'}; "
         f"B 18-26 nicht mehr als 1 SE unter <= 6 %: {'ja' if b_ok else 'nein'}).\n",
         tab(df, fm), "\n",
         f"Haeufigkeit > 6 %: letzte 5 J in {w5[0]:.0%} der Wochen mindestens ein Signal (Ø {w5[1]:.2f} je Woche), "
         f"letzte 2 J {w2[0]:.0%} (Ø {w2[1]:.2f}).\n",
         "## Anlass-Werte (alle Signale ab 2009, abgeschlossen)\n", tab(netz_g, {"R_A": "{:+.2f}", "R_B": "{:+.2f}",
                                                                              "ATRp_med": "{:.1f}"}), "\n",
         "## Juengste Hoch-ATR-Signale (180 Tage, R offen = Stand letzter Schluss)\n",
         tab(neu, {"R_A": "{:+.2f}", "R_B": "{:+.2f}", "ATRp": "{:.2f}"}), "\n",
         "Kosten sind eine Annahme (4 EUR je Seite unter 500 EUR auf gettex), nicht aus dem Preisverzeichnis gelesen. "
         "Survivorship-Bias trifft die Hoch-ATR-Klassen vermutlich staerker als die ruhigen.\n"]
    (out / "LERNSPUR_HOCH_ATR.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
