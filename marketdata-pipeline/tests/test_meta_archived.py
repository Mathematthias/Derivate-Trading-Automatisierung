"""2026-10-20: watchlist_meta traegt das Archivdatum (Re-Eval zaehlt erst ab Archivtag)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import state_yaml as sy  # noqa: E402


def test_archivdatum_im_meta():
    block = {"entries": [
        {"symbol": "EPI-A.ST", "status": "archiviert", "archived": {"date": "2026-10-20", "reason": "x"},
         "legs": [{"label": "A", "gate": "🔴", "text": "RE-EVAL: 1D-Schluss >259,56 (Rueckkehr) - dann neu rechnen."}]},
        {"symbol": "X", "status": "aktiv", "legs": [{"label": "A", "gate": "🟡", "text": "TIW = 1D-Schluss unter 1,00€."}]},
    ]}
    m = sy.watchlist_meta(block)
    assert m[0]["archived"] == "2026-10-20" and m[0]["reeval"] == {"op": ">", "level": 259.56}
    assert m[1]["archived"] is None
