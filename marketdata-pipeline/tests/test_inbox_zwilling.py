"""2026-10-28 (Befund NET): INBOX-set_*-Aktionen treffen bei Archiv-Zwillingen die aktive Zeile."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import state_yaml as sy  # noqa: E402


def _wl():
    return {"entries": [
        {"symbol": "NET", "status": "archiviert", "expiry": "2026-10-20", "legs": [{"label": "A", "gate": "🔴"}]},
        {"symbol": "NET", "status": "aktiv", "expiry": "2026-10-29", "legs": [{"label": "A", "gate": "🟡"}]},
    ]}


def test_live_entry_bevorzugt_aktiv_dann_position():
    wl = _wl()
    assert sy._find_live_entry(wl, "net")["expiry"] == "2026-10-29"
    wl["entries"][1]["status"] = "position"
    assert sy._find_live_entry(wl, "NET")["status"] == "position"
    wl["entries"][1]["status"] = "archiviert"
    assert sy._find_live_entry(wl, "NET") is wl["entries"][0]
    assert sy._find_live_entry(wl, "XYZ") is None


def test_keine_alte_erste_zeile_suche_in_set_ops():
    src = open(sy.__file__, encoding="utf-8").read()
    assert 'e = _find_entry(wl, a["symbol"])' not in src
