"""Datenstand im Digest (2026-09-07, Anlassfall US-Feiertag Labor Day).

Am 2026-09-07 waren 40 von 99 Universums-Eintraegen einen Handelstag alt
(alle US-Ticker, US-Indizes, US-Rohstofffutures), und nichts im Digest hat es
gesagt: die Frische-Pruefung misst das Datei-Alter, nicht den Datenstand.
"""
import json
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from digest_renderer import _data_freshness  # noqa: E402

TS = datetime(2026, 9, 7, 18, 31, tzinfo=timezone.utc)


def _u(**kw):
    return {s: {"bar_date": d} for s, d in kw.items()}


class TestDataFreshness:

    def test_alles_aktuell(self):
        r = _data_freshness(_u(SIXDE="2026-09-07", DB1DE="2026-09-07"), TS)
        assert r["stale_count"] == 0
        assert r["stale"] == []
        assert r["latest_bar"] == "2026-09-07"

    def test_us_feiertag_wird_gemeldet(self):
        uni = _u(SIXDE="2026-09-07", DB1DE="2026-09-07",
                 MU="2026-09-04", CTAS="2026-09-04", FANG="2026-09-04")
        r = _data_freshness(uni, TS)
        assert r["stale_count"] == 3
        assert r["stale"] == ["CTAS", "FANG", "MU"]
        assert r["by_date"] == {"2026-09-07": 2, "2026-09-04": 3}

    def test_einzelner_haengender_feed(self):
        """Was eine Feiertagsliste NICHT faengt (Anlassfall G1A.DE)."""
        uni = _u(SIXDE="2026-09-07", G1ADE="2026-09-03")
        r = _data_freshness(uni, TS)
        assert r["stale"] == ["G1ADE"]

    def test_fehlendes_bar_date_landet_in_unknown(self):
        uni = {"X": {"bar_date": None}, "Y": {"bar_date": "2026-09-07"}}
        r = _data_freshness(uni, TS)
        assert r["unknown"] == ["X"] and r["stale_count"] == 0

    def test_leeres_universum(self):
        r = _data_freshness({}, TS)
        assert r["latest_bar"] is None and r["stale_count"] == 0

    def test_serialisierbar(self):
        json.dumps(_data_freshness(_u(A="2026-09-04"), TS))
