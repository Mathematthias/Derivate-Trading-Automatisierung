"""
Tests für adhoc_scanner — laufen ohne Netzzugriff.

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src python tests/test_filter.py
oder mit pytest:
    PYTHONPATH=./src pytest tests/ -v
"""

import datetime as dt
import os
import sys

# src/ in den Path, damit adhoc_scanner gefunden wird
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from adhoc_scanner import (
    FeedItem, filter_and_classify, watchlist_hit, render_markdown,
)


def make_item(title: str, summary: str = "", hours_ago: float = 1) -> FeedItem:
    return FeedItem(
        title=title,
        link=f"https://example.com/{abs(hash(title))}",
        published=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago),
        summary=summary,
        source="test",
    )


def test_classification_gewinnwarnung():
    item = make_item("VIDINEXT AG: Gewinnwarnung für das Geschäftsjahr 2025")
    assert item.classify() == "Gewinnwarnung"
    assert not item.matches_blacklist()


def test_classification_takeover():
    item = make_item("XRG P.J.S.C. übermittelt förmliches Squeeze-out-Verlangen")
    assert item.classify() == "M&A / Übernahme"


def test_classification_buyback():
    item = make_item("Allianz SE beschließt neues Rückkaufprogramm für Aktien")
    assert item.classify() == "Aktienrückkauf"


def test_classification_directors_dealings():
    item = make_item(
        "Eigengeschäfte von Führungskräften gemäß Art. 19 MAR — CEO Kauf 50.000 Aktien"
    )
    assert item.classify() == "Insider / Directors' Dealings"


# === Regressionstests aus Live-Lauf 2026-04-29 ===

def test_real_world_talanx_quartalsergebnis_NOT_insider():
    """Talanx Q-Ergebnis war fälschlich als Insider klassifiziert.
    Title enthält keine Insider-Stichwörter — Summary darf Boilerplate
    enthalten ohne Trigger."""
    item = FeedItem(
        title="EQS-Adhoc: Talanx Aktiengesellschaft: Talanx erzielt Quartalsergebnis von EUR 774 Mio.",
        link="https://example.com/talanx",
        published=dt.datetime.now(dt.timezone.utc),
        summary=(
            "EQS-Ad-hoc: Talanx Aktiengesellschaft / Schlagwort(e): Quartalsergebnis. "
            "Veröffentlichung einer Insiderinformation gemäß Artikel 17 MAR. "
            "Der Konzern erzielt im 1. Quartal 2026 ein Ergebnis von EUR 774 Mio."
        ),
        source="finanznachrichten_adhoc",
    )
    # Quartalsergebnis ohne Beat/Miss-Hinweis ist KEIN Catalyst — gehört in Earnings-Layer.
    # Wichtig: weder als Insider noch als Gewinnwarnung klassifizieren.
    assert item.classify() is None


def test_real_world_verlustanzeige_is_sondersituation():
    """Deutsche Defence Verlustanzeige nach § 92 AktG war fälschlich
    als Insider klassifiziert. Gehört in Sondersituation."""
    item = FeedItem(
        title="PTA-Adhoc: Deutsche Defence Beteiligungen AG: Vorsorgliche Verlustanzeige nach § 92 Abs.1 AktG",
        link="https://example.com/dd",
        published=dt.datetime.now(dt.timezone.utc),
        summary="Veröffentlichung von Insiderinformationen gemäß Artikel 17 MAR.",
        source="finanznachrichten_adhoc",
    )
    assert item.classify() == "Sondersituation"


def test_real_world_aktienkaufvertrag_is_ma():
    """Saxony Minerals Aktienkaufvertrag war fälschlich als Insider
    klassifiziert. Gehört in M&A."""
    item = FeedItem(
        title="PTA-Adhoc: Saxony Minerals & Exploration - SME AG: Abschluss eines Aktienkaufvertrags durch Aktionäre - Vollzug derzeit ungewiss",
        link="https://example.com/sme",
        published=dt.datetime.now(dt.timezone.utc),
        summary="Veröffentlichung von Insiderinformationen gemäß Artikel 17 MAR.",
        source="finanznachrichten_adhoc",
    )
    assert item.classify() == "M&A / Übernahme"


def test_eqs_boilerplate_in_summary_does_not_trigger_insider():
    """Generische EQS-Pflichtboilerplate im Summary darf NIE allein Insider-
    Klassifikation auslösen — egal welches sonst harmlose Title."""
    item = FeedItem(
        title="Hapag-Lloyd AG: Karl Gernandt übernimmt Aufsichtsratsvorsitz",
        link="https://example.com/hl",
        published=dt.datetime.now(dt.timezone.utc),
        summary=(
            "Veröffentlichung einer Insiderinformation gemäß Artikel 17 MAR. "
            "Personelle Veränderungen im Aufsichtsrat..."
        ),
        source="test",
    )
    # Sollte als "Strategie / Vorstand" klassifiziert werden ODER None,
    # aber definitiv nicht als Insider.
    assert item.classify() != "Insider / Directors' Dealings"


def test_genuine_directors_dealings_still_triggers():
    """Sicherstellen, dass echte Directors-Dealings-Items weiter klappen."""
    item = make_item(
        "EQS-DD: Beispiel AG — Directors' Dealings: CEO kauft 100.000 Aktien"
    )
    assert item.classify() == "Insider / Directors' Dealings"


def test_verlustanzeige_short_form():
    """Kurzform '§92 AktG' (ohne Leerzeichen) muss auch matchen."""
    item = make_item("Beispiel AG: Verlustanzeige nach §92 AktG")
    assert item.classify() == "Sondersituation"


def test_blacklist_voting_rights():
    item = make_item("Stimmrechtsmitteilung gemäß § 33 WpHG")
    assert item.matches_blacklist()


def test_blacklist_agm():
    item = make_item("Einladung zur ordentlichen Hauptversammlung 2026")
    assert item.matches_blacklist()


def test_filter_old_items_dropped():
    items = [
        make_item("Gewinnwarnung — frisch", hours_ago=2),
        make_item("Gewinnwarnung — alt", hours_ago=48),
    ]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    result = filter_and_classify(items, cutoff)
    assert result.total_items_seen == 2
    assert result.total_catalysts() == 1


def test_filter_blacklist_dropped():
    items = [
        make_item("Hauptversammlung Tagesordnung 2026"),
        make_item("Gewinnwarnung 2025"),
    ]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    result = filter_and_classify(items, cutoff)
    assert result.total_items_dropped_blacklist == 1
    assert result.total_catalysts() == 1


def test_filter_unmatched_dropped():
    items = [
        make_item("Quartalsmeldung — alles wie geplant"),  # weder Catalyst noch Blacklist
        make_item("Übernahmeangebot"),
    ]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    result = filter_and_classify(items, cutoff)
    assert result.total_items_dropped_unmatched >= 1
    assert result.total_catalysts() == 1


def test_dedupe_same_link_same_source():
    item1 = FeedItem(
        title="Aktienrückkauf bei Allianz", link="https://example.com/x",
        published=dt.datetime.now(dt.timezone.utc),
        summary="", source="src1",
    )
    item2 = FeedItem(
        title="Aktienrückkauf bei Allianz",  # gleicher Inhalt
        link="https://example.com/x",  # gleicher Link
        published=dt.datetime.now(dt.timezone.utc),
        summary="", source="src1",
    )
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    result = filter_and_classify([item1, item2], cutoff)
    assert result.total_catalysts() == 1


def test_no_dedupe_different_sources():
    item1 = FeedItem(
        title="Aktienrückkauf bei Allianz", link="https://example.com/x",
        published=dt.datetime.now(dt.timezone.utc),
        summary="", source="finanznachrichten",
    )
    item2 = FeedItem(
        title="Aktienrückkauf bei Allianz", link="https://example.com/x",
        published=dt.datetime.now(dt.timezone.utc),
        summary="", source="deutsche_boerse",
    )
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    result = filter_and_classify([item1, item2], cutoff)
    # Bewusst: gleicher Link aus zwei Quellen zählt 2× — wir trennen pro Quelle.
    assert result.total_catalysts() == 2


def test_watchlist_hit():
    item = make_item("CBK.DE: Übernahmegerüchte verdichten sich")
    watchlist = ["CBK.DE", "PG", "ATOSS"]
    assert watchlist_hit(item, watchlist) == "CBK.DE"


def test_watchlist_no_hit():
    item = make_item("Allianz beschließt Rückkaufprogramm")
    watchlist = ["CBK.DE", "PG", "ATOSS"]
    assert watchlist_hit(item, watchlist) is None


def test_render_empty():
    from adhoc_scanner import ScanResult
    result = ScanResult(cutoff_utc=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24))
    md = render_markdown(result, [], dt.datetime.now(dt.timezone.utc))
    assert "Keine Catalysts" in md
    assert "ADHOC-CATALYSTS" in md


def test_render_with_watchlist_hit():
    from adhoc_scanner import filter_and_classify
    items = [
        make_item("CBK.DE: Übernahmeangebot"),
        make_item("Vodafone Plc: Gewinnwarnung 2025"),
    ]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    result = filter_and_classify(items, cutoff)
    md = render_markdown(result, ["CBK.DE"], dt.datetime.now(dt.timezone.utc))
    assert "Watchlist-Direkttreffer" in md
    assert "CBK.DE" in md
    assert "Vodafone" in md


# Mini-Test-Runner — funktioniert auch ohne pytest
if __name__ == "__main__":
    import inspect
    fns = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    passed = 0
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {name}: UNEXPECTED — {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
