"""Digest-Fixes aus dem ersten Morning Check mit Digest v4 (2026-10-05).

Fix 2 — watchlist_expiry: 105 Eintraege, davon 74 archiviert. Archivierte
        Zeilen verfallen nicht mehr; nur aktiv/position, jeweils mit status.
Fix 3 — Positions-Monitore in Stufe 1: NBIS und JST.DE standen in
        buckets.ready, DHL.DE wurde ueber "Invalidator … EMA50-1D (~55,86€)"
        als approx-Trigger BEREIT. Monitore gehoeren nur in position_monitors.

Die Eintraege laufen durch state_yaml.entries_from_yaml — derselbe Weg wie bei
WATCHLIST_SOURCE=yaml —, damit der Test auch prueft, dass der YAML-Status am
Entry ankommt.
"""
from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

from digest_renderer import (_is_position_monitor, _watchlist_status,
                             build_briefing_digest)
from filter_engine import TriggerStatus, WatchlistResult
from state_yaml import entries_from_yaml

TS = dt.datetime(2026, 10, 5, 10, 2, tzinfo=dt.timezone.utc)


def _yaml_entry(symbol, status, name=None, expiry="2026-10-09", text=None,
                direction="LONG", trade_nr=None):
    return {
        "symbol": symbol, "name": name or symbol, "direction": direction,
        "klasse": "position_monitor" if status == "position" else "trend_pullback",
        "status": status, "expiry": expiry, "trade_nr": trade_nr,
        "legs": [{"label": "A", "gate": "🟢",
                  "text": text or "TREND-PULLBACK-LONG: Zone 50,00-52,00€"}],
    }


def _entries(*rows):
    by = {e.symbol: e for e in entries_from_yaml({"entries": list(rows)})}
    return by


def _ready(entry):
    """WatchlistResult im BEREIT-Zustand (in_zone, nichts fehlt)."""
    ts = TriggerStatus(label="A", proximity="in_zone", distance_pct=0.0,
                       conditions_met=["Zone"], summary="in Zone")
    return WatchlistResult(entry=entry, snapshot=None, overall_status="active",
                           trigger_results=[ts], note="")


def _far(entry):
    ts = TriggerStatus(label="A", proximity="far", distance_pct=12.0)
    return WatchlistResult(entry=entry, snapshot=None, overall_status="active",
                           trigger_results=[ts], note="")


def _digest(results):
    return json.loads(build_briefing_digest({}, results, [], [], TS))


# --- Status kommt am Entry an ------------------------------------------------

def test_yaml_status_haengt_am_entry():
    by = _entries(_yaml_entry("SIE.DE", "aktiv"),
                  _yaml_entry("DHL.DE", "position", trade_nr="102"),
                  _yaml_entry("ZTS", "archiviert"))
    assert by["SIE.DE"].state_status == "aktiv"
    assert by["DHL.DE"].state_status == "position"
    assert by["ZTS"].state_status == "archiviert"
    # Pipeline-Status bleibt, wie filter_engine ihn kennt
    assert {e.status for e in by.values()} == {"aktiv"}


def test_status_ohne_yaml_wird_abgeleitet():
    """STATE-Doc-Pfad: kein Lebenszyklus-Feld -> Monitor-Kriterium."""
    mon = SimpleNamespace(symbol="SBLK", name="Star Bulk [MONITOR #11 AV]",
                          direction="LONG")
    alt = SimpleNamespace(symbol="SBLK", name="Star Bulk",
                          direction="POSITION-MONITOR (LONG)")
    kand = SimpleNamespace(symbol="SIE.DE", name="Siemens", direction="LONG")
    assert _watchlist_status(mon) == "position"
    assert _watchlist_status(alt) == "position"
    assert _watchlist_status(kand) == "aktiv"
    assert _is_position_monitor(alt) and not _is_position_monitor(kand)


# --- Fix 2: watchlist_expiry ---------------------------------------------------

def test_expiry_ohne_archivierte_mit_status():
    by = _entries(
        _yaml_entry("SIE.DE", "aktiv", expiry="2026-10-09"),
        _yaml_entry("WMT", "position", expiry="2026-10-02",
                    name="Walmart [MONITOR #99]", direction="SHORT"),
        _yaml_entry("ZTS", "archiviert", expiry="2026-10-06"),
        _yaml_entry("MRK.DE", "archiviert", expiry="2026-09-07",
                    name="Merck KGaA (ehem. Monitor)"),
    )
    d = _digest([_far(e) for e in by.values()])
    exp = d["watchlist_expiry"]
    assert [z["symbol"] for z in exp] == ["WMT", "SIE.DE"]
    assert exp[0] == {"symbol": "WMT", "expiry": "2026-10-02",
                      "tage_rest": -3, "status": "position"}
    assert exp[1]["status"] == "aktiv" and exp[1]["tage_rest"] == 4


def test_expiry_fenster_gilt_weiter():
    by = _entries(_yaml_entry("SIE.DE", "aktiv", expiry="2026-12-31"))
    assert _digest([_far(by["SIE.DE"])])["watchlist_expiry"] == []


# --- Fix 3: Monitore raus aus Stufe 1 -----------------------------------------

def test_monitor_im_ready_zustand_nicht_in_buckets():
    """Anlassfall DHL.DE: Monitor-Text mit Preis -> als Zone geparst -> BEREIT."""
    by = _entries(
        _yaml_entry("DHL.DE", "position", trade_nr="102",
                    name="DHL Group (DHL, XETRA) [MONITOR #102]",
                    text="POSITION-MONITOR (#102) - kein Entry-Trigger. SL 9,68EUR "
                         "(U ~54,94). Invalidator = EMA50-1D (~55,86€)"),
        _yaml_entry("NBIS", "position", name="Nebius Group N.V. (NBIS) [MONITOR #9 AV]"),
        _yaml_entry("SIE.DE", "aktiv"),
    )
    res = [_ready(by["DHL.DE"]), _ready(by["NBIS"]), _ready(by["SIE.DE"])]
    res[0].note = "TIW-Abstand 2,1 %"
    d = _digest(res)

    assert [b["symbol"] for b in d["buckets"]["ready"]] == ["SIE.DE"]
    for name, rows in d["buckets"].items():
        assert not {"DHL.DE", "NBIS"} & {b["symbol"] for b in rows}, name

    mon = {m["symbol"]: m for m in d["position_monitors"]}
    assert set(mon) == {"DHL.DE", "NBIS"}
    assert mon["DHL.DE"]["name"] == "DHL Group (DHL, XETRA) [MONITOR #102]"
    assert mon["DHL.DE"]["note"] == "TIW-Abstand 2,1 %"
    assert mon["DHL.DE"]["label"] == "LONG"

    c = d["counts"]
    assert c["ready"] == 1 and c["position_monitors"] == 2
    assert sum(c[k] for k in ("ready", "in_zone_partial", "very_close", "close",
                              "watching", "pending", "paused", "no_data", "far",
                              "position_monitors")) == len(res)


def test_status_position_ohne_monitor_token_reicht():
    """Der YAML-Status allein genuegt — auch wenn ein Name das Token nicht
    traegt (entries_from_yaml ergaenzt es heute, der Filter haengt nicht
    davon ab)."""
    e = SimpleNamespace(symbol="DB1.DE", name="Deutsche Boerse AG",
                        direction="LONG", state_status="position",
                        expiry_date=None, triggers=[])
    r = WatchlistResult(entry=e, snapshot=None, overall_status="active",
                        trigger_results=[TriggerStatus(label="A", proximity="in_zone",
                                                       distance_pct=0.0)])
    d = _digest([r])
    assert d["buckets"] == {}
    assert [m["symbol"] for m in d["position_monitors"]] == ["DB1.DE"]


def test_altes_kriterium_richtung_bleibt():
    """STATE-Doc-Monitore (Richtung POSITION-MONITOR) fallen ebenfalls raus."""
    e = SimpleNamespace(symbol="SBLK", name="Star Bulk", expiry_date=None,
                        direction="POSITION-MONITOR (LONG)", triggers=[])
    d = _digest([_ready(e)])
    assert "ready" not in d["buckets"]
    assert [m["symbol"] for m in d["position_monitors"]] == ["SBLK"]


def test_monitor_indikatoren_bleiben_im_universe():
    from market_data import TickerSnapshot
    by = _entries(_yaml_entry("JST.DE", "position", name="JOST Werke SE [MONITOR #100]"))
    snap = TickerSnapshot(symbol="JST.DE", timestamp=dt.datetime(2026, 10, 5),
                          price=59.4, prev_close=59.0)
    d = json.loads(build_briefing_digest({"JST.DE": snap}, [_ready(by["JST.DE"])],
                                         [], [], TS))
    assert "JST.DE" in d["universe"] and d["universe"]["JST.DE"]["kurs"] == 59.4
    assert d["buckets"] == {}
    assert [m["symbol"] for m in d["position_monitors"]] == ["JST.DE"]


def test_archivierter_monitor_ist_keine_position():
    """Fix 2026-10-09: Geschlossene Trades behalten das "[MONITOR #NN]"-Token im
    Namen. Mit Status archiviert duerfen sie nicht in position_monitors landen
    (Morning Check 2026-10-09: 10 statt 4 Positionen)."""
    by = _entries(
        _yaml_entry("NBIS", "archiviert", name="Nebius Group N.V. (NBIS) [MONITOR #9 AV]"),
        _yaml_entry("RACE.MI", "position", name="Ferrari NV [MONITOR #103]"),
    )
    assert not _is_position_monitor(by["NBIS"])
    assert _is_position_monitor(by["RACE.MI"])
    assert _watchlist_status(by["NBIS"]) == "archiviert"
    d = _digest([_ready(by["NBIS"]), _ready(by["RACE.MI"])])
    assert [m["symbol"] for m in d["position_monitors"]] == ["RACE.MI"]
    # Buckets: archivierte Zeilen haben in der Pipeline nur 🔴-Legs und
    # landen ueber die Filter-Engine in "paused" — das deckt dieser Test nicht ab.
