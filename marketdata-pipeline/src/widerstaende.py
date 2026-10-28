"""widerstaende.py — horizontale Widerstands-/Unterstuetzungszonen mit Staerkeklasse.

User-Entscheid 2026-10-28 („A und C jetzt“): TP1 liegt am ersten STARKEN Widerstand,
mittlere und schwache Marken bis dorthin sind Flags. Dieses Modul liefert den
Vorschlag (Variante C, Hybrid): die Zeile traegt das Etikett von Hand, der
Morning Check gleicht es gegen diese Zonen ab. Gewichte sind gesetzt, nicht
gemessen — die Messung laeuft ueber trade_audit/mfe_mae (L24).

Verfahren (Tagesbalken):
  1. Pivot-Hochs/-Tiefs: Hoch (Tief) ist Extremwert im Fenster +/- PIVOT_K Balken,
     ueber die letzten LOOKBACK_HT Balken. Je Pivot die Reaktion (Gegenbewegung in
     den REAKTION_HT Folgebalken, in ATR).
  2. Wochen-Pivots (+/- 2 Wochen) ueber die ganze Historie.
  3. Pivots per Single-Linkage zu Zonen buendeln (Abstand <= CLUSTER_ATR x ATR).
  4. Punktwert je Zone:
       Beruehrungen = max(Pivots, Abpraller-Ereignisse) >= 2: +2
       Rollentausch (Pivot auf der anderen Seite, danach Schluss >= 0,5 ATR jenseits): +2
       staerkste Reaktion >= 3 ATR: +1
       Wochen-Pivot in der Zone: +1
       52W-Hoch/-Tief in der Zone: +2
       EMA200 in der Zone: +1
       runde Zahl in der Zone: +1
     Klasse: >= 4 stark, 2-3 mittel, sonst schwach; eine Einzelmarke (n < 2) ohne 52W
     ist hoechstens mittel. Zonen hoechstens 1 ATR breit (Kalibrierung 2026-10-28).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

PIVOT_K = 3
LOOKBACK_HT = 252
REAKTION_HT = 10
CLUSTER_ATR = 0.5
RAND_ATR = 0.25           # Toleranz fuer 52W/EMA200/runde Zahl an der Zone
MAX_DIST_ATR = 8.0
MAX_ZONEN = 8
KLASSE_STARK = 4
KLASSE_MITTEL = 2
# Kalibrierung 2026-10-28 (erster Lauf: fast alles "stark", CAP-Doppeltop 127,3 nur schwach)
MAX_BREITE_ATR = 1.0      # Zone hoechstens 1 ATR breit (keine Verkettung in Seitwaertsphasen)
BRUCH_ATR = 0.5           # Rollentausch nur nach Schluss >= 0,5 ATR jenseits der Zone
ABPRALL_TOL_ATR = 0.15    # Abpraller: Hoch (Tief) bis 0,15 ATR an die Zone, Schluss diesseits


def _rundung(preis: float) -> float:
    """Schrittweite runder Zahlen: halbe Zehnerpotenz (247 -> 50, 35 -> 5, 1.2 -> 0.5)."""
    if preis <= 0:
        return 0.0
    return 10 ** math.floor(math.log10(preis)) / 2.0


def _pivots(high: np.ndarray, low: np.ndarray, k: int) -> list[tuple[int, str, float]]:
    out = []
    n = len(high)
    for i in range(k, n - k):
        hw = high[i - k:i + k + 1]
        lw = low[i - k:i + k + 1]
        if high[i] == hw.max() and (hw == high[i]).sum() == 1:
            out.append((i, "H", float(high[i])))
        if low[i] == lw.min() and (lw == low[i]).sum() == 1:
            out.append((i, "T", float(low[i])))
    return out


def zonen(df: pd.DataFrame, preis: float, atr: Optional[float],
          ema200: Optional[float] = None, hoch_52w: Optional[float] = None,
          tief_52w: Optional[float] = None) -> Optional[dict]:
    """{"ueber": [...], "unter": [...]} — je Zone lo, hi, level, klasse, score, gruende, dist_atr.
    None bei zu wenig Daten oder ohne ATR."""
    if df is None or atr is None or atr <= 0 or preis is None or preis <= 0:
        return None
    if not {"High", "Low", "Close"} <= set(df.columns) or len(df) < 30:
        return None
    d = df.tail(LOOKBACK_HT)
    hi = d["High"].to_numpy(dtype=float)
    lo = d["Low"].to_numpy(dtype=float)
    if np.isnan(hi).any() or np.isnan(lo).any():
        d = d.dropna(subset=["High", "Low"])
        hi = d["High"].to_numpy(dtype=float)
        lo = d["Low"].to_numpy(dtype=float)
    piv = _pivots(hi, lo, PIVOT_K)
    if not piv:
        return {"ueber": [], "unter": []}

    # Reaktion je Pivot in ATR (Gegenbewegung in den Folgebalken)
    punkte = []
    for i, art, p in piv:
        j = min(len(hi), i + 1 + REAKTION_HT)
        if i + 1 >= j:
            reakt = 0.0
        elif art == "H":
            reakt = (p - float(lo[i + 1:j].min())) / atr
        else:
            reakt = (float(hi[i + 1:j].max()) - p) / atr
        punkte.append({"preis": p, "art": art, "reakt": max(0.0, reakt), "i": i})

    # Wochen-Pivots
    wochen = []
    try:
        w = df.resample("W-FRI").agg({"High": "max", "Low": "min"}).dropna()
        for _, art, p in _pivots(w["High"].to_numpy(dtype=float), w["Low"].to_numpy(dtype=float), 2):
            wochen.append(p)
    except Exception:  # noqa: BLE001 — Index ohne Datum (Tests) oder Luecken
        pass

    # Single-Linkage-Cluster nach Preis
    punkte.sort(key=lambda x: x["preis"])
    cluster, akt = [], [punkte[0]]
    for q in punkte[1:]:
        if (q["preis"] - akt[-1]["preis"] <= CLUSTER_ATR * atr
                and q["preis"] - akt[0]["preis"] <= MAX_BREITE_ATR * atr):
            akt.append(q)
        else:
            cluster.append(akt)
            akt = [q]
    cluster.append(akt)
    cl = d["Close"].to_numpy(dtype=float) if "Close" in d.columns else None

    schritt = _rundung(preis)
    ueber, unter = [], []
    for c in cluster:
        z_lo = min(q["preis"] for q in c)
        z_hi = max(q["preis"] for q in c)
        level = float(np.median([q["preis"] for q in c]))
        oben = level > preis
        score, gr = 0, []
        rand = RAND_ATR * atr
        # Beruehrungen = max(Pivots, Abpraller-Ereignisse) — Abpraller fangen Doppeltops,
        # deren Hochs naeher als +/- PIVOT_K Balken beieinander liegen (Anlass CAP 127,3)
        abpr = 0
        if cl is not None:
            tol = ABPRALL_TOL_ATR * atr
            letzte = -10
            for j in range(len(hi)):
                if oben:
                    treffer = hi[j] >= z_lo - tol and cl[j] < z_lo
                else:
                    treffer = lo[j] <= z_hi + tol and cl[j] > z_hi
                if treffer:
                    if j - letzte > 1:
                        abpr += 1
                    letzte = j
        n = max(len(c), abpr)
        if n >= 3:
            score += 2; gr.append(f"{n}x")
        elif n == 2:
            score += 2; gr.append("2x")
        # Rollentausch: Zone hielt erst auf der anderen Seite und wurde danach per Schluss
        # deutlich (>= BRUCH_ATR) durchbrochen
        rt = False
        if cl is not None:
            for q in c:
                if oben and q["art"] == "T":
                    nach = cl[q["i"] + 1:]
                    rt = rt or bool(len(nach) and (nach < z_lo - BRUCH_ATR * atr).any())
                if (not oben) and q["art"] == "H":
                    nach = cl[q["i"] + 1:]
                    rt = rt or bool(len(nach) and (nach > z_hi + BRUCH_ATR * atr).any())
        if rt:
            score += 2; gr.append("Rollentausch")
        rmax = max(q["reakt"] for q in c)
        if rmax >= 3:
            score += 1; gr.append(f"Reaktion {rmax:.1f} ATR")
        if any(z_lo - rand <= p <= z_hi + rand for p in wochen):
            score += 1; gr.append("Woche")
        ext = False
        if oben and hoch_52w is not None and z_lo - rand <= hoch_52w <= z_hi + rand:
            score += 2; gr.append("52W-Hoch"); ext = True
        if (not oben) and tief_52w is not None and z_lo - rand <= tief_52w <= z_hi + rand:
            score += 2; gr.append("52W-Tief"); ext = True
        if ema200 is not None and z_lo - rand <= ema200 <= z_hi + rand:
            score += 1; gr.append("EMA200")
        if schritt > 0:
            r = round(level / schritt) * schritt
            if z_lo - rand <= r <= z_hi + rand:
                score += 1; gr.append(f"rund {r:g}")
        klasse = "stark" if score >= KLASSE_STARK else ("mittel" if score >= KLASSE_MITTEL else "schwach")
        if klasse == "stark" and n < 2 and not ext:
            klasse = "mittel"          # Einzelmarke ohne 52W nie "stark"
        im_kurs = z_lo <= preis <= z_hi
        dist = ((z_lo - preis) if oben else (preis - z_hi)) / atr
        if dist > MAX_DIST_ATR:
            continue
        z = {"lo": round(z_lo, 4), "hi": round(z_hi, 4), "level": round(level, 4), "klasse": klasse,
             "score": score, "gruende": gr, "dist_atr": round(dist, 2), "im_kurs": im_kurs}
        (ueber if oben else unter).append(z)
    ueber.sort(key=lambda z: z["level"])
    unter.sort(key=lambda z: -z["level"])
    return {"ueber": ueber[:MAX_ZONEN], "unter": unter[:MAX_ZONEN]}
