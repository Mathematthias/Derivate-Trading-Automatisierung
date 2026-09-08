"""Prueft die 4h-Abdeckung, BEVOR `intraday_4h.evaluate_reverse` scharfgestellt wird.

Der Layer wurde am 2026-09-08 gegen synthetische Daten gebaut und getestet; die
tatsaechliche Yahoo-Intraday-Abdeckung je Boerse ist damit NICHT verifiziert.
Dieses Skript beantwortet genau drei Fragen fuer das reale Universum:

  1. Fuer wie viele Symbole liefert Yahoo ueberhaupt 1h-Balken?
  2. Wie viele davon haben genug Historie fuer EMA50-4h und RSI-14-4h?
  3. Passen die Blockzeiten zu den erwarteten Session-Startzeiten?

Aufruf (aus marketdata-pipeline/):
    PYTHONPATH=src python3 scripts/verify_4h_coverage.py --tier b --limit 40

Erst wenn Spalte "auswertbar" fuer die relevanten Boersen hoch genug ist, darf
`evaluate_reverse: true` gesetzt werden — sonst kippen Zeilen von BEREIT* nach
NAHE, weil Daten fehlen und nicht, weil das Setup schlechter ist.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from intraday_4h import pull_4h  # noqa: E402


def load_symbols(tier: str) -> list[str]:
    cfg_path = Path(__file__).resolve().parents[1] / "config" / f"tickers_tier_{tier}.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    syms: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
        elif isinstance(o, str) and o and not o.islower() and " " not in o:
            syms.add(o)

    walk(cfg.get("categories", cfg))
    return sorted(syms)


def suffix(sym: str) -> str:
    return sym.rsplit(".", 1)[1] if "." in sym else "US"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="b", choices=["a", "b", "c"])
    ap.add_argument("--limit", type=int, default=0, help="0 = alle")
    ap.add_argument("--period", default="60d")
    args = ap.parse_args()

    syms = load_symbols(args.tier)
    if args.limit:
        syms = syms[: args.limit]
    print(f"Pruefe {len(syms)} Symbole aus tier_{args.tier} (period={args.period}) ...\n")

    res = pull_4h(syms, period=args.period)

    per_suffix: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    start_hours: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for sym, ind in res.items():
        sfx = suffix(sym)
        per_suffix[sfx]["gesamt"] += 1
        if ind.bars_available:
            per_suffix[sfx]["mit_daten"] += 1
        # EMA50 braucht 50 Balken, RSI-Signal 14+14
        if ind.ema50 is not None and ind.rsi14_signal is not None:
            per_suffix[sfx]["auswertbar"] += 1
        if ind.bar_time:
            start_hours[sfx][ind.bar_time[11:16]] += 1

    print(f"{'Boerse':10}{'gesamt':>8}{'mit Daten':>11}{'auswertbar':>12}{'Quote':>8}")
    for sfx in sorted(per_suffix, key=lambda k: -per_suffix[k]["gesamt"]):
        c = per_suffix[sfx]
        q = c["auswertbar"] / c["gesamt"] * 100 if c["gesamt"] else 0
        print(f"{sfx:10}{c['gesamt']:>8}{c['mit_daten']:>11}{c['auswertbar']:>12}{q:>7.0f}%")

    print("\nBlock-Startzeiten des letzten geschlossenen 4h-Balkens je Boerse")
    print("(erwartet: XETRA/DE 09:00|13:00|17:00, NYSE/US 09:30|13:30)")
    for sfx in sorted(start_hours):
        top = ", ".join(f"{t} ({n})" for t, n in start_hours[sfx].most_common(4))
        print(f"  {sfx:8} {top}")

    ok = sum(c["auswertbar"] for c in per_suffix.values())
    tot = sum(c["gesamt"] for c in per_suffix.values())
    print(f"\nGESAMT auswertbar: {ok}/{tot} ({ok/tot*100:.0f}%)" if tot else "\nkeine Daten")
    print("\nEmpfehlung: evaluate_reverse erst auf true setzen, wenn die Quote fuer")
    print("die tatsaechlich getradeten Boersen ueber ~90 %% liegt UND die Startzeiten")
    print("zu den Session-Eroeffnungen passen. Sonst kippen Zeilen aus Datenmangel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
