"""Datenstand im Digest (2026-09-07, Anlassfall US-Feiertag Labor Day).

Am 2026-09-07 waren 40 von 99 Universums-Eintraegen einen Handelstag alt
(alle US-Ticker, US-Indizes, US-Rohstofffutures), und nichts im Digest hat es
gesagt: die Frische-Pruefung misst das Datei-Alter, nicht den Datenstand.

2026-10-05 (Morning Check v49, Erstlauf 12:02 CEST): "stale" hiess bis dahin
"bar_date != heute" — damit standen am Montagmittag alle 68 US-Ticker mit dem
Freitagsschluss auf "stale, kein Entry", jeden Vormittag strukturell falsch.
Seitdem ist stale peer-relativ je Boersengruppe; eine ganze Gruppe ohne
heutigen Balken steht in pre_session.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from digest_renderer import _data_freshness, exchange_group  # noqa: E402

TS = datetime(2026, 9, 7, 18, 31, tzinfo=timezone.utc)
MO_MITTAG = datetime(2026, 10, 5, 10, 2, tzinfo=timezone.utc)   # 12:02 CEST
SAMSTAG = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
FREITAG = "2026-10-02"
MONTAG = "2026-10-05"


def _u(pairs):
    return {s: {"bar_date": d} for s, d in pairs.items()}


class TestExchangeGroup:

    @pytest.mark.parametrize("sym,grp", [
        ("SIE.DE", "EU"), ("G1A.DE", "EU"), ("NG.L", "EU"), ("TTE.PA", "EU"),
        ("RACE.MI", "EU"), ("ASML.AS", "EU"), ("ABI.BR", "EU"),
        ("IBE.MC", "EU"), ("ALC.SW", "EU"), ("EPI-A.ST", "EU"),
        ("STERV.HE", "EU"), ("MAERSK-B.CO", "EU"), ("EQNR.OL", "EU"),
        ("VOE.VI", "EU"), ("XYZ.WA", "EU"), ("ABC.F", "EU"),
        ("^GDAXI", "EU"), ("^MDAXI", "EU"), ("^SDAXI", "EU"),
        ("^TECDAX", "EU"), ("^STOXX50E", "EU"), ("^FTSE", "EU"),
        ("NBIS", "US"), ("WMT", "US"), ("BRK-B", "US"),
        ("^GSPC", "US"), ("^IXIC", "US"), ("^DJI", "US"), ("^RUT", "US"),
        ("^VIX", "US"),
        ("4568.T", "ASIA"), ("0700.HK", "ASIA"), ("^N225", "ASIA"),
        ("^HSI", "ASIA"),
        ("EURUSD=X", "CONT"), ("GC=F", "CONT"), ("NG=F", "CONT"),
        ("BTC-EUR", "CRYPTO"), ("ETH-USD", "CRYPTO"),
    ])
    def test_zuordnung(self, sym, grp):
        assert exchange_group(sym) == grp

    def test_unbekannte_boerse_ist_eigene_gruppe(self):
        """Lieber kein Vergleichspartner als eine fremde Boerse als Massstab."""
        assert exchange_group("SHOP.TO") == ".TO"
        assert exchange_group("^AXJO") == "^AXJO"


class TestDataFreshness:

    def test_alles_aktuell(self):
        r = _data_freshness(_u({"SIX2.DE": "2026-09-07", "DB1.DE": "2026-09-07"}), TS)
        assert r["stale_count"] == 0
        assert r["stale"] == []
        assert r["pre_session"] == []
        assert r["latest_bar"] == "2026-09-07"

    def test_us_feiertag_wird_gemeldet(self):
        """Labor Day: die US-Gruppe als Ganzes liegt zurueck. Das ist kein
        stale-Befund je Ticker mehr, sondern steht in pre_session."""
        uni = _u({"SIX2.DE": "2026-09-07", "DB1.DE": "2026-09-07",
                  "MU": "2026-09-04", "CTAS": "2026-09-04", "FANG": "2026-09-04"})
        r = _data_freshness(uni, TS)
        assert r["stale_count"] == 0
        assert r["pre_session"] == ["US"]
        assert r["groups"]["US"] == {"latest": "2026-09-04", "count": 3}
        assert r["by_date"] == {"2026-09-07": 2, "2026-09-04": 3}

    def test_einzelner_haengender_feed(self):
        """Was eine Feiertagsliste NICHT faengt (Anlassfall G1A.DE)."""
        uni = _u({"SIX2.DE": "2026-09-07", "G1A.DE": "2026-09-03"})
        r = _data_freshness(uni, TS)
        assert r["stale"] == ["G1A.DE"]
        assert r["pre_session"] == []

    def test_montagmittag_us_noch_zu(self):
        """(a) Anlassfall 2026-10-05 12:02 CEST: EU, FX/Futures und Krypto
        haben den Montagsbalken, US steht auf dem Freitagsschluss."""
        uni = _u({
            "SIE.DE": MONTAG, "DHL.DE": MONTAG, "^GDAXI": MONTAG, "NG.L": MONTAG,
            "EURUSD=X": MONTAG, "GC=F": MONTAG, "BTC-EUR": MONTAG,
            "NBIS": FREITAG, "WMT": FREITAG, "LLY": FREITAG, "^GSPC": FREITAG,
            "^VIX": FREITAG,
        })
        r = _data_freshness(uni, MO_MITTAG)
        assert r["stale"] == [] and r["stale_count"] == 0
        assert r["pre_session"] == ["US"]
        assert r["groups"]["US"]["latest"] == FREITAG
        assert r["groups"]["US"]["count"] == 5
        assert r["groups"]["EU"] == {"latest": MONTAG, "count": 4}
        assert r["as_of"] == MONTAG
        assert r["latest_bar"] == MONTAG

    def test_ein_eu_ticker_auf_vortag(self):
        """(b) Rest der EU auf heute, ein Ticker auf Vortag -> genau der."""
        uni = _u({
            "SIE.DE": MONTAG, "ALV.DE": MONTAG, "TTE.PA": MONTAG,
            "G1A.DE": "2026-10-02",
            "NBIS": FREITAG, "WMT": FREITAG,
        })
        r = _data_freshness(uni, MO_MITTAG)
        assert r["stale"] == ["G1A.DE"]
        assert r["stale_count"] == 1
        assert r["pre_session"] == ["US"]

    def test_wochenende_alles_auf_freitag(self):
        """(c) Samstag: alle Gruppen auf Freitag. as_of liegt vor jeder
        Gruppe, aber pre_session misst gegen den juengsten Balken des
        Universums, nicht gegen as_of -> leer."""
        uni = _u({"SIE.DE": FREITAG, "NG.L": FREITAG, "NBIS": FREITAG,
                  "^GSPC": FREITAG, "EURUSD=X": FREITAG, "GC=F": FREITAG})
        r = _data_freshness(uni, SAMSTAG)
        assert r["as_of"] == "2026-10-03"
        assert r["stale"] == []
        assert r["pre_session"] == []

    def test_wochenende_krypto_ist_voraus(self):
        """(c') Realistischer Samstag: Krypto hat einen Samstagsbalken. Weder
        werden FX/Futures dadurch stale, noch rutschen EU/US in pre_session."""
        uni = _u({"SIE.DE": FREITAG, "NBIS": FREITAG, "EURUSD=X": FREITAG,
                  "GC=F": FREITAG, "BTC-EUR": "2026-10-03",
                  "ETH-EUR": "2026-10-03"})
        r = _data_freshness(uni, SAMSTAG)
        assert r["stale"] == []
        assert r["pre_session"] == []
        assert r["latest_bar"] == "2026-10-03"

    def test_krypto_feed_haengt_an_einem_werktag(self):
        """Krypto zaehlt nicht fuer den Massstab, kann aber selbst zurueck-
        liegen."""
        uni = _u({"SIE.DE": MONTAG, "BTC-EUR": "2026-10-04",
                  "ETH-EUR": "2026-10-04"})
        r = _data_freshness(uni, MO_MITTAG)
        assert r["pre_session"] == ["CRYPTO"]
        assert r["stale"] == []

    def test_fehlendes_bar_date_landet_in_unknown(self):
        uni = {"X": {"bar_date": None}, "Y": {"bar_date": "2026-09-07"}}
        r = _data_freshness(uni, TS)
        assert r["unknown"] == ["X"] and r["stale_count"] == 0
        assert r["groups"]["US"]["count"] == 1      # unknown zaehlt nicht mit

    def test_leeres_universum(self):
        r = _data_freshness({}, TS)
        assert r["latest_bar"] is None and r["stale_count"] == 0
        assert r["groups"] == {} and r["pre_session"] == []

    def test_bestehende_felder_bleiben(self):
        r = _data_freshness(_u({"A": "2026-09-04"}), TS)
        for feld in ("as_of", "latest_bar", "by_date", "stale_count", "stale",
                     "unknown", "groups", "pre_session"):
            assert feld in r

    def test_serialisierbar(self):
        json.dumps(_data_freshness(_u({"A": "2026-09-04", "B.DE": "2026-09-07"}), TS))
