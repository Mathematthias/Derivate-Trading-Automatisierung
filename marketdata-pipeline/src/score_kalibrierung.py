"""score_kalibrierung.py — Messung fuer L12/L23 (User-Auftrag 2026-10-09).

FRAGE
    Trennt der Entry-Score (L23: Kommazahl, GO ab 5,0) gute von schlechten Trades,
    und verdient das Score-Sizing (L12: >=5,0 -> 1 %, >=6,0 -> 2 %, >=6,5 -> 3 %)
    mehr als ein flaches 1 %? Bis 2026-10-09 war das nie gemessen.

BEFUND BEIM BAU (Journal 20261009, 47 Trades im Trade-Audit)
    Nur 6 Trades tragen einen Score in den Notizen, 25 ein dokumentiertes Risiko
    in % RK — fast alle bei ~1 %. Score-Sizing wurde praktisch nie ausgeuebt.
    Rueckwirkend ist L12 also nicht pruefbar; die Messung zaehlt ab jetzt.

EINGABE  state/trade_audit.csv mit den Spalten
    Score        Kommazahl 0-7 (Summe der Achsen 0/0,5/1), beim Entry festgehalten
    Sizing_Pct   tatsaechliches Risiko in % RK beim Entry (Max-Verlust / 15.000 x 100)
    Score_Quelle "Entry" (beim Kauf festgehalten) | "Journal-Notiz" (nachgetragen) |
                 "alt X/7" (alte Zaehlschreibweise, nur bedingt vergleichbar)
    R            Ergebnis in R (schon vorhanden)
    optional state/mfe_mae.csv fuer MFE_R / Klasse.

AUSGABE  Markdown fuer den 20er-Block-Review:
    1. Abdeckung (wie viele Trades sind ueberhaupt messbar)
    2. Score-Baender: n, Trefferquote mit Wilson-95-%, Mittel/Median R, Mittel MFE
    3. Spearman-Rangkorrelation Score <-> R
    4. Gegenrechnung: Score-Sizing gegen flaches 1 % (Summe R x Gewicht)
    5. Einstiegsqualitaet (Weg 3, User-Entscheid 2026-10-09): je Einstiegsart und
       Setup_Klasse n, Einstiegsfehler-Quote (MFE-Klasse "Einstiegsfehler"), Treffer,
       Mittel R. Entscheidet L27 bei n >= 20 je Einstiegsart und geht mit dem
       Exit-Test in den 20er-Review.
    Urteil erst ab n >= 20 (L28), vorher nur Prozessbefund.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Optional

import pandas as pd

BAENDER = [("< 5,0 (kein GO)", None, 5.0), ("5,0-5,5 (1 %)", 5.0, 6.0),
           ("6,0 (2 %)", 6.0, 6.5), (">= 6,5 (3 %)", 6.5, None)]
URTEIL_AB_N = 20


def gewicht(score: float) -> float:
    """Sizing-Gewicht relativ zu 1 % nach L12."""
    if score >= 6.5:
        return 3.0
    if score >= 6.0:
        return 2.0
    if score >= 5.0:
        return 1.0
    return 0.0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[Optional[float], Optional[float]]:
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def _zahl(x) -> Optional[float]:
    s = str(x or "").strip().replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def lade(audit_csv: Path, mfe_csv: Optional[Path] = None) -> pd.DataFrame:
    df = pd.read_csv(audit_csv, dtype=str).fillna("")
    for col in ("Score", "Sizing_Pct", "Score_Quelle", "Einstiegsart", "Setup_Klasse", "Vol_Mult"):
        if col not in df.columns:
            df[col] = ""
    df["score"] = df["Score"].map(_zahl)
    df["sizing"] = df["Sizing_Pct"].map(_zahl)
    df["r"] = df["R"].map(_zahl)
    df["geschlossen"] = df["Verkauf"].str.strip() != ""
    if mfe_csv and Path(mfe_csv).exists():
        m = pd.read_csv(mfe_csv, dtype=str).fillna("")
        m = m[["TradeID"] + [c for c in ("MFE_R", "Klasse") if c in m.columns]]
        df = df.merge(m, on="TradeID", how="left")
        df["mfe"] = df.get("MFE_R", pd.Series(dtype=str)).map(_zahl)
    else:
        df["mfe"] = None
    if "Klasse" not in df.columns:
        df["Klasse"] = ""
    df["Klasse"] = df["Klasse"].fillna("")
    return df


def spearman(x: list[float], y: list[float]) -> Optional[float]:
    if len(x) < 3:
        return None
    rx = pd.Series(x).rank()
    ry = pd.Series(y).rank()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(rx.corr(ry))


def auswerten(df: pd.DataFrame) -> dict:
    zu = df[df["geschlossen"] & df["r"].notna()]
    sc = zu[zu["score"].notna()]
    baender = []
    for name, lo, hi in BAENDER:
        b = sc
        if lo is not None:
            b = b[b["score"] >= lo]
        if hi is not None:
            b = b[b["score"] < hi]
        n = len(b)
        k = int((b["r"] > 0).sum())
        wl, wh = wilson(k, n)
        baender.append({"band": name, "n": n, "treffer": k, "quote": (k / n) if n else None,
                        "wilson": (wl, wh), "r_mittel": float(b["r"].mean()) if n else None,
                        "r_median": float(b["r"].median()) if n else None,
                        "mfe_mittel": float(pd.to_numeric(b["mfe"], errors="coerce").mean()) if n and "mfe" in b else None})
    rho = spearman(sc["score"].tolist(), sc["r"].tolist())
    flat = float(sc["r"].sum()) if len(sc) else 0.0
    gew = float(sum(r * gewicht(s) for s, r in zip(sc["score"], sc["r"]))) if len(sc) else 0.0
    ist = zu[zu["sizing"].notna()]
    return {"trades": len(zu), "gescort": len(sc), "mit_sizing": len(ist),
            "quellen": sc["Score_Quelle"].replace("", "unbekannt").value_counts().to_dict(),
            "baender": baender, "spearman": rho, "summe_flat_r": flat, "summe_score_sizing_r": gew,
            "sizing_verteilung": ist["sizing"].round(1).value_counts().sort_index().to_dict(),
            "urteil_moeglich": len(sc) >= URTEIL_AB_N}


def einstiegsqualitaet(df: pd.DataFrame) -> dict:
    """Einstiegsfehler-Quote je Einstiegsart und Setup-Klasse (geschlossene Trades mit R)."""
    zu = df[df["geschlossen"] & df["r"].notna()].copy()
    zu["efehler"] = zu["Klasse"].astype(str).str.startswith("Einstiegsfehler")
    if "Vol_Mult" not in zu.columns:
        zu["Vol_Mult"] = ""
    def _grp(col):
        out = []
        for k, g in zu.groupby(zu[col].replace("", "unklar")):
            n = len(g)
            out.append({"gruppe": k, "n": n, "efehler": int(g["efehler"].sum()),
                        "treffer": int((g["r"] > 0).sum()), "r_mittel": float(g["r"].mean())})
        return sorted(out, key=lambda x: -x["n"])
    # 2026-10-09: Volumen am Ausbruchstag (Boden 1,0 / Daempfer 1,3) — nur Trades mit Wert
    vm = zu["Vol_Mult"].map(_zahl) if "Vol_Mult" in zu.columns else pd.Series(dtype=float)
    zu["vol_band"] = [("" if v is None or (isinstance(v, float) and math.isnan(v))
                       else ("1,0-1,3 (gedaempft)" if v < 1.3 else ">= 1,3")) for v in vm]
    return {"einstiegsart": _grp("Einstiegsart"), "setup_klasse": _grp("Setup_Klasse"),
            "vol_band": [g for g in _grp("vol_band") if g["gruppe"] != "unklar"],
            "gesamt": len(zu), "efehler_gesamt": int(zu["efehler"].sum())}


def _p(x: Optional[float]) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.0f} %"


def _r(x: Optional[float]) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.2f}".replace(".", ",")


def render(res: dict, stichtag: str = "") -> str:
    z = [f"# Score-Kalibrierung L12/L23{(' — ' + stichtag) if stichtag else ''}", ""]
    z.append(f"Geschlossene Trades mit R: **{res['trades']}**, davon mit Score: **{res['gescort']}**, "
             f"mit dokumentiertem Risiko: {res['mit_sizing']}.")
    if res["quellen"]:
        z.append("Score-Quellen: " + ", ".join(f"{k} {v}" for k, v in res["quellen"].items()) + ".")
    if not res["urteil_moeglich"]:
        z.append(f"\n**Kein Urteil (L28):** {res['gescort']} von mindestens {URTEIL_AB_N} gescorten Trades. "
                 "Die Tabelle ist ein Zwischenstand, keine Evidenz.")
    z += ["", "| Score-Band | n | Treffer | Quote | Wilson 95 % | Ø R | Median R | Ø MFE |",
          "|---|---|---|---|---|---|---|---|"]
    for b in res["baender"]:
        wl, wh = b["wilson"]
        wi = "—" if wl is None else f"{wl * 100:.0f}–{wh * 100:.0f} %"
        z.append(f"| {b['band']} | {b['n']} | {b['treffer']} | {_p(b['quote'])} | {wi} | {_r(b['r_mittel'])} | "
                 f"{_r(b['r_median'])} | {_r(b['mfe_mittel'])} |")
    rho = res["spearman"]
    z += ["", f"Spearman ρ (Score ↔ R): **{'—' if rho is None else f'{rho:+.2f}'.replace('.', ',')}** "
          f"(n = {res['gescort']}). Faustregel: |ρ| < 0,3 trennt praktisch nicht; erst ab n ≥ 20 deuten.",
          "", f"Gegenrechnung Sizing: flach 1 % = {_r(res['summe_flat_r'])} R, "
          f"Score-Sizing (1/2/3 %, < 5,0 = 0) = {_r(res['summe_score_sizing_r'])} R-Einheiten à 1 %. "
          "Liegt Score-Sizing nicht klar darueber, verdient die Staffel ihr Risiko nicht."]
    eq = res.get("einstieg")
    if eq:
        z += ["", "## Einstiegsqualität (Weg 3)", "",
              f"Einstiegsfehler (MFE < 0,5 R bei MAE ≥ 0,8 R) insgesamt: {eq['efehler_gesamt']} von {eq['gesamt']}. "
              f"Entscheid zu L27 erst bei n ≥ {URTEIL_AB_N} je Einstiegsart."]
        for titel, key in (("Einstiegsart", "einstiegsart"), ("Setup-Klasse", "setup_klasse"),
                           ("Ausbruchs-Volumen (seit 2026-10-09)", "vol_band")):
            if not eq.get(key):
                continue
            z += ["", f"| {titel} | n | Einstiegsfehler | Quote | Treffer | Ø R |", "|---|---|---|---|---|---|"]
            for g in eq[key]:
                z.append(f"| {g['gruppe']} | {g['n']} | {g['efehler']} | {_p(g['efehler'] / g['n'])} | "
                         f"{g['treffer']} | {_r(g['r_mittel'])} |")
    if res["sizing_verteilung"]:
        z += ["", "Tatsaechliches Risiko je Trade (% RK → Anzahl): " +
              ", ".join(f"{k:g} → {v}" for k, v in res["sizing_verteilung"].items())]
    return "\n".join(z) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit-csv", default="state/trade_audit.csv")
    ap.add_argument("--mfe-csv", default="state/mfe_mae.csv")
    ap.add_argument("--md", default=None, help="Markdown in Datei schreiben (sonst stdout)")
    ap.add_argument("--stichtag", default="")
    a = ap.parse_args(argv)
    df = lade(Path(a.audit_csv), Path(a.mfe_csv) if a.mfe_csv else None)
    res = auswerten(df)
    res["einstieg"] = einstiegsqualitaet(df)
    txt = render(res, a.stichtag)
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(txt, encoding="utf-8")
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
