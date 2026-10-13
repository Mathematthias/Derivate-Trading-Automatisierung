"""Diagnose 2026-10-13: Warum fehlt nach Mitternacht der Tagesbalken des Vortags?

Vergleicht fuer eine Stichprobe die Yahoo-Rohantwort (v8 chart) mit der
yfinance-Ausgabe (Ticker.history und yf.download im Batch) und schreibt alles
nach diag/out/<stamp>.json. Wird nur auf dem Branch diag/vortagesbalken
ausgefuehrt; aendert nichts an der Pipeline.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

SAMPLE = ["SAP.DE", "ABBN.SW", "RACE.MI", "SMIN.L", "EURUSD=X", "BTC-EUR", "^GDAXI", "AAPL", "SBLK"]


def _rows(df: pd.DataFrame, n: int = 6) -> list:
    if df is None or df.empty:
        return []
    out = []
    for idx, row in df.tail(n).iterrows():
        out.append({"idx": str(idx), **{c: (None if pd.isna(row.get(c)) else float(row.get(c)))
                                          for c in ("Open", "High", "Low", "Close", "Volume") if c in row}})
    return out


def raw_chart(sym: str) -> dict:
    from yfinance.data import YfData

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
    params = {"range": "1mo", "interval": "1d", "includePrePost": "false", "events": "div,splits"}
    r = YfData().get(url=url, params=params, timeout=20)
    j = r.json()
    res = j["chart"]["result"][0]
    meta = res.get("meta", {})
    ts = res.get("timestamp", [])
    q = res["indicators"]["quote"][0]
    tail = []
    for i in range(max(0, len(ts) - 6), len(ts)):
        tail.append({
            "ts": ts[i],
            "utc": datetime.fromtimestamp(ts[i], tz=timezone.utc).isoformat(),
            "open": q["open"][i], "high": q["high"][i], "low": q["low"][i],
            "close": q["close"][i], "volume": q["volume"][i],
        })
    return {
        "meta": {k: meta.get(k) for k in ("exchangeTimezoneName", "gmtoffset", "regularMarketTime",
                                           "regularMarketPrice", "currentTradingPeriod", "dataGranularity", "validRanges")},
        "tail": tail,
    }


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    out: dict = {"stamp_utc": stamp, "yfinance": yf.__version__, "pandas": pd.__version__, "ticker": {}}

    for sym in SAMPLE:
        rec: dict = {}
        try:
            rec["raw"] = raw_chart(sym)
        except Exception:
            rec["raw_err"] = traceback.format_exc()[-1500:]
        for label, kw in (("hist_1mo", {"period": "1mo"}), ("hist_2y", {"period": "2y"}),
                          ("hist_2y_repair", {"period": "2y", "repair": True})):
            try:
                rec[label] = _rows(yf.Ticker(sym).history(interval="1d", auto_adjust=False, actions=True, **kw))
            except Exception:
                rec[label + "_err"] = traceback.format_exc()[-1500:]
        out["ticker"][sym] = rec

    # Batch wie in market_data.fetch_ticker_data
    try:
        raw = yf.download(SAMPLE, period="2y", interval="1d", group_by="ticker", auto_adjust=False,
                          actions=True, progress=False, threads=True)
        for sym in SAMPLE:
            df = raw[sym].dropna(subset=["Close"])
            out["ticker"][sym]["batch_2y"] = _rows(df)
            out["ticker"][sym]["batch_2y_nan_rows"] = [str(i) for i in raw[sym].tail(6).index
                                                        if pd.isna(raw[sym].loc[i, "Close"])]
    except Exception:
        out["batch_err"] = traceback.format_exc()[-1500:]

    os.makedirs("diag/out", exist_ok=True)
    path = f"diag/out/{stamp}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
