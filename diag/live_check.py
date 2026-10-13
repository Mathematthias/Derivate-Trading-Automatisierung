"""Diag Lauf 3: fetch_ticker_data mit Luecken-Reparatur gegen Live-Yahoo."""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, "marketdata-pipeline/src")
import market_data as md

SAMPLE = ["SAP.DE", "ABBN.SW", "RACE.MI", "SMIN.L", "GIVN.SW", "FRA.DE", "HOLN.SW",
          "EURUSD=X", "BTC-EUR", "^GDAXI", "AAPL", "SBLK"]
snaps = md.fetch_ticker_data(SAMPLE)
out = {s: {"last": v.last_bar_date, "prev": v.prev_bar_date, "prev_close": v.prev_close,
           "price": v.price, "chg": v.change_pct, "luecke": v.prev_luecke,
           "rek": list(v.rekonstruiert), "atr": v.atr14, "ema20": v.ema20}
       for s, v in snaps.items()}
os.makedirs("diag/out", exist_ok=True)
p = "diag/out/live_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ") + ".json"
json.dump(out, open(p, "w"), indent=1, default=str)
print(p)
