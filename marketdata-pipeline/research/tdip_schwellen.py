"""TDIP-Einstieg: reine Messung (2026-11-09, User-Frage: Warum erst -20 %?). Protokoll vorab festgelegt.

Abschnitte: 1 Schwellen-Raster · 2 Jetzt kaufen gegen auf -20 % warten · 3 Kurs wie vor 6/12 Monaten ·
4 Marktbreite Tech · 5 Umkehr-Ausloeser · 6 Kontext (nur Tech gefallen? Tempo? Rueckstand zu SPY?).
Ereignis = erstes Kreuzen nach Erholung ueber -5 % vom 252-Tage-Hoch. Dividendenbereinigt, ohne Kosten und Steuern.
ETFs ohne Survivorship-Bias, Einzelaktien mit (heutige Gewinner).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

IDX = ["XLK", "QQQ", "SMH", "SKYY", "IGV", "SPY"]
ETF_TECH = ["XLK", "QQQ", "SMH", "SKYY", "IGV"]
AKTIEN = ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "CSCO", "ADBE", "QCOM", "TXN", "INTU", "NOW", "MU",
          "AMAT", "LRCX", "KLAC", "IBM", "ACN", "INTC", "PANW", "CRWD", "SNPS", "CDNS", "ADI", "NXPI", "ANET", "DELL",
          "HPQ", "AMZN", "GOOGL", "META"]
H = {"1M": 21, "3M": 63, "6M": 126, "12M": 252}


def lade() -> pd.DataFrame:
    alle = IDX + AKTIEN + ["^VIX"]
    if os.environ.get("TDIP_SYNTH"):
        ix = pd.bdate_range("1999-01-01", "2026-11-06")
        rng = np.random.default_rng(1)
        df = pd.DataFrame({s: 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.018, len(ix)))) for s in alle}, index=ix)
        df["^VIX"] = 20 * np.exp(np.cumsum(rng.normal(0, 0.03, len(ix))) * 0.05)
        return df
    import yfinance as yf
    d = yf.download(alle, period="max", auto_adjust=True, group_by="ticker", progress=False, threads=True)
    px = pd.DataFrame({s: d[s]["Close"] for s in alle}).dropna(how="all")
    return px[px.index < pd.Timestamp.utcnow().tz_localize(None).normalize()]  # nur abgeschlossene Tage


def rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def dd_von(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    hoch = c.rolling(252, min_periods=60).max()
    return c / hoch - 1, hoch


def ereignisse(dd: pd.Series, schw: float, extra: pd.Series | None = None) -> list[int]:
    out, scharf = [], True
    werte = dd.to_numpy()
    ex = None if extra is None else extra.to_numpy()
    for i, v in enumerate(werte):
        if np.isnan(v):
            continue
        if v > -0.05:
            scharf = True
        elif scharf and v <= schw and (ex is None or bool(ex[i])):
            out.append(i)
            scharf = False
    return out


def fwd(c: np.ndarray, i: int, n: int) -> float:
    return c[i + n] / c[i] - 1 if i + n < len(c) else np.nan


def mae(c: np.ndarray, i: int, n: int) -> float:
    if i + n >= len(c):
        return np.nan
    return c[i + 1:i + n + 1].min() / c[i] - 1


def s(x) -> dict:
    x = np.array([v for v in x if not np.isnan(v)], dtype=float)
    if len(x) == 0:
        return {"n": 0, "mean": np.nan, "med": np.nan, "pos": np.nan, "min": np.nan, "se": np.nan}
    return {"n": len(x), "mean": x.mean(), "med": float(np.median(x)), "pos": float((x > 0).mean()), "min": x.min(),
            "se": x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan}


def p(v, nk=1):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v * 100:+.{nk}f} %"


def q(v):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v * 100:.0f} %"


def tab(kopf, zeilen):
    z = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    z += ["| " + " | ".join(str(v) for v in r) + " |" for r in zeilen]
    return "\n".join(z) + "\n"


def zeile_fwd(name, c_map: list[tuple[np.ndarray, int]]):
    """c_map: Liste (Kurse, Index). Liefert Tabellenzeile fuer 1M/3M/6M/12M, Trefferquoten, MAE."""
    r = {k: s([fwd(c, i, n) for c, i in c_map]) for k, n in H.items()}
    m = s([mae(c, i, 126) for c, i in c_map])
    return [name, len(c_map), p(r["1M"]["mean"]), p(r["3M"]["mean"]), p(r["6M"]["mean"]), p(r["12M"]["mean"]),
            q(r["6M"]["pos"]), q(r["12M"]["pos"]), p(r["6M"]["min"]), p(r["12M"]["min"]), p(m["mean"]), p(m["min"]),
            p(r["6M"]["se"])]


KOPF_FWD = ["Gruppe", "n", "Ø 1M", "Ø 3M", "Ø 6M", "Ø 12M", "pos 6M", "pos 12M", "min 6M", "min 12M", "Ø Tief 6M", "min Tief 6M",
            "SE 6M"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/out")
    a = ap.parse_args()
    px = lade()
    L = ["# TDIP-Einstieg: Schwellen, Warten, Umkehr (Messung 2026-11-09)\n",
         f"Daten: Yahoo, dividendenbereinigt, letzter Bar {px.index[-1].date()}. Ohne Kosten und Steuern. Ereignis = erstes Kreuzen "
         "nach Erholung über −5 % vom 252-Tage-Hoch. Wenige, sich überlappende Episoden, ETFs sind stark korreliert: Unterschiede "
         "unter rund zwei Standardfehlern sind Rauschen. Einzelaktien mit Survivorship-Bias (heutige Gewinner).\n"]
    C = {t: px[t].dropna() for t in IDX + AKTIEN}
    DD = {t: dd_von(C[t]) for t in C}
    spy_dd = DD["SPY"][0]

    # Stand
    z = []
    for t in IDX:
        c = C[t]
        z.append([t, c.index[-1].date(), f"{c.iloc[-1]:.2f}", p(DD[t][0].iloc[-1]), p(c.iloc[-1] / c.iloc[-127] - 1), p(c.iloc[-1] / c.iloc[-253] - 1),
                  f"{rsi(c).iloc[-1]:.0f}", "ja" if c.iloc[-1] > c.rolling(200).mean().iloc[-1] else "nein",
                  p((c.iloc[-1] / c.iloc[-22]) / (C["SPY"].iloc[-1] / C["SPY"].iloc[-22]) - 1)])
    L += ["## Stand\n", tab(["ETF", "Datum", "Schluss", "zum Hoch", "6M", "12M", "RSI", "über SMA200", "1M gegen SPY"], z), "\n"]

    # 1 Raster
    L += ["## 1 Schwellen-Raster\n"]
    schw = [-0.10, -0.125, -0.15, -0.175, -0.184, -0.20, -0.225, -0.25, -0.30]
    for t in ETF_TECH + ["SPY"]:
        c = C[t].to_numpy()
        z = [zeile_fwd(f"{t} {x * 100:.1f} %", [(c, i) for i in ereignisse(DD[t][0], x)]) for x in schw]
        L += [f"**{t}**\n", tab(KOPF_FWD, z), "\n"]
    z = []
    for x in schw:
        cm = []
        for t in ETF_TECH:
            c = C[t].to_numpy()
            cm += [(c, i) for i in ereignisse(DD[t][0], x)]
        z.append(zeile_fwd(f"{x * 100:.1f} %", cm))
    L += ["**Alle Tech-ETFs zusammen** (nicht unabhängig)\n", tab(KOPF_FWD, z), "\n"]
    z = []
    for t in ETF_TECH + ["SPY"]:
        c = C[t].to_numpy()
        z.append([t] + [p(np.nanmean([fwd(c, i, n) for i in range(len(c) - n)])) for n in H.values()])
    L += ["Unbedingt (jeder Tag):\n", tab(["ETF"] + list(H), z), "\n"]

    # 2 Warten
    L += ["## 2 Jetzt kaufen gegen auf −20 % warten\n",
          "Einstieg A = Schluss am ersten Kreuzen der Schwelle. W = Kauf am ersten Schluss ≤ −20 % binnen 126 Tagen, sonst 0. "
          "H = halb bei A, halb bei −20 %. Bewertung: bis A+126 Tage, Ausstieg am nächsten Schluss nach Unterschreiten von −35 % "
          "vom Hoch bei A. Rendite je voller Position.\n"]

    def lauf(c, lvl, ein, ende):
        for k in range(ein + 1, min(ende + 1, len(c))):
            if c[k] < lvl:
                return c[min(k + 1, len(c) - 1)] / c[ein] - 1
        return c[ende] / c[ein] - 1

    def erg(t, x):
        c = C[t].to_numpy()
        dd, hoch = DD[t]
        d = dd.to_numpy()
        h = hoch.to_numpy()
        rows = []
        for i in ereignisse(dd, x):
            if i + 126 >= len(c):
                continue
            j = next((k for k in range(i, i + 127) if d[k] <= -0.20), None)
            lvl, ende = h[i] * 0.65, i + 126
            r_a = lauf(c, lvl, i, ende)
            r_w = 0.0 if j is None else lauf(c, lvl, j, ende)
            rows.append(dict(t=t, datum=C[t].index[i].date(), hit=j is not None, tage=None if j is None else j - i,
                             r_a=r_a, r_w=r_w, r_h=0.5 * r_a + 0.5 * r_w, sprung=(j == i), preisvort=None if j is None else c[j] / c[i] - 1))
        return rows

    for x in (-0.15, -0.175, -0.184):
        z = []
        alle = []
        for t in ETF_TECH:
            r = erg(t, x)
            alle += r
            if r:
                z.append([t, len(r), q(np.mean([e["hit"] for e in r])), q(np.mean([e["hit"] and e["tage"] <= 20 for e in r])),
                          q(np.mean([e["hit"] and e["tage"] <= 60 for e in r])), p(np.mean([e["r_a"] for e in r])), p(np.mean([e["r_w"] for e in r])),
                          p(np.mean([e["r_h"] for e in r])), p(np.nanmean([e["r_a"] for e in r if not e["hit"]]) if any(not e["hit"] for e in r) else np.nan)])
        if alle:
            r = alle
            z.append(["alle", len(r), q(np.mean([e["hit"] for e in r])), q(np.mean([e["hit"] and e["tage"] <= 20 for e in r])),
                      q(np.mean([e["hit"] and e["tage"] <= 60 for e in r])), p(np.mean([e["r_a"] for e in r])), p(np.mean([e["r_w"] for e in r])),
                      p(np.mean([e["r_h"] for e in r])), p(np.nanmean([e["r_a"] for e in r if not e["hit"]]) if any(not e["hit"] for e in r) else np.nan)])
        L += [f"**Ausgang bei {x * 100:.1f} %, Marke −20 %**\n",
              tab(["ETF", "n", "−20 % erreicht", "binnen 20 T", "binnen 60 T", "Ø sofort", "Ø warten", "Ø halb/halb", "Ø sofort, wenn −20 % nie kam"], z), "\n"]
    L += ["**Einzelepisoden XLK, Ausgang −18,4 %**\n",
          tab(["Datum", "−20 % erreicht", "nach Tagen", "sofort", "warten", "halb/halb"],
              [[e["datum"], "ja" if e["hit"] else "nein", e["tage"], p(e["r_a"]), p(e["r_w"]), p(e["r_h"])] for e in erg("XLK", -0.184)]), "\n"]

    # 3 Kurs wie vor 6/12 Monaten
    L += ["## 3 Kurs wie vor 6 oder 12 Monaten\n", "Ereignis: Kurs ≤ Kurs vor 126 bzw. 252 Tagen und zugleich ≥ 15 % unter dem Hoch, nach einem Lauf von mindestens +25 % in den 252 Tagen vor dem Hoch.\n"]

    def vorlauf(t):
        c, (dd, hoch) = C[t], DD[t]
        idxmax = c.rolling(252, min_periods=60).apply(lambda v: len(v) - 1 - int(np.argmax(v)), raw=True)
        arr = c.to_numpy()
        out = np.full(len(arr), np.nan)
        for i, a2 in enumerate(idxmax.to_numpy()):
            if np.isnan(a2):
                continue
            pk = i - int(a2)
            if pk >= 252:
                out[i] = arr[pk] / arr[pk - 252] - 1
        return pd.Series(out, index=c.index)

    def ev3(t, n, mit_lauf):
        c = C[t]
        ret = c / c.shift(n) - 1
        bed = ret <= 0
        if mit_lauf:
            bed = bed & (vorlauf(t) >= 0.25)
        return ereignisse(DD[t][0], -0.15, bed)

    z = []
    for t in ETF_TECH:
        c = C[t].to_numpy()
        for n, lab in ((126, "6M"), (252, "12M")):
            z.append(zeile_fwd(f"{t} ≤ {lab}", [(c, i) for i in ev3(t, n, False)]))
            z.append(zeile_fwd(f"{t} ≤ {lab}, nach Lauf", [(c, i) for i in ev3(t, n, True)]))
    L += [tab(KOPF_FWD, z), "\n"]
    z = []
    for n, lab in ((126, "6M"), (252, "12M")):
        for lauf_flag in (False, True):
            cm = []
            for t in AKTIEN:
                c = C[t].to_numpy()
                cm += [(c, i) for i in ev3(t, n, lauf_flag)]
            z.append(zeile_fwd(f"Aktien ≤ {lab}" + (", nach Lauf" if lauf_flag else ""), cm))
    uncond = {k: np.nanmean([np.nanmean([fwd(C[t].to_numpy(), i, m) for i in range(0, len(C[t]) - m, 21)]) for t in AKTIEN]) for k, m in H.items()}
    L += ["**32 Tech-Aktien zusammen** (Survivorship-Bias)\n", tab(KOPF_FWD, z), "\n",
          "Unbedingt Aktien: " + ", ".join(f"{k} {p(v)}" for k, v in uncond.items()) + "\n\n"]
    jetzt = []
    for t in AKTIEN:
        c = C[t]
        if len(c) > 260:
            jetzt.append([t, f"{c.iloc[-1]:.2f}", p(DD[t][0].iloc[-1]), p(c.iloc[-1] / c.iloc[-127] - 1), p(c.iloc[-1] / c.iloc[-253] - 1)])
    L += ["Stand Einzelwerte:\n", tab(["Aktie", "Schluss", "zum Hoch", "6M", "12M"], jetzt), "\n"]

    # 4 Breite
    L += ["## 4 Marktbreite Tech (32 Aktien)\n", "Anteil der Aktien, die unter ihrem Kurs von vor 12 Monaten, vor 6 Monaten bzw. mehr als 20 % unter dem Hoch stehen. Erstes Überschreiten, neu scharf unter 30 %. Survivorship-Bias.\n"]
    a_df = pd.DataFrame({t: C[t] for t in AKTIEN})
    ok = a_df.notna().sum(axis=1) >= 15
    br = {"12M neg.": (a_df / a_df.shift(252) - 1 <= 0).where(a_df.shift(252).notna()), "6M neg.": (a_df / a_df.shift(126) - 1 <= 0).where(a_df.shift(126).notna()),
          "≥20 % unterm Hoch": pd.DataFrame({t: DD[t][0] <= -0.20 for t in AKTIEN}).where(a_df.notna())}
    z = []
    for lab, m in br.items():
        m = m.astype(float)
        sh = (m.sum(axis=1) / m.notna().sum(axis=1).replace(0, np.nan)).where(ok)
        L += [f"{lab}, heute: {q(sh.dropna().iloc[-1])}\n\n"]
        for b in (0.4, 0.5, 0.6, 0.7, 0.8):
            ev, scharf = [], True
            for d, v in sh.dropna().items():
                if v < 0.30:
                    scharf = True
                elif scharf and v >= b:
                    ev.append(d)
                    scharf = False
            for t in ("XLK", "QQQ"):
                c = C[t]
                cm = [(c.to_numpy(), int(c.index.get_indexer([d], method="nearest")[0])) for d in ev if d in c.index]
                z.append(zeile_fwd(f"{lab} ≥ {q(b)} → {t}", cm))
    L += [tab(KOPF_FWD, z), "\n"]

    # 5 Umkehr
    L += ["## 5 Umkehr-Auslöser\n", "Voraussetzung: −15 % vom Hoch erreicht (Scharfstellung). Erster Auslöser binnen 126 Tagen danach, je Episode einmal. „Aufpreis“ = Einstieg gegen Kurs am Scharfstellungstag.\n"]
    vix = px["^VIX"].dropna()

    def trig(t):
        c = C[t]
        dd = DD[t][0]
        arr = c.to_numpy()
        e20 = c.ewm(span=20, adjust=False).mean().to_numpy()
        e50 = c.ewm(span=50, adjust=False).mean().to_numpy()
        r = rsi(c).to_numpy()
        r5 = (c / c.shift(5) - 1).to_numpy()
        v = vix.reindex(c.index).ffill()
        vc = (v / v.shift(3) - 1).to_numpy()
        vv = v.to_numpy()
        res = {k: [] for k in ("Scharf -15 %", "Schluss > EMA20", "Schluss > EMA50", "RSI <35 dann >=40", "5T +6 %", "VIX >=25, 3T -15 %")}
        for i in ereignisse(dd, -0.15):
            res["Scharf -15 %"].append((i, i))
            ende = min(i + 126, len(arr) - 1)
            f = lambda bed: next((k for k in range(i, ende + 1) if bed(k)), None)
            for k, b in (("Schluss > EMA20", lambda k: arr[k] > e20[k]), ("Schluss > EMA50", lambda k: arr[k] > e50[k]), ("5T +6 %", lambda k: r5[k] >= 0.06),
                         ("VIX >=25, 3T -15 %", lambda k: vv[k] >= 25 and vc[k] <= -0.15)):
                j = f(b)
                if j is not None:
                    res[k].append((i, j))
            un = next((k for k in range(i, ende + 1) if r[k] < 35), None)
            if un is not None:
                j = next((k for k in range(un, ende + 1) if r[k] >= 40), None)
                if j is not None:
                    res["RSI <35 dann >=40"].append((i, j))
        return res

    for t in ["XLK", "ALLE"]:
        z = []
        namen = None
        pool = {}
        for tt in (["XLK"] if t == "XLK" else ETF_TECH):
            for k, v in trig(tt).items():
                pool.setdefault(k, []).extend((C[tt].to_numpy(), i, j) for i, j in v)
        for k, v in pool.items():
            z.append(zeile_fwd(k, [(c, j) for c, i, j in v]) + [p(np.mean([c[j] / c[i] - 1 for c, i, j in v]) if v else np.nan)])
        L += [f"**{t}**\n", tab(KOPF_FWD + ["Ø Aufpreis"], z), "\n"]

    # 6 Kontext
    L += ["## 6 Kontext\n"]
    z = []
    for x in (-0.15, -0.20):
        gr = {"nur Tech (SPY besser als -10 %)": [], "breit (SPY -10 % oder tiefer)": [], "schnell (21T <= -12 %)": [], "langsam (21T > -12 %)": [],
              "Rückstand zu SPY 21T <= -8 %": [], "Rückstand zu SPY 21T > -8 %": []}
        for t in ETF_TECH:
            c = C[t]
            arr = c.to_numpy()
            r21 = (c / c.shift(21) - 1)
            rel = (c / c.shift(21)) / (C["SPY"].reindex(c.index) / C["SPY"].reindex(c.index).shift(21)) - 1
            sd = spy_dd.reindex(c.index)
            for i in ereignisse(DD[t][0], x):
                gr["nur Tech (SPY besser als -10 %)" if sd.iloc[i] > -0.10 else "breit (SPY -10 % oder tiefer)"].append((arr, i))
                gr["schnell (21T <= -12 %)" if r21.iloc[i] <= -0.12 else "langsam (21T > -12 %)"].append((arr, i))
                gr["Rückstand zu SPY 21T <= -8 %" if rel.iloc[i] <= -0.08 else "Rückstand zu SPY 21T > -8 %"].append((arr, i))
        for k, v in gr.items():
            z.append(zeile_fwd(f"{x * 100:.0f} %: {k}", v))
    L += [tab(KOPF_FWD, z), "\n"]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    (Path(a.out) / "TDIP_SCHWELLEN.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L)[:600])


if __name__ == "__main__":
    main()
