"""Plausibilitaet der Rotations-Scores: Rohkurse und Teilrenditen je Lookback."""
import yfinance as yf
syms = ["XLK", "SMH", "QQQ", "XLV", "XLE", "XLP", "XLB", "XLF", "SKYY"]
for adj in (True, False):
    df = yf.download(syms, period="2y", auto_adjust=adj, group_by="ticker", progress=False)
    print("auto_adjust", adj)
    for s in syms:
        c = df[s]["Close"].dropna()
        r = {lb: c.iloc[-1] / c.iloc[-1 - lb] - 1 for lb in (63, 126, 252)}
        print(f"{s:5} letzter {c.index[-1].date()} {c.iloc[-1]:9.2f}  vor252 {c.index[-253].date()} {c.iloc[-253]:9.2f}  "
              + "  ".join(f"{k}:{v:+.3f}" for k, v in r.items()) + f"  n={len(c)}")
