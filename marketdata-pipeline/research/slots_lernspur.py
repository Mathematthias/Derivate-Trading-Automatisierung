"""Portfolio-Simulation der Lern-Spur mit Plaetzen (User-Fragen 2026-11-07 abends).

1. Kommen mit dem Filter EMA50 > EMA200 genug Kandidaten (Ziel 2-3 pro Woche)?
2. Wie viel schneller laufen 20 Trades, wenn eine Position mit Chandelier-Stop >= Einstieg (Breakeven)
   keinen Risiko-Platz mehr belegt?

Signal: EMA20 kreuzt EMA50, Schluss > EMA200, ATR% 0,5-6, optional EMA50 > EMA200. Einstieg am
Signalschluss, Stop 1,5 ATR, Chandelier 3 ATR (Stop = max(alt, hoechster Schluss - 3 ATR), wirksam ab
naechstem Tag), max 60 HT. Je Tag Auswahl nach niedrigster ATR%. Ein Symbol nie doppelt.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import _a, ind, laden, tab, universum  # noqa: E402


def pfad(d: pd.DataFrame, i: int, mult: float = 3.0, max_ht: int = 60):
    """R, Ausstiegstag (Index), Tag ab dem der Stop >= Einstieg ist (Index oder None)."""
    O, H, Lo, C, A = _a(d)
    e = C[i]
    stop = e - 1.5 * A[i]
    risk = e - stop
    hoch, be = e, None
    n = len(C)
    for k in range(1, max_ht + 1):
        j = i + k
        if j >= n:
            return (C[-1] - e) / risk, n - 1, be
        if Lo[j] <= stop:
            return (min(O[j], stop) - e) / risk, j, be
        hoch = max(hoch, C[j])
        stop = max(stop, hoch - mult * A[j])
        if be is None and stop >= e:
            be = j + 1          # ab dem naechsten Tag gilt der abgesicherte Stop
    return (C[i + max_ht] - e) / risk, i + max_ht, be


def signale(dd, filt: bool) -> pd.DataFrame:
    rows = []
    for s, d in dd.items():
        ueber = d.ema20 > d.ema50
        m = ueber & ~ueber.shift(fill_value=True) & (d.Close > d.ema200) & (d.atrp <= 0.06) & (d.atrp >= 0.005)
        if filt:
            m &= d.ema50 > d.ema200
        for j in np.flatnonzero(m.values):
            if j < 260 or j >= len(d) - 2:
                continue
            r, x, be = pfad(d, j)
            rows.append({"Symbol": s, "Datum": d.index[j], "ATRp": d.atrp.iloc[j], "R": r,
                         "Exit": d.index[min(x, len(d) - 1)], "BE": d.index[be] if be is not None and be < len(d) else pd.NaT})
    return pd.DataFrame(rows)


def portfolio(t: pd.DataFrame, risiko_plaetze: int, max_gesamt: int, be_frei: bool) -> pd.DataFrame:
    tage = np.sort(t.Datum.unique())
    nach_tag = {k: g.sort_values("ATRp") for k, g in t.groupby("Datum")}
    offen, genommen, belegung = [], [], []
    for tg in tage:
        offen = [p for p in offen if p["Exit"] > tg]          # am Exit-Tag frei fuer neue Signale am Schluss
        risiko = sum(1 for p in offen if not (be_frei and pd.notna(p["BE"]) and p["BE"] <= tg))
        held = {p["Symbol"] for p in offen}
        for _, c in nach_tag.get(tg, pd.DataFrame()).iterrows():
            if risiko >= risiko_plaetze or len(offen) >= max_gesamt:
                break
            if c.Symbol in held:
                continue
            p = c.to_dict()
            offen.append(p); genommen.append(p); held.add(c.Symbol); risiko += 1
        belegung.append(len(offen))
    g = pd.DataFrame(genommen)
    g.attrs["belegung_max"] = max(belegung) if belegung else 0
    g.attrs["belegung_mittel"] = float(np.mean(belegung)) if belegung else 0
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    uni = universum(Path(a.cfg))
    # Live-Universum: nur Direktaktien in EUR oder USD (wie config/lern_spur.yaml)
    eur = (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".HE", ".VI")
    uni = [s for s in uni if "." not in s or s.endswith(eur)]
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    L = [f"# Lern-Spur: Kandidaten je Woche und Breakeven-Freigabe ({pd.Timestamp.utcnow():%Y-%m-%d})\n",
         f"Universum: {len(dd)} Direktaktien in EUR/USD. Ab 2009. Survivorship-Bias wie im Hauptbericht, "
         "absolute R mit rund +0,07 R Simulationsbias.\n"]
    for filt in (False, True):
        t = signale(dd, filt)
        t = t[t.Datum >= "2009-01-01"]
        ende = t.Datum.max()
        name = "mit EMA50 > EMA200" if filt else "ohne Filter (LS-1 heute)"
        wo = t.groupby(t.Datum.dt.to_period("W")).size()
        alle_wo = pd.period_range(t.Datum.min(), ende, freq="W")
        wo = wo.reindex(alle_wo, fill_value=0)
        w5 = wo[wo.index >= (ende - pd.DateOffset(years=5)).to_period("W")]
        be_anteil = t.BE.notna().mean()
        tage_be = ((t.BE - t.Datum).dt.days[t.BE.notna()]).median()
        L += [f"## {name}\n",
              f"Signale: {len(t)}, Ø R {t.R.mean():+.2f}, Anteil mit Breakeven-Stop {be_anteil:.0%} "
              f"(Median {tage_be:.0f} Kalendertage bis dahin).\n",
              f"Signale je Woche gesamt: Median {wo.median():.0f}, Mittel {wo.mean():.1f}, Wochen mit mindestens 2: {(wo >= 2).mean():.0%}, ohne Signal: {(wo == 0).mean():.0%}.",
              f"Letzte 5 Jahre: Median {w5.median():.0f}, Mittel {w5.mean():.1f}, Wochen mit mindestens 2: {(w5 >= 2).mean():.0%}, ohne Signal: {(w5 == 0).mean():.0%}.\n"]
        rows = {}
        jahre = (ende - pd.Timestamp("2009-01-01")).days / 365.25
        for vname, rp, mg, bf in (("2 Plaetze (heute)", 2, 2, False), ("2 Risiko-Plaetze, max 3 gesamt", 2, 3, True),
                                  ("2 Risiko-Plaetze, max 4 gesamt", 2, 4, True), ("2 Risiko-Plaetze, unbegrenzt", 2, 99, True)):
            g = portfolio(t, rp, mg, bf)
            g5 = g[g.Datum >= ende - pd.DateOffset(years=5)]
            rows[vname] = {"Trades/Jahr": len(g) / jahre, "Trades/Jahr 5J": len(g5) / 5,
                           "Wochen fuer 20 Trades": 20 / (len(g) / jahre) * 52, "Ø R": g.R.mean(), "Ø R 5J": g5.R.mean(),
                           "R/Jahr": g.R.sum() / jahre, "Positionen max": g.attrs["belegung_max"],
                           "Positionen Ø": g.attrs["belegung_mittel"]}
        L += [tab(pd.DataFrame(rows).T, {"Trades/Jahr": "{:.1f}", "Trades/Jahr 5J": "{:.1f}",
                                         "Wochen fuer 20 Trades": "{:.0f}", "Positionen max": "{:.0f}",
                                         "Positionen Ø": "{:.2f}", "R/Jahr": "{:.1f}"}), "\n"]
    (out / "LERNSPUR_SLOTS.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
