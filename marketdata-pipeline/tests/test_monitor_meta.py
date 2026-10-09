"""v63 (2026-10-09): Positions-Monitor-Meta im Digest — SL, TP1 (gefuellt?), Review.
Anlass: DUE #101, TP1 am 08.10. gefuellt und SL nachgezogen, die Monitor-Zeile stand
noch auf dem Einstiegsplan; der Morning Check fragte deshalb nach einem laengst
gefuellten TP1."""
import src.state_yaml as sy


def _block(text, status="position"):
    return {"entries": [{"symbol": "DUE.DE", "status": status, "trade_nr": "101",
                         "legs": [{"label": "A", "gate": "🟢", "text": text}]}]}


def test_runner_nach_tp1():
    t = ("POSITION-MONITOR (#101, Rest 80 Stk, RUNNER) - kein Entry-Trigger. TP1 4,65EUR gefuellt 2026-10-08 "
         "(80 Stk, U ~16,31). SL 3,64EUR (U ~17,30). TIW = 1D-Schluss ueber 17,75€. TP2 5,56EUR. Recheck 2026-10-15.")
    m = sy.watchlist_meta(_block(t))[0]["monitor"]
    assert m == {"sl": 3.64, "tp1": 4.65, "tp1_gefuellt": True, "review": "2026-10-15"}


def test_einstiegsplan_stop_wort():
    t = ("POSITION-MONITOR (#11 AV) - kein Entry-Trigger. Stop 24,98EUR (U 27,94$ bei FX 1,1187). "
         "TIW = 1D-Schluss unter 28,20$. TP1 32,40$ = 45 Stk. Review 2026-10-14 (verlaengert 07.10.).")
    m = sy.watchlist_meta(_block(t))[0]["monitor"]
    assert m["sl"] == 24.98 and m["tp1"] is None and m["tp1_gefuellt"] is False and m["review"] == "2026-10-14"


def test_nur_positionen():
    t = "nach 2026-10-09 TREND-PULLBACK-LONG: SL 3,64EUR. Review 2026-10-15."
    assert sy.watchlist_meta(_block(t, status="aktiv"))[0]["monitor"] is None
