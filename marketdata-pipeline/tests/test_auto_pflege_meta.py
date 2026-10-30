"""2026-10-30 (Auto-Pflege v83): watchlist_meta traegt quelle und added; Ethik-Liste."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import state_yaml as sy  # noqa: E402


def test_quelle_und_added_im_meta():
    block = {"entries": [
        {"symbol": "AAA", "status": "aktiv", "quelle": "auto", "added": "2026-10-30",
         "legs": [{"label": "A", "gate": "🟡", "text": "TIW = 1D-Schluss unter 1,00€."}]},
        {"symbol": "BBB", "status": "aktiv", "legs": [{"label": "A", "gate": "🟡", "text": "x"}]},
    ]}
    m = sy.watchlist_meta(block)
    assert m[0]["quelle"] == "auto" and m[0]["added"] == "2026-10-30"
    assert m[1]["quelle"] is None and m[1]["added"] is None


def test_tkms_ausgeschlossen_renk_grenzfall():
    cfg = yaml.safe_load(open(ROOT / "config" / "filter_config.yaml", encoding="utf-8"))
    def finde(d):
        if isinstance(d, dict):
            if "ethics_exclude" in d:
                return d
            for v in d.values():
                r = finde(v)
                if r:
                    return r
        return None
    p = finde(cfg)
    assert "TKMS.DE" in p["ethics_exclude"] and "RHM.DE" in p["ethics_exclude"]
    assert "R3NK.DE" in p["ethics_grenzfall"]
