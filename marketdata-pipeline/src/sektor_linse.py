"""Sektor-Linse (2026-10-19) — reine Messung, kein Gate, keine Pitches.

Anlass: Am 2026-10-19 lagen Halbleiter 30–37 % und Software 18–21 % unter dem
52W-Hoch (SOX -11,4 % in KW42), der Nasdaq dagegen nur 5,7 % mit bullischem
Stack und 4 % über der EMA200. Der Morning Check sah 18 Einzelwerte mit
beschädigtem Trend, aber nirgends die Aussage „Cluster korrigiert bei
intaktem Index-Trend". Diese Linse schließt die Lücke als MESSUNG.

Bewusst NICHT: Entry-Signal, Gate oder Pitch. Die Reversal-Klasse wurde am
2026-10-04 mit Daten gestrichen; eine scharfe Sektor-Lane würde sie durch die
Hintertür zurückholen. Erst bei n ≥ 20 Signaltagen (L24) wird ausgewertet, ob
`signal` etwas taugt — Datenbasis sind die archivierten Digests.

Rechnet je Cluster aus dem kompakten `universe`-Block des Digests (Felder
kurs, atr, ema20/50/100/200, stack, dist52wH, move30d, chg). Mitglieder ohne
Daten zählen nicht; `n` sagt, wie viele wirklich gemessen wurden.
"""
from __future__ import annotations

from statistics import median
from typing import Any, Optional

# Cluster-Listen sind bewusst breiter als das heutige Tier-A-Universum: die
# Linse nimmt die Schnittmenge, wächst also mit, wenn Ticker dazukommen.
CLUSTER: dict[str, tuple[str, ...]] = {
    "halbleiter": ("NVDA", "AMD", "AVGO", "MU", "QCOM", "TXN", "INTC", "AMAT",
                   "LRCX", "KLAC", "MRVL", "ADI", "NXPI", "MCHP", "ON", "ARM",
                   "TSM", "ASML.AS", "ASM.AS", "BESI.AS", "STMPA.PA", "IFX.DE"),
    "software": ("CRM", "NOW", "SNOW", "ADBE", "PANW", "CRWD", "NET", "DDOG",
                 "PLTR", "ORCL", "INTU", "WDAY", "TEAM", "ZS", "FTNT", "MDB",
                 "ADSK", "CDNS", "SNPS", "SAP.DE", "DSY.PA", "CAP.PA", "GFT.DE",
                 "NEM.DE"),
    "mega_caps": ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "TSLA"),
    "ai_netz_hw": ("ANET", "CSCO", "DELL", "SMCI", "HPE", "NBIS", "CRWV", "VRT"),
}
BENCHMARK = "^IXIC"

# Schwellen (Messdefinition, nicht Handelsregel):
TIEF_ATR = 2.0          # „tief": Kurs mehr als 2 ATR unter der EMA20
ANKER_ATR = 0.5         # Kurs ≤ 0,5 ATR an EMA100/EMA200 = tiefer Anker
SIGNAL_ANTEIL = 0.4     # Anteil „tief" im Cluster, ab dem `signal` gesetzt wird
MIN_N = 4               # darunter kein Signal (Stichprobe trägt es nicht)


def _num(x: Any) -> Optional[float]:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _median(xs: list[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(median(xs), 2) if xs else None


def _benchmark_lage(universe: dict[str, Any]) -> dict[str, Any]:
    b = universe.get(BENCHMARK) or {}
    kurs, e200 = _num(b.get("kurs")), _num(b.get("ema200"))
    return {
        "symbol": BENCHMARK,
        "stack": b.get("stack"),
        "ueber_ema200": (kurs > e200) if (kurs is not None and e200 is not None) else None,
        "dist52wH": _num(b.get("dist52wH")),
    }


def _mitglied(sym: str, v: dict[str, Any]) -> Optional[dict[str, Any]]:
    kurs, atr = _num(v.get("kurs")), _num(v.get("atr"))
    e = {k: _num(v.get(k)) for k in ("ema20", "ema50", "ema100", "ema200")}
    if not kurs or not atr or any(x is None for x in e.values()):
        return None
    d20 = (kurs - e["ema20"]) / atr
    anker = None
    if (v.get("stack") or "").lower() == "bullish":
        for k in ("ema100", "ema200"):
            if abs(kurs - e[k]) / atr <= ANKER_ATR:
                anker = k.upper()
                break
    return {
        "symbol": sym,
        "d_ema20_atr": round(d20, 2),
        "ueber_emas": sum(kurs > e[k] for k in e),
        "tief": d20 < -TIEF_ATR,
        "anker": anker,
        "dist52wH": _num(v.get("dist52wH")),
        "move30d": _num(v.get("move30d")),
        "chg": _num(v.get("chg")),
    }


def sektor_linse(universe: dict[str, Any]) -> dict[str, Any]:
    """Messblock je Cluster. Rückgabe ist JSON-fähig und stabil sortiert."""
    bench = _benchmark_lage(universe)
    index_intakt = bench["stack"] == "bullish" and bench["ueber_ema200"] is True
    cluster_out: dict[str, Any] = {}
    for name, tickers in CLUSTER.items():
        m = [x for x in (_mitglied(s, universe[s]) for s in tickers if s in universe) if x]
        n = len(m)
        n_tief = sum(x["tief"] for x in m)
        anteil = round(n_tief / n, 2) if n else None
        cluster_out[name] = {
            "n": n,
            "n_tief": n_tief,
            "anteil_tief": anteil,
            "median_d_ema20_atr": _median([x["d_ema20_atr"] for x in m]),
            "median_dist52wH": _median([x["dist52wH"] for x in m]),
            "median_move30d": _median([x["move30d"] for x in m]),
            "median_chg": _median([x["chg"] for x in m]),
            "tiefe_anker": sorted(f'{x["symbol"]}@{x["anker"]}' for x in m if x["anker"]),
            "signal": bool(n >= MIN_N and anteil is not None
                           and anteil >= SIGNAL_ANTEIL and index_intakt),
        }
    return {
        "modus": "messung",
        "def": {"tief_atr": TIEF_ATR, "anker_atr": ANKER_ATR,
                "signal_anteil": SIGNAL_ANTEIL, "min_n": MIN_N},
        "benchmark": bench,
        "index_intakt": index_intakt,
        "cluster": cluster_out,
    }
