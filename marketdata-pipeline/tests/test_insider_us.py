"""Tests für insider_us_scanner.py (Paket C1) — keine Netzwerk-Abhängigkeit.

Abgedeckt:
- Form-4-XML-Parse (Codes P/S, Rollen, 10b5-1-Checkbox, Joint Filings)
- Cluster-Logik Buy (≥2 Organe ≥ Schwelle) inkl. Einzelkauf-Abgrenzung
- Sell-Regeln (Cluster-only, CEO/CFO-groß-Pfad)
- Earnings-Nähe-Annotation (±5 KT, gemockt)
- Renderer-Smoke (Sektionen, bevorzugte Earnings-Nähe-Sortierung)
"""

import datetime as dt
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import insider_us_scanner as ius  # noqa: E402


def _form4_xml(owner_blocks: str, tx_blocks: str, plan: str = "0") -> str:
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Test Corp</issuerName>
    <issuerTradingSymbol>TST</issuerTradingSymbol>
  </issuer>
  {owner_blocks}
  <aff10b5One>{plan}</aff10b5One>
  <nonDerivativeTable>
  {tx_blocks}
  </nonDerivativeTable>
</ownershipDocument>"""


def _owner(name: str, director: str = "0", officer: str = "0", title: str = "") -> str:
    return f"""<reportingOwner>
      <reportingOwnerId><rptOwnerName>{name}</rptOwnerName></reportingOwnerId>
      <reportingOwnerRelationship>
        <isDirector>{director}</isDirector>
        <isOfficer>{officer}</isOfficer>
        <officerTitle>{title}</officerTitle>
      </reportingOwnerRelationship>
    </reportingOwner>"""


def _tx(code: str, date: str, shares: float, price: float) -> str:
    return f"""<nonDerivativeTransaction>
      <transactionDate><value>{date}</value></transactionDate>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{'A' if code == 'P' else 'D'}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>"""


def test_parse_basic_buy():
    xml = _form4_xml(_owner("Doe Jane", director="1"), _tx("P", "2026-06-05", 1000, 60.0))
    txs = ius.parse_form4(xml, "acc-1")
    assert len(txs) == 1
    t = txs[0]
    assert t.ticker == "TST" and t.code == "P"
    assert t.value_usd == 60_000
    assert t.is_director and not t.is_officer
    assert not t.is_10b5_1
    assert t.role_label == "Director"


def test_parse_10b5_1_flag_and_ceo():
    xml = _form4_xml(
        _owner("Smith John", officer="1", title="Chief Executive Officer"),
        _tx("S", "2026-06-04", 10000, 60.0), plan="1",
    )
    txs = ius.parse_form4(xml, "acc-2")
    assert txs[0].is_10b5_1 and txs[0].is_ceo_cfo
    assert txs[0].value_usd == 600_000


def test_parse_ignores_non_ps_codes():
    xml = _form4_xml(_owner("Doe Jane", director="1"),
                     _tx("A", "2026-06-05", 5000, 60.0))  # Award, kein Open-Market
    assert ius.parse_form4(xml, "acc-3") == []


def test_parse_joint_filing_two_owners():
    xml = _form4_xml(
        _owner("Doe Jane", director="1") + _owner("Smith John", officer="1", title="CFO"),
        _tx("P", "2026-06-05", 1000, 60.0),
    )
    txs = ius.parse_form4(xml, "acc-4")
    assert len(txs) == 2  # beide Owner bekommen die Zeile zugeordnet
    assert {t.owner_name for t in txs} == {"Doe Jane", "Smith John"}


def _mk_tx(owner, code, date, value, director=True, officer=False,
           title="", plan=False):
    return ius.InsiderTx(
        ticker="TST", issuer_name="Test Corp", owner_name=owner,
        is_director=director, is_officer=officer, officer_title=title,
        code=code, date=dt.date.fromisoformat(date),
        shares=value / 50.0, price=50.0, value_usd=value,
        is_10b5_1=plan, accession="acc",
    )


def test_buy_cluster_requires_two_insiders_over_threshold():
    txs = [
        _mk_tx("A", "P", "2026-06-03", 60_000),
        _mk_tx("B", "P", "2026-06-05", 70_000),
        _mk_tx("C", "P", "2026-06-05", 10_000),  # unter Schwelle, zählt nicht
    ]
    cluster, sell, singles = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert cluster is not None and cluster.is_cluster
    assert len(cluster.owners) == 2
    assert cluster.total_usd == 130_000
    assert sell is None and singles == []


def test_single_buy_no_cluster():
    txs = [_mk_tx("A", "P", "2026-06-03", 80_000)]
    cluster, sell, singles = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert cluster is None and len(singles) == 1


def test_owner_aggregation_sums_multiple_buys():
    # Ein Insider, zwei Käufe je 30k → Summe 60k über Schwelle
    txs = [
        _mk_tx("A", "P", "2026-06-03", 30_000),
        _mk_tx("A", "P", "2026-06-04", 30_000),
        _mk_tx("B", "P", "2026-06-05", 60_000),
    ]
    cluster, _, _ = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert cluster is not None and len(cluster.owners) == 2


def test_non_organ_owner_not_counted():
    # 10%-Owner ohne Organfunktion zählt nicht für Cluster (Note #48)
    txs = [
        _mk_tx("Fund LP", "P", "2026-06-03", 900_000, director=False),
        _mk_tx("B", "P", "2026-06-05", 60_000),
    ]
    cluster, _, singles = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert cluster is None and len(singles) == 1


def test_sell_single_small_is_dropped():
    txs = [_mk_tx("A", "S", "2026-06-03", 80_000)]
    _, sell, _ = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert sell is None


def test_sell_cluster_qualifies():
    txs = [
        _mk_tx("A", "S", "2026-06-03", 80_000),
        _mk_tx("B", "S", "2026-06-04", 90_000),
    ]
    _, sell, _ = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert sell is not None and sell.is_cluster


def test_sell_ceo_big_single_path():
    txs = [_mk_tx("CEO X", "S", "2026-06-03", 600_000,
                  director=False, officer=True, title="Chief Executive Officer")]
    _, sell, _ = ius.evaluate_issuer("TST", "Test Corp", txs)
    assert sell is not None and not sell.is_cluster
    # Earnings-Nähe-Pflicht wird in run_scan durchgesetzt, nicht hier


def test_earnings_annotation(monkeypatch):
    txs = [
        _mk_tx("A", "P", "2026-06-03", 60_000),
        _mk_tx("B", "P", "2026-06-05", 70_000),
    ]
    cluster, _, _ = ius.evaluate_issuer("TST", "Test Corp", txs)
    monkeypatch.setattr(
        ius, "fetch_earnings_dates",
        lambda t: (dt.date(2026, 6, 1), dt.date(2026, 9, 1)),
    )
    ius.annotate_earnings_proximity(cluster)
    # 2026-06-03 liegt 2 KT nach last earnings 2026-06-01 → near
    assert cluster.earnings_near and cluster.earnings_date == "2026-06-01"
    assert cluster.earnings_kind == "last"


def test_earnings_annotation_outside_window(monkeypatch):
    txs = [
        _mk_tx("A", "P", "2026-06-03", 60_000),
        _mk_tx("B", "P", "2026-06-05", 70_000),
    ]
    cluster, _, _ = ius.evaluate_issuer("TST", "Test Corp", txs)
    monkeypatch.setattr(
        ius, "fetch_earnings_dates",
        lambda t: (dt.date(2026, 5, 20), dt.date(2026, 8, 20)),
    )
    ius.annotate_earnings_proximity(cluster)
    assert not cluster.earnings_near


def test_renderer_sections_and_priority(monkeypatch):
    res = ius.ScanResult()
    near = ius.IssuerSignal(
        ticker="NEAR", issuer_name="Near Corp", direction="BUY",
        owners=[], total_usd=100_000,
        window_start=dt.date(2026, 6, 3), window_end=dt.date(2026, 6, 5),
        is_cluster=True, earnings_near=True,
        earnings_date="2026-06-04", earnings_kind="last",
    )
    far = ius.IssuerSignal(
        ticker="FARX", issuer_name="Far Corp", direction="BUY",
        owners=[], total_usd=900_000,
        window_start=dt.date(2026, 6, 3), window_end=dt.date(2026, 6, 5),
        is_cluster=True,
    )
    res.buy_clusters = [near, far]
    md = ius.render_markdown(res, dt.datetime(2026, 6, 10, 7, 0))
    assert "BEVORZUGT" in md
    assert md.index("NEAR") < md.index("FARX")  # Earnings-Nähe zuerst
    assert "Insider-Kauf-Cluster" in md


def test_renderer_empty():
    md = ius.render_markdown(ius.ScanResult(), dt.datetime(2026, 6, 10, 7, 0))
    assert "Keine Insider-Signale" in md
