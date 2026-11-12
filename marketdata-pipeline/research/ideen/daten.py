"""Gemeinsamer Datenlader fuer die Ideen-Backtests 2026-11-12 (Yahoo, Tagesbasis).

Ein Cache (pickle) fuer alle vier Tests:
  aktien    : Pipeline-Universum mit Volumen (PEAD)
  etfs      : Kern-Rotation (16) + SPY, URTH, BIL (Cash-Zins USD)
  indizes   : DAX, MDAX, SDAX, STOXX50E, S&P 500 TR, EXS1.DE
  krypto    : BTC, ETH, SOL in EUR, BTC in USD (laengere Historie)
  earnings  : historische Earnings-Termine je Aktie, soweit Yahoo sie liefert
"""
from __future__ import annotations

import pickle
import time
from pathlib import Path

import pandas as pd
import yaml

START = "1987-01-01"
KERN = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLU", "XLB", "SMH", "SKYY", "QQQ",
        "IWM", "EFA", "EEM", "TLT", "IEF"]
ETFS = KERN + ["SPY", "URTH", "BIL"]
INDIZES = ["^GDAXI", "^MDAXI", "^SDAXI", "^STOXX50E", "^SP500TR", "^GSPC", "EXS1.DE"]
KRYPTO = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "BTC-USD", "ETH-USD"]


def universum(cfg: Path) -> list[str]:
    a = yaml.safe_load((cfg / "tickers_tier_a.yaml").read_text())
    ex = set(a.get("ethik_excluded") or [])
    out: list[str] = []
    for k in ("thesen_koerbe", "tech_linse", "nebenwerte_de", "positionen"):
        out += list((a.get(k) or {}).values())
    for t in "bc":
        d = yaml.safe_load((cfg / f"tickers_tier_{t}.yaml").read_text())
        for v in (d.get("categories") or {}).values():
            if isinstance(v, dict):
                out += list(v.values())
            elif isinstance(v, list):
                out += [x if isinstance(x, str) else x.get("ticker") for x in v]
    skip = set(ETFS) | {"4GLD.DE", "XAD5.DE"}
    return [s for s in dict.fromkeys(out) if s and isinstance(s, str) and s not in ex
            and not s.startswith("^") and "=" not in s and "-EUR" not in s and "-USD" not in s
            and s not in skip]


def _download(symbole: list[str], start: str, mind: int) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    data: dict[str, pd.DataFrame] = {}

    def hole(chunk):
        try:
            df = yf.download(chunk, start=start, auto_adjust=True, group_by="ticker",
                             threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print("Download-Fehler", e, flush=True)
            return
        for s in chunk:
            try:
                d = df[s] if len(chunk) > 1 else df
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(-1)
                d = d[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "Close"])
                d = d[(d.Open > 0) & (d.Close > 0)]
                if len(d) >= mind:
                    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
                    data[s] = d
            except Exception:  # noqa: BLE001
                pass

    for i in range(0, len(symbole), 40):
        hole(symbole[i:i + 40])
        time.sleep(2)
    fehlend = [s for s in symbole if s not in data]
    for i in range(0, len(fehlend), 10):
        hole(fehlend[i:i + 10])
        time.sleep(3)
    return data


def _earnings(symbole: list[str], budget_s: int = 900) -> dict[str, list[pd.Timestamp]]:
    """Historische Earnings-Termine (Yahoo, so weit verfuegbar). Zeitbudget, damit der Lauf
    nicht haengen bleibt; Abdeckung wird im Bericht genannt."""
    import yfinance as yf
    out: dict[str, list[pd.Timestamp]] = {}
    t0 = time.time()
    for s in symbole:
        if time.time() - t0 > budget_s:
            print("Earnings: Zeitbudget erschoepft", flush=True)
            break
        try:
            ed = yf.Ticker(s).get_earnings_dates(limit=100)
            if ed is not None and len(ed):
                idx = pd.DatetimeIndex(ed.index)
                if idx.tz is not None:
                    # Termin in Ortszeit New York; nach 16:00 -> Reaktion am Folgetag
                    idx = idx.tz_convert("America/New_York")
                ts = []
                for x in idx:
                    d = pd.Timestamp(x.date())
                    ts.append((d, int(getattr(x, "hour", 0)) >= 16))
                out[s] = ts
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    return out


def laden(cfg: Path, cache: Path, mit_earnings: bool = True) -> dict:
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    aktien = universum(cfg)
    res = {
        "aktien": _download(aktien, "2007-01-01", 400),
        "etfs": _download(ETFS, "2000-01-01", 400),
        "indizes": _download(INDIZES, START, 400),
        "krypto": _download(KRYPTO, "2014-01-01", 300),
        "aktien_liste": aktien,
    }
    print({k: len(v) for k, v in res.items() if isinstance(v, dict)}, flush=True)
    res["earnings"] = _earnings([s for s in aktien if "." not in s and s in res["aktien"]]) \
        if mit_earnings else {}
    print("Earnings-Termine fuer", len(res["earnings"]), "Aktien", flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(res))
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--cache", default="work/ideen_cache.pkl")
    ap.add_argument("--ohne-earnings", action="store_true")
    a = ap.parse_args()
    laden(Path(a.cfg), Path(a.cache), not a.ohne_earnings)
