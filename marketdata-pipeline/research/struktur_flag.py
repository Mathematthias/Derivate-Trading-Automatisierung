"""Struktur-Flag (Treppe) und Strukturstop (User 2026-11-14). Reine Messung, aendert keine Regel.

Protokoll (vor dem Lauf festgelegt, 2026-11-14, im Chat vorgelegt):
  Swing-Hoch / Swing-Tief: Tag k mit dem hoechsten Hoch / tiefsten Tief im Fenster k-5 .. k+5 (bei
    Gleichstand zaehlt der erste Tag). Bestaetigt erst am Schluss von k+5; an Tag j zaehlen nur Swings
    mit k+5 <= j. Kein Blick in die Zukunft.
  Treppe an Tag j aus den letzten zwei bestaetigten Swing-Hochs H1, H2 und Swing-Tiefs T1, T2:
    aufwaerts H2 > H1 und T2 > T1, abwaerts H2 < H1 und T2 < T1, sonst gemischt.

  Aktien (LS-2-Signale wie einstieg_t1.py, Live-Variante B: Einstieg Eroeffnung T+1, Stop Schluss T - 1,5 ATR,
  Chandelier 3 ATR, Zeitausstieg 60 HT):
    M1  Flag: Ø R, Treffer, letzte 5 J je Treppe; Zufall an Trendtagen je Treppe; Portfolio (Budget 3 R a 50 EUR,
        12.000 EUR, CHF-Deckel, Auswahl niedrigste ATR %) alle Signale gegen "ohne abwaerts" und "nur aufwaerts".
    M2a Lage des ATR-Stops zum letzten bestaetigten Swing-Tief unter dem Signalschluss (hoechstens 120 HT alt):
        Abstand (Stop - Swing-Tief) / ATR in Klassen; Ø R und Anteil voller Stop (R <= -0,9) je Klasse.
    M2b Strukturstop: Stop = min(ATR-Stop, Swing-Tief - 0,5 ATR). R auf diesen Abstand, Stueckzahl also
        kleiner; Chandelier unveraendert. Vergleich je Trade (gepaart) und im Portfolio.
  Krypto (36 Kraken-Coins wie krypto_lernspur.py, Yahoo USD, Tagesschluss): Vorwaertsrendite 20 / 60 Tage
    je Treppe fuer (a) alle Tage, (b) Donchian-Einstiege je Coin (Schluss > Hoch der 50 Vortage, Vortag nicht),
    jeweils alle Coins und nur BTC/ETH. Fenster ab 2018 und ab 2022.

Grenzen: Survivorship-Bias (heutige Universen), Aktien ohne Kosten und Steuern, Krypto-Renditen ueberlappen
(Standardfehler zu klein), Signale ballen sich.
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view as swv

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import _a, ind, laden, tab, universum  # noqa: E402
from einstieg_t1 import START, se, signale, zufall  # noqa: E402
from filter_ls2 import EUR, _chf_deckel  # noqa: E402
from slots_risikobudget import rest_am  # noqa: E402

N = 5
LOOKBACK = 120
TREPPE = {1.0: "aufwaerts", 0.0: "gemischt", -1.0: "abwaerts"}
COINS = ["BTC-USD", "ETH-USD", "XRP-USD", "LTC-USD", "BCH-USD", "ADA-USD", "XLM-USD", "LINK-USD",
         "DOT-USD", "SOL-USD", "DOGE-USD", "TRX-USD", "ETC-USD", "ATOM-USD", "AVAX-USD", "UNI7083-USD",
         "AAVE-USD", "ALGO-USD", "XTZ-USD", "NEAR-USD", "FIL-USD", "BAT-USD", "DASH-USD", "ZEC-USD",
         "EOS-USD", "MANA-USD", "SAND-USD", "GRT6719-USD", "CRV-USD", "SNX-USD", "ICP-USD", "INJ-USD",
         "HBAR-USD", "VET-USD", "QNT-USD", "KSM-USD"]


# ------------------------------------------------------------------ Struktur
def swing_idx(x: np.ndarray, hoch: bool, n: int = N) -> np.ndarray:
    """Indizes k der Swing-Punkte (Extrem im Fenster k-n..k+n, erster bei Gleichstand)."""
    if len(x) < 2 * n + 1:
        return np.array([], dtype=int)
    w = swv(np.where(np.isfinite(x), x, -np.inf if hoch else np.inf), 2 * n + 1)
    a = np.argmax(w, axis=1) if hoch else np.argmin(w, axis=1)
    k = np.flatnonzero(a == n) + n
    return k[np.isfinite(x[k])]


def treppe(H: np.ndarray, L: np.ndarray, n: int = N):
    """Treppe je Tag (+1/0/-1, NaN ohne Historie) und die bestaetigten Swing-Tiefs (Index, Bestaetigung)."""
    m = len(H)
    kh, kl = swing_idx(H, True, n), swing_idx(L, False, n)
    st = np.full(m, np.nan)
    if len(kh) < 2 or len(kl) < 2:
        return st, kl
    j = np.arange(m)
    ih = np.searchsorted(kh + n, j, side="right")
    il = np.searchsorted(kl + n, j, side="right")
    ok = (ih >= 2) & (il >= 2)
    h2, h1 = H[kh[np.clip(ih - 1, 0, None)]], H[kh[np.clip(ih - 2, 0, None)]]
    l2, l1 = L[kl[np.clip(il - 1, 0, None)]], L[kl[np.clip(il - 2, 0, None)]]
    auf, ab = (h2 > h1) & (l2 > l1), (h2 < h1) & (l2 < l1)
    st[ok] = np.where(auf, 1.0, np.where(ab, -1.0, 0.0))[ok]
    return st, kl


def swing_tief_unter(L, kl, j, preis, n=N, lookback=LOOKBACK):
    """Letztes am Tag j bestaetigtes Swing-Tief unter preis, hoechstens lookback HT alt; sonst NaN."""
    i = np.searchsorted(kl + n, j, side="right") - 1
    while i >= 0 and j - kl[i] <= lookback:
        if L[kl[i]] < preis:
            return float(L[kl[i]])
        i -= 1
    return np.nan


# ------------------------------------------------------------------ Aktien
def pfad_stop(d, i, stop0, mult=3.0, max_ht=60):
    """Wie einstieg_t1.pfad_t1, aber mit frei gewaehltem Anfangsstop. R auf Schluss T - stop0."""
    O, H, Lo, C, A = _a(d)
    j0 = i + 1
    e, stop = O[j0], stop0
    plan = C[i] - stop0
    if e <= stop or plan <= 0:
        return None
    hoch = e
    rest = {j0: (e - stop) / plan}
    n = len(C)
    for k in range(0, max_ht + 1):
        j = j0 + k
        if j >= n:
            return (C[-1] - e) / plan, n - 1, rest
        if Lo[j] <= stop:
            return (min(O[j], stop) - e) / plan, j, rest
        hoch = max(hoch, C[j])
        stop = max(stop, hoch - mult * A[j])
        rest[j + 1] = max(0.0, (e - stop) / plan)
    return (C[j0 + max_ht] - e) / plan, j0 + max_ht, rest


def pf(t, budget=3.0, r_eur=50.0, kapital=12000.0, deckel=2000.0) -> pd.DataFrame:
    """Portfolio wie einstieg_t1_zerlegung.pf; Einsatz aus dem Stopabstand in % (riskp)."""
    tage = np.sort(t.Datum.unique())
    nach_tag = {k: g.sort_values("ATRp") for k, g in t.groupby("Datum")}
    offen, genommen = [], []
    for tg in tage:
        offen = [p for p in offen if p["Exit"] > tg]
        held = {p["Symbol"] for p in offen}
        belegt = sum(rest_am(p, tg) for p in offen)
        for _, c in nach_tag[tg].iterrows():
            if belegt + 1 > budget + 1e-9:
                break
            if c.Symbol in held:
                continue
            einsatz = min(deckel, r_eur / c.riskp)
            if sum(q["einsatz"] for q in offen) + einsatz > kapital:
                continue
            p = c.to_dict()
            p["einsatz"] = einsatz
            offen.append(p); genommen.append(p); held.add(c.Symbol); belegt += 1
    return pd.DataFrame(genommen)


def kennz(r: pd.Series) -> dict:
    r = r.dropna()
    return {"n": len(r), "Ø R": r.mean(), "SE": se(r), "Median": r.median(), "Treffer": (r > 0).mean(),
            "voller Stop": (r <= -0.9).mean()}


def pf_kennz(p: pd.DataFrame, jahre: float, ab5) -> dict:
    if p.empty:
        return {"Trades/J": 0.0}
    eur = p.R * p.einsatz * p.riskp
    kum = p.sort_values("Exit").R.cumsum()
    return {"Trades/J": len(p) / jahre, "Ø R": p.R.mean(), "Ø R 5J": p.R[p.Datum >= ab5].mean(),
            "EUR/J": eur.sum() / jahre, "EUR/J 5J": eur[p.Datum >= ab5].sum() / 5.0,
            "DD R": float((kum - kum.cummax()).min()), "Treffer": (p.R > 0).mean()}


def rest_serie(idx, rest):
    return pd.Series({idx[k]: v for k, v in rest.items() if k < len(idx)})


def aktien(a, L: list[str]) -> None:
    uni = [s for s in universum(Path(a.cfg)) if "." not in s or s.endswith(EUR) or s.endswith(".SW")]
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    ST, KL = {}, {}
    for s, d in dd.items():
        _, H, Lo, _, _ = _a(d)
        ST[s], KL[s] = treppe(H, Lo)

    t, _ = signale(dd)
    t = t[(t.Datum >= START) & t.R_B.notna()].reset_index(drop=True)
    rows = []
    for _, r in t.iterrows():
        d = dd[r.Symbol]
        j = d.index.get_loc(r.Datum)
        _, _, Lo, C, A = _a(d)
        stop_atr = C[j] - 1.5 * A[j]
        sl = swing_tief_unter(Lo, KL[r.Symbol], j, C[j])
        stop_b = min(stop_atr, sl - 0.5 * A[j]) if np.isfinite(sl) else stop_atr
        b = pfad_stop(d, j, stop_b)
        rows.append({"treppe": ST[r.Symbol][j], "swing_tief": sl,
                     "abst_atr": (stop_atr - sl) / A[j] if np.isfinite(sl) else np.nan,
                     "stop_b_atr": (C[j] - stop_b) / A[j],
                     "R_S": b[0] if b else np.nan,
                     "Exit_S": d.index[min(b[1], len(d) - 1)] if b else pd.NaT,
                     "rest_S": rest_serie(d.index, b[2]) if b else None})
    t = pd.concat([t, pd.DataFrame(rows)], axis=1)
    t["R"] = t.R_B; t["Exit"] = t.Exit_B
    t["rest"] = [rest_serie(dd[s].index, r) for s, r in zip(t.Symbol, t.rest_B)]
    t["riskp"] = 1.5 * t.ATRp
    t["Treppe"] = t.treppe.map(TREPPE).fillna("ohne Historie")
    ende = t.Datum.max()
    ab5 = ende - pd.DateOffset(years=5)
    jahre = (ende - pd.Timestamp(START)).days / 365.25

    # M1 je Treppe
    zt = zufall(dd, True)
    zt = zt[(zt.Datum >= START) & zt.R_B.notna()].reset_index(drop=True)
    zt["Treppe"] = [TREPPE.get(ST[s][dd[s].index.get_loc(x)], "ohne Historie") for s, x in zip(zt.Symbol, zt.Datum)]
    rows = {}
    for g in ("aufwaerts", "gemischt", "abwaerts", "ohne Historie"):
        m = t.Treppe == g
        if not m.any():
            continue
        k = kennz(t.R[m]); k["Anteil"] = m.mean(); k["Ø R 5J"] = t.R[m & (t.Datum >= ab5)].mean()
        zm = zt.Treppe == g
        k["Zufall Trendtage Ø R"] = zt.R_B[zm].mean(); k["Zufall n"] = int(zm.sum())
        rows[g] = k
    k = kennz(t.R); k["Anteil"] = 1.0; k["Ø R 5J"] = t.R[t.Datum >= ab5].mean()
    k["Zufall Trendtage Ø R"] = zt.R_B.mean(); k["Zufall n"] = len(zt)
    rows["alle"] = k
    T1 = pd.DataFrame(rows).T
    T1.index.name = "Treppe am Signaltag"

    # M1 Portfolio
    basis = _chf_deckel(t).reset_index(drop=True)
    P = {"alle Signale (LS-2 heute)": pf(basis),
         "ohne Treppe abwaerts": pf(basis[basis.Treppe != "abwaerts"]),
         "nur Treppe aufwaerts": pf(basis[basis.Treppe == "aufwaerts"])}
    T1b = pd.DataFrame({k: pf_kennz(v, jahre, ab5) for k, v in P.items()}).T
    T1b.index.name = "Portfolio (3 R a 50 EUR)"

    # M2a Lage des ATR-Stops zum Swing-Tief
    bins = [-np.inf, -0.5, 0.0, 0.25, 1.0, np.inf]
    labs = ["Stop > 0,5 ATR unter Swing-Tief", "Stop 0-0,5 ATR unter Swing-Tief", "Stop 0-0,25 ATR ueber Swing-Tief",
            "Stop 0,25-1 ATR ueber Swing-Tief", "Stop > 1 ATR ueber Swing-Tief"]
    t["Lage"] = pd.cut(t.abst_atr, bins, labels=labs, right=False).astype(object)
    t.loc[t.abst_atr.isna(), "Lage"] = f"kein Swing-Tief (<= {LOOKBACK} HT)"
    rows = {}
    for g in labs + [f"kein Swing-Tief (<= {LOOKBACK} HT)"]:
        m = t.Lage == g
        if m.any():
            k = kennz(t.R[m]); k["Anteil"] = m.mean(); k["Ø R 5J"] = t.R[m & (t.Datum >= ab5)].mean(); rows[g] = k
    T2 = pd.DataFrame(rows).T
    T2.index.name = "Lage ATR-Stop"

    # M2b Strukturstop
    s = t[t.R_S.notna()].copy()
    geaendert = s.stop_b_atr > 1.5 + 1e-9
    rows = {}
    for lab, m in (("alle", pd.Series(True, index=s.index)), ("Stop geaendert", geaendert), ("Stop gleich", ~geaendert)):
        x = s[m]
        rows[lab] = {"n": len(x), "Ø Stopabstand ATR": x.stop_b_atr.mean(), "P90 Stopabstand ATR": x.stop_b_atr.quantile(0.9),
                     "Ø R ATR-Stop": x.R.mean(), "Ø R Strukturstop": x.R_S.mean(), "Δ gepaart": (x.R_S - x.R).mean(),
                     "SE Δ": se(x.R_S - x.R), "voller Stop ATR": (x.R <= -0.9).mean(), "voller Stop Struktur": (x.R_S <= -0.9).mean(),
                     "Δ 5J": (x.R_S - x.R)[x.Datum >= ab5].mean()}
    T3 = pd.DataFrame(rows).T
    T3.index.name = "Trades"
    sb = s.copy()
    sb["R"] = sb.R_S; sb["Exit"] = sb.Exit_S; sb["rest"] = sb.rest_S
    sb["riskp"] = sb.stop_b_atr * sb.ATRp
    sb = _chf_deckel(sb).reset_index(drop=True)
    T3b = pd.DataFrame({"ATR-Stop (LS-2 heute)": pf_kennz(P["alle Signale (LS-2 heute)"], jahre, ab5),
                        "Strukturstop": pf_kennz(pf(sb), jahre, ab5)}).T
    T3b.index.name = "Portfolio (3 R a 50 EUR)"

    L += ["## Aktien: LS-2-Signale", "",
          f"Signale {t.Datum.min():%Y-%m-%d} bis {ende:%Y-%m-%d}, {t.Symbol.nunique()} Werte, n = {len(t)} "
          f"(Live-Variante B). Zufall: 3 % der Trendtage je Wert, gleiche Simulation.", "",
          "### M1 Treppen-Flag je Signal", "", tab(T1), "",
          "### M1 Treppen-Flag im Portfolio", "", tab(T1b, {"EUR/J": "{:.0f}", "EUR/J 5J": "{:.0f}"}), "",
          "### M2a Lage des ATR-Stops zum letzten Swing-Tief", "", tab(T2), "",
          "### M2b Strukturstop min(ATR-Stop, Swing-Tief - 0,5 ATR)", "", tab(T3), "",
          tab(T3b, {"EUR/J": "{:.0f}", "EUR/J 5J": "{:.0f}"}), ""]
    t.drop(columns=["rest", "rest_A", "rest_B", "rest_S"]).to_csv(Path(a.out) / "struktur_flag_aktien.csv", index=False)


# ------------------------------------------------------------------ Krypto
def laden_krypto(cache: Path) -> dict[str, pd.DataFrame]:
    """Wie krypto_lernspur.laden (Branch research/krypto-lernspur-2026-11-12), zusaetzlich High/Low."""
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import yfinance as yf
    data = {}
    for s in COINS:
        for _ in range(3):
            try:
                d = yf.download(s, start="2014-01-01", auto_adjust=True, progress=False)
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(0)
                d = d[["Open", "High", "Low", "Close"]].dropna()
                d = d[(d > 0).all(axis=1)]
                d.index = pd.DatetimeIndex(d.index).tz_localize(None)
                d = d[~d.index.duplicated()].asfreq("D").ffill()
                if len(d) > 400:
                    data[s] = d
                break
            except Exception as e:  # noqa: BLE001
                print("Fehler", s, e, flush=True)
                time.sleep(3)
        time.sleep(1)
    print("Coins geladen:", len(data), flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(data))
    return data


def krypto(a, L: list[str]) -> None:
    D = laden_krypto(Path(a.cache_krypto))
    rows, stand = [], []
    for s, d in D.items():
        H, Lo, C = d.High.to_numpy(float), d.Low.to_numpy(float), d.Close.to_numpy(float)
        st, kl = treppe(H, Lo)
        hoch50 = pd.Series(C).rolling(50).max().shift(1).to_numpy()
        ueber = C > hoch50
        don = ueber & ~np.r_[False, ueber[:-1]]
        f20 = np.r_[C[20:] / C[:-20] - 1, np.full(20, np.nan)]
        f60 = np.r_[C[60:] / C[:-60] - 1, np.full(60, np.nan)]
        for j in range(260, len(C)):
            rows.append((s, d.index[j], st[j], bool(don[j]), f20[j], f60[j]))
        if s in ("BTC-USD", "ETH-USD"):
            kh = swing_idx(H, True)
            kh = kh[kh + N <= len(H) - 1][-2:]
            kl2 = kl[kl + N <= len(H) - 1][-2:]
            stand.append(f"- {s.split('-')[0]} am {d.index[-1]:%Y-%m-%d}: Treppe {TREPPE.get(st[-1], 'ohne Historie')}, "
                         f"Schluss {C[-1]:,.0f}; letzte Swing-Hochs "
                         + ", ".join(f"{H[k]:,.0f} ({d.index[k]:%Y-%m-%d})" for k in kh)
                         + "; letzte Swing-Tiefs " + ", ".join(f"{Lo[k]:,.0f} ({d.index[k]:%Y-%m-%d})" for k in kl2))
    k = pd.DataFrame(rows, columns=["Coin", "Datum", "treppe", "donchian", "f20", "f60"])
    k["Treppe"] = k.treppe.map(TREPPE).fillna("ohne Historie")
    k = k[k.Datum >= "2018-01-01"]

    def block(x: pd.DataFrame) -> pd.DataFrame:
        out = {}
        for g in ("aufwaerts", "gemischt", "abwaerts"):
            y = x[x.Treppe == g]
            if len(y):
                out[g] = {"n": len(y), "Anteil": len(y) / len(x), "Ø 20T": y.f20.mean(), "Median 20T": y.f20.median(),
                          "20T > 0": (y.f20.dropna() > 0).mean(), "Ø 60T": y.f60.mean(), "Median 60T": y.f60.median(),
                          "60T > 0": (y.f60.dropna() > 0).mean()}
        out["alle"] = {"n": len(x), "Anteil": 1.0, "Ø 20T": x.f20.mean(), "Median 20T": x.f20.median(),
                       "20T > 0": (x.f20.dropna() > 0).mean(), "Ø 60T": x.f60.mean(), "Median 60T": x.f60.median(),
                       "60T > 0": (x.f60.dropna() > 0).mean()}
        T = pd.DataFrame(out).T
        T.index.name = "Treppe"
        return T

    fmt = {c: "{:+.1%}" for c in ("Ø 20T", "Median 20T", "Ø 60T", "Median 60T")}
    fmt.update({c: "{:.0%}" for c in ("Anteil", "20T > 0", "60T > 0")})
    L += ["## Krypto: Vorwaertsrenditen je Treppe", "",
          f"{k.Coin.nunique()} Coins, Tagesschluss USD, ab 2018. Renditen ueberlappen, Standardfehler darum nicht angegeben.", ""]
    for lab, m in (("alle Coins, alle Tage", k.Coin.notna()), ("alle Coins, Donchian-Einstiege", k.donchian),
                   ("BTC/ETH, alle Tage", k.Coin.isin(["BTC-USD", "ETH-USD"])),
                   ("BTC/ETH, Donchian-Einstiege", k.Coin.isin(["BTC-USD", "ETH-USD"]) & k.donchian)):
        for von in ("2018-01-01", "2022-01-01"):
            x = k[m & (k.Datum >= von)]
            if len(x):
                L += [f"### {lab}, ab {von[:4]}", "", tab(block(x), fmt), ""]
    L += ["### Stand heute (Kontrolle)", ""] + stand + [""]
    k.to_csv(Path(a.out) / "struktur_flag_krypto.csv", index=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl")
    ap.add_argument("--cache-krypto", default="work/krypto_lernspur.pkl")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    L = ["# Struktur-Flag und Strukturstop (Messung 2026-11-14)", "",
         "Reine Messung, aendert keine Regel. Protokoll im Kopf von research/struktur_flag.py. "
         "Survivorship-Bias, Aktien ohne Kosten und Steuern.", ""]
    aktien(a, L)
    krypto(a, L)
    (Path(a.out) / "STRUKTUR_FLAG.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
