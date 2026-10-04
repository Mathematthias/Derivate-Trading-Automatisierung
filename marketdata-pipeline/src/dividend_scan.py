"""
dividend_scan.py — wöchentlicher Dividende-×-Trend-Scan (seit 2026-10-04).

Sucht Aktien, die in den letzten zwölf Monaten mindestens `min_yield_ttm_pct`
Prozent TATSÄCHLICH ausgeschüttet haben UND im Aufwärtstrend stehen
(Kurs > EMA200, EMA50 > EMA200). Schreibt DIVIDEND-SCAN-{datetime}.md + .json
in den Briefing-Ordner. Der Morning-Check (Skill v48, Routine 7) rendert die
Treffer montags als Bucket 7, an den übrigen Tagen als Einzeiler.

ANLASS (Chat 2026-10-04): Frage nach weiteren Dividendenwerten im
Aufwärtstrend neben der SBLK-Position. Die Recherche zeigte zwei Dinge, die
dieser Job ins Design übernimmt:

  1. Hohe Rendite und Aufwärtstrend schließen sich meist aus — steigt der
     Kurs, fällt die Rendite. Beides zusammen gibt es fast nur bei Zyklikern
     mit variabler Ausschüttung (Tanker, Trockenmassengut). Deshalb die
     Klumpen-Bremse `max_per_cluster` und die Flags "Spitze"/"gekürzt".
  2. Die oft zitierte Rendite ist die hochgerechnete LETZTE Zahlung (SBLK:
     0,90 × 4 = 12 %). Gezahlt wurden in zwölf Monaten 1,88 USD = 6,3 %.
     Gefiltert wird auf die gezahlte (TTM), die Hochrechnung steht daneben.

ABGRENZUNG — was dieser Job NICHT tut:
  Er empfiehlt nichts und setzt keine Trigger. Ein Treffer ist ein Kandidat
  für die Watchlist (Trend-Pullback-Long-Geometrie), kein Entry. Die
  Dividende ist Filter, keine Renditequelle: am Ex-Tag fällt der Kurs um den
  Betrag, und die Ausschüttung landet im allgemeinen Topf.

Universum: Tier B (EU) + Tier C (NASDAQ-100) + config/dividend_pool.yaml,
ohne Ethik-Ausschlüsse. Pull in Batches (filter_config dividend_scan.batch_size),
jeder Batch einzeln gekapselt — ein ausgefallener Batch verkleinert den
Output, killt den Job aber nicht (Design wie catalyst_calendar_sync).

Aufruf-Modi:
  1. Produktiv (GitHub-Action):   python src/dividend_scan.py
     Erwartet GDRIVE_SA_KEY, BRIEFING_FOLDER_ID.
  2. Lokal (Trockentest):         python src/dividend_scan.py --output ./div.md
  3. Nur Pool, schneller Test:    python src/dividend_scan.py --nur-pool --output ./div.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
from typing import Any, Optional

import yaml

logger = logging.getLogger("dividend_scan")

FILENAME_PREFIX = "DIVIDEND-SCAN-"
KEEP_COUNT = 8
SCHEMA_VERSION = "dividend-scan/v1"

CONFIG_DIR = os.environ.get("CONFIG_DIR", "./config")

DEFAULT_PARAMS: dict[str, Any] = {
    "min_yield_ttm_pct": 5.0,
    "plausibel_max_yield_pct": 25.0,
    "min_ttm_count": 1,
    "min_volume_eur_avg_20d": 1_000_000,
    "anchor_atr": 1.0,
    "ext_gate_max": 2.0,
    "ex_hinweis_tage": 30,
    "spitze_ratio": 1.5,
    "kuerzung_ratio": 0.67,
    "max_per_cluster": 3,
    "top_n": 15,
    "rank_yield_cap_pct": 12.0,
    "beinahe_top_n": 5,
    "batch_size": 120,
}

# Ethik (SKILL.md § Ethik-Regel) — identisch zu catalyst_calendar_sync.
ETHIK_BLOCKLIST = {
    "RHM.DE", "RHM", "BA.L", "BAES", "LMT", "NOC", "GD", "RTX", "KNDS",
}


# ---------------------------------------------------------------------------
# Universum
# ---------------------------------------------------------------------------

def load_params(config_dir: str = CONFIG_DIR) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    path = os.path.join(config_dir, "filter_config.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        params.update(cfg.get("dividend_scan") or {})
    except FileNotFoundError:
        logger.warning("filter_config.yaml fehlt — Defaults")
    return params


def load_universe(config_dir: str = CONFIG_DIR, nur_pool: bool = False
                  ) -> dict[str, dict[str, Optional[str]]]:
    """{symbol: {"name", "cluster", "quelle"}} aus Tier B, Tier C und Pool.

    Pool-Einträge auf Symbolen, die schon in einem Tier stehen, ergänzen nur
    Name/Cluster. Ethik-Ausschlüsse fallen immer heraus.
    """
    uni: dict[str, dict[str, Optional[str]]] = {}
    excluded: set[str] = set(ETHIK_BLOCKLIST)

    if not nur_pool:
        for tier, fname in (("tier_b", "tickers_tier_b.yaml"),
                            ("tier_c", "tickers_tier_c.yaml")):
            path = os.path.join(config_dir, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except FileNotFoundError:
                logger.warning("%s fehlt — übersprungen", fname)
                continue
            for sym in data.get("ethik_excluded", []) or []:
                excluded.add(sym)
            container = data.get("categories", data)
            for section_name, section in container.items():
                if section_name == "ethik_excluded" or not isinstance(section, dict):
                    continue
                for name, sym in section.items():
                    if sym and sym not in uni:
                        uni[sym] = {"name": str(name), "cluster": None,
                                    "quelle": f"{tier}:{section_name}"}

    path = os.path.join(config_dir, "dividend_pool.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            pool = (yaml.safe_load(f) or {}).get("pool", []) or []
    except FileNotFoundError:
        logger.warning("dividend_pool.yaml fehlt — nur Tier-Universum")
        pool = []
    for e in pool:
        sym = (e or {}).get("symbol")
        if not sym:
            continue
        row = uni.setdefault(sym, {"name": None, "cluster": None, "quelle": "pool"})
        if e.get("name"):
            row["name"] = e["name"]
        if e.get("cluster"):
            row["cluster"] = e["cluster"]

    for sym in excluded:
        uni.pop(sym, None)
    return uni


# ---------------------------------------------------------------------------
# Bewertung (reine Funktionen — testbar ohne Netz)
# ---------------------------------------------------------------------------

def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    if x is None:
        return None
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def _stack(s: Any) -> str:
    e20, e50, e200 = s.ema20, s.ema50, s.ema200
    if None in (e20, e50, e200):
        return "neutral"
    if e20 > e50 > e200:
        return "bullish"
    if e20 < e50 < e200:
        return "bearish"
    return "neutral"


def trend_intakt(s: Any) -> bool:
    """Kurs > EMA200 und EMA50 > EMA200 — der Aufwärtstrend im Sinne des Scans.

    Bewusst NICHT der volle bullishe Stack: ein Pullback unter die EMA20 (oder
    knapp an die EMA50) ist im Aufwärtstrend genau der Einstiegsort, den
    Trend-Pullback-Long sucht. Gefiltert wird der übergeordnete Trend.
    """
    if s.ema50 is None or s.ema200 is None or s.price is None:
        return False
    return s.price > s.ema200 and s.ema50 > s.ema200


def bewerte(s: Any, meta: dict, p: dict, heute: dt.date) -> dict[str, Any]:
    """Eine Zeile mit allen Kennzahlen und Flags — unabhängig vom Filter."""
    y = getattr(s, "div_yield_ttm_pct", None)
    cad = getattr(s, "div_cadence_days", None)
    last_amt = getattr(s, "last_ex_div_amount", None)
    ttm = getattr(s, "div_ttm", None)

    fwd_y = None
    ratio = None
    if last_amt and cad and s.price:
        # Zahlungen pro Jahr als ganze Zahl (91 → 4, 182 → 2, 365 → 1) —
        # 365/91 = 4,01 würde die Hochrechnung um 0,3 % verfälschen.
        pro_jahr = max(1, round(365.0 / cad))
        fwd_y = last_amt * pro_jahr / s.price * 100.0
        if ttm:
            ratio = (last_amt * pro_jahr) / ttm

    dist_ema50_atr = None
    if s.ema50 is not None and s.atr14:
        dist_ema50_atr = (s.price - s.ema50) / s.atr14
    ext = None
    if s.ema20 is not None and s.atr14:
        ext = (s.price - s.ema20) / s.atr14

    ex_next = getattr(s, "next_ex_div_date", None)
    ex_tage = None
    if ex_next:
        try:
            ex_tage = (dt.date.fromisoformat(ex_next) - heute).days
        except ValueError:
            ex_tage = None

    flags: list[str] = []
    if y is not None and y > p["plausibel_max_yield_pct"]:
        flags.append("Daten prüfen (Rendite unplausibel hoch)")
    if ratio is not None and ratio >= p["spitze_ratio"]:
        flags.append(f"Spitze: letzte Zahlung hochgerechnet ×{ratio:.1f} der TTM")
    if ratio is not None and ratio <= p["kuerzung_ratio"]:
        flags.append(f"gekürzt: letzte Zahlung hochgerechnet nur ×{ratio:.2f} der TTM")
    if dist_ema50_atr is not None and abs(dist_ema50_atr) <= p["anchor_atr"]:
        flags.append("am Anker EMA50 (Trend-Pullback-Long prüfen)")
    if ext is not None and ext >= p["ext_gate_max"]:
        flags.append(f"überdehnt (Ext-Gate {ext:.1f} ATR)")
    if ex_tage is not None and 0 <= ex_tage <= p["ex_hinweis_tage"]:
        flags.append(f"Ex-Tag in {ex_tage} Tagen (geschätzt) — Abschlag, kein Edge")

    atr_pct = (s.atr14 / s.price * 100.0) if (s.atr14 and s.price) else None

    return {
        "symbol": s.symbol,
        "name": meta.get("name") or s.symbol,
        "cluster": meta.get("cluster"),
        "quelle": meta.get("quelle"),
        "kurs": _r(s.price, 4),
        "bar_date": getattr(s, "last_bar_date", None),
        "ttm_yield": _r(y, 2),
        "ttm_count": getattr(s, "div_ttm_count", None),
        "ttm_sum": _r(ttm, 4),
        "last_amt": _r(last_amt, 4),
        "fwd_yield": _r(fwd_y, 2),
        "fwd_ttm_ratio": _r(ratio, 2),
        "cadence": cad,
        "ex_next": ex_next,
        "ex_src": getattr(s, "next_ex_div_source", None),
        "ex_tage": ex_tage,
        "ema20": _r(s.ema20, 4),
        "ema50": _r(s.ema50, 4),
        "ema200": _r(s.ema200, 4),
        "stack": _stack(s),
        "atr_pct": _r(atr_pct, 2),
        "dist_ema50_atr": _r(dist_ema50_atr, 2),
        "ext_gate": _r(ext, 2),
        "dist52wH": _r(getattr(s, "distance_from_52w_high_pct", None), 2),
        "flags": flags,
    }


def run_scan(snapshots: dict[str, Any], universe: dict[str, dict],
             params: dict, heute: dt.date) -> dict[str, Any]:
    """Filter + Ranking + Klumpen-Bremse. Rein, ohne Netz."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    stats = {"universum": len(universe), "gezogen": len(snapshots),
             "mit_dividende": 0, "rendite_ok": 0, "liquide": 0,
             "trend_ok": 0}

    kandidaten: list[dict[str, Any]] = []
    beinahe: list[dict[str, Any]] = []
    for sym, s in snapshots.items():
        y = getattr(s, "div_yield_ttm_pct", None)
        cnt = getattr(s, "div_ttm_count", None) or 0
        if y is None or cnt == 0:
            continue
        stats["mit_dividende"] += 1
        if y < p["min_yield_ttm_pct"] or cnt < p["min_ttm_count"]:
            continue
        stats["rendite_ok"] += 1
        vol = getattr(s, "volume_eur_avg_20d", None)
        if vol is not None and vol < p["min_volume_eur_avg_20d"]:
            continue
        stats["liquide"] += 1
        row = bewerte(s, universe.get(sym, {}), p, heute)
        if trend_intakt(s):
            stats["trend_ok"] += 1
            kandidaten.append(row)
        else:
            beinahe.append(row)

    cap = p["rank_yield_cap_pct"]

    def _rang(r: dict) -> tuple:
        # Rendite bis zum Deckel, danach Nähe zur EMA50 (besserer Einstiegsort).
        return (-min(r["ttm_yield"] or 0.0, cap),
                abs(r["dist_ema50_atr"]) if r["dist_ema50_atr"] is not None else 99)

    kandidaten.sort(key=_rang)
    treffer: list[dict[str, Any]] = []
    gekappt: list[dict[str, Any]] = []
    pro_cluster: dict[str, int] = {}
    for r in kandidaten:
        c = r["cluster"]
        if c:
            if pro_cluster.get(c, 0) >= p["max_per_cluster"]:
                gekappt.append({"symbol": r["symbol"], "cluster": c,
                                "ttm_yield": r["ttm_yield"]})
                continue
            pro_cluster[c] = pro_cluster.get(c, 0) + 1
        treffer.append(r)
    ueber_top_n = treffer[p["top_n"]:]
    treffer = treffer[: p["top_n"]]

    beinahe.sort(key=lambda r: -(r["ttm_yield"] or 0.0))
    beinahe_out = [{"symbol": r["symbol"], "name": r["name"],
                    "cluster": r["cluster"], "ttm_yield": r["ttm_yield"],
                    "stack": r["stack"], "dist52wH": r["dist52wH"]}
                   for r in beinahe[: p["beinahe_top_n"]]]

    stats.update({"treffer": len(treffer), "gekappt_cluster": len(gekappt),
                  "ueber_top_n": len(ueber_top_n),
                  "ohne_trend": len(beinahe)})
    return {
        "schema": SCHEMA_VERSION,
        "params": {k: p[k] for k in DEFAULT_PARAMS if k != "batch_size"},
        "stats": stats,
        "treffer": treffer,
        "gekappt": gekappt,
        "ohne_trend": beinahe_out,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(x: Any, nd: int = 2, suf: str = "") -> str:
    if x is None:
        return "–"
    if isinstance(x, (int, float)):
        return f"{x:.{nd}f}".replace(".", ",") + suf
    return str(x)


def render_markdown(res: dict[str, Any], now: dt.datetime) -> str:
    p, st = res["params"], res["stats"]
    out = [
        f"# DIVIDEND-SCAN — {now.strftime('%Y-%m-%d %H:%M')} (Europe/Berlin)",
        "",
        f"Filter: TTM-Rendite ≥ {_fmt(p['min_yield_ttm_pct'], 1)} % (gezahlt, "
        f"nicht hochgerechnet) · Kurs > EMA200 und EMA50 > EMA200 · "
        f"max. {p['max_per_cluster']} je Cluster.",
        f"Universum {st['universum']} · gezogen {st['gezogen']} · mit Dividende "
        f"{st['mit_dividende']} · Rendite ok {st['rendite_ok']} · liquide "
        f"{st['liquide']} · Trend ok {st['trend_ok']} · **Treffer {st['treffer']}**"
        f" (Cluster-gekappt {st['gekappt_cluster']}, ohne Trend {st['ohne_trend']})",
        "",
        "Die Dividende ist Filter, kein Edge: am Ex-Tag fällt der Kurs um den "
        "Betrag, die Ausschüttung landet im allgemeinen Topf.",
        "",
        "## Treffer",
        "",
    ]
    if res["treffer"]:
        out.append("| Symbol | Name | Cluster | TTM % | hochger. % | Ex-Tag (geschätzt) "
                   "| Stack | Abst. EMA50 (ATR) | Flags |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for r in res["treffer"]:
            ex = (f"{r['ex_next']} ({r['ex_src']})" if r["ex_next"] else "–")
            out.append(
                f"| {r['symbol']} | {r['name']} | {r['cluster'] or '–'} | "
                f"{_fmt(r['ttm_yield'])} | {_fmt(r['fwd_yield'])} | {ex} | "
                f"{r['stack']} | {_fmt(r['dist_ema50_atr'])} | "
                f"{'; '.join(r['flags']) or '–'} |"
            )
    else:
        out.append("_keine — ein gültiger Befund._")
    out.append("")
    if res["gekappt"]:
        out.append("## Klumpen-Bremse")
        out.append("")
        out.append("Wegen max. %d je Cluster nicht gelistet: %s." % (
            p["max_per_cluster"],
            ", ".join(f"{g['symbol']} ({g['cluster']}, {_fmt(g['ttm_yield'])} %)"
                      for g in res["gekappt"])))
        out.append("")
    if res["ohne_trend"]:
        out.append("## Hohe Rendite ohne Aufwärtstrend (Fallen-Anschauung)")
        out.append("")
        out.append("Nicht handeln — hier ist die Rendite hoch, WEIL der Kurs fällt.")
        out.append("")
        for r in res["ohne_trend"]:
            out.append(f"- {r['symbol']} {r['name']} — TTM {_fmt(r['ttm_yield'])} %, "
                       f"Stack {r['stack']}, {_fmt(r['dist52wH'])} % unter 52W-Hoch")
        out.append("")
    return "\n".join(out)


def render_json(res: dict[str, Any], now: dt.datetime) -> str:
    d = {"schema": res["schema"], "generated": now.isoformat(), **{
        k: v for k, v in res.items() if k != "schema"}}
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Pull + Orchestrierung
# ---------------------------------------------------------------------------

def pull_snapshots(symbols: list[str], batch_size: int) -> tuple[dict[str, Any], dict]:
    """yfinance in Batches; jeder Batch einzeln gekapselt."""
    from market_data import fetch_ticker_data

    snaps: dict[str, Any] = {}
    batches: dict[str, Any] = {}
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i:i + batch_size]
        key = f"batch_{i // batch_size + 1}"
        try:
            got = fetch_ticker_data(chunk, period="2y")
            snaps.update(got)
            batches[key] = f"{len(got)}/{len(chunk)}"
            logger.info("%s: %d/%d", key, len(got), len(chunk))
        except Exception as e:  # noqa: BLE001
            batches[key] = f"FEHLER: {type(e).__name__}"
            logger.error("%s: FEHLER %s: %s", key, type(e).__name__, e)
    return snaps, batches


def _now_berlin() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:  # noqa: BLE001
        return dt.datetime.now()


def run(nur_pool: bool = False) -> tuple[dict[str, Any], dt.datetime]:
    params = load_params()
    universe = load_universe(nur_pool=nur_pool)
    snaps, batches = pull_snapshots(sorted(universe), int(params["batch_size"]))
    now = _now_berlin()
    res = run_scan(snaps, universe, params, now.date())
    res["stats"]["batches"] = batches
    return res, now


def run_with_drive(args) -> int:
    from drive_writer import (build_drive_service, cleanup_old_files,
                              write_json_file, write_markdown_file)
    folder = os.environ.get("BRIEFING_FOLDER_ID")
    if not folder:
        logger.error("BRIEFING_FOLDER_ID env variable nicht gesetzt")
        return 1
    res, now = run(args.nur_pool)
    stamp = now.strftime("%Y-%m-%d-%H%M")
    svc = build_drive_service()
    write_markdown_file(svc, folder, f"{FILENAME_PREFIX}{stamp}.md",
                        render_markdown(res, now))
    write_json_file(svc, folder, f"{FILENAME_PREFIX}{stamp}.json",
                    render_json(res, now))
    cleanup_old_files(svc, folder, FILENAME_PREFIX, keep_count=KEEP_COUNT)
    logger.info("Dividend-Scan fertig: %s", res["stats"])
    return 0


def run_with_local_file(args) -> int:
    res, now = run(args.nur_pool)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(render_markdown(res, now))
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            f.write(render_json(res, now))
    logger.info("Geschrieben nach %s (%s)", args.output, res["stats"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", help="Lokaler Markdown-Output (kein Drive).")
    ap.add_argument("--json-output", help="Zusätzlicher lokaler JSON-Output.")
    ap.add_argument("--nur-pool", action="store_true",
                    help="Nur dividend_pool.yaml scannen (schneller Test).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if args.output:
        return run_with_local_file(args)
    return run_with_drive(args)


if __name__ == "__main__":
    sys.exit(main())
