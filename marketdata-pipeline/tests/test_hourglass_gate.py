"""
test_hourglass_gate.py — Regression für den ⏳-Blindfleck-Fix (2026-07-23).

Vorher: `_evaluate_trigger` übersprang JEDEN ⏳-Trigger blind ('far'). Ein
⏳-Eintrag, dessen Kurs längst in der Trigger-Zone lag, wurde nie gebucketet
und tauchte nie als NAHE/BEREIT auf (Anlassfall MRK: 0,2 ATR am Trigger, aber
⏳ → unsichtbar).

Fix: ⏳ wird nur noch übersprungen, wenn der Trigger KEINEN auswertbaren Preis
hat (echte "warte auf Datum/Event"-Trigger, z.B. PEAD-Event-Legs). Ein ⏳ MIT
Preis-Op wird normal ausgewertet — das Datum ist ohnehin entry-seitig über
earliest_date → pending abgedeckt.
"""
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from filter_engine import _evaluate_trigger          # noqa: E402
from state_parser import ParsedTrigger               # noqa: E402
from test_verdeckt_bereit import FakeSnap            # noqa: E402  (reuse fixture)


@pytest.fixture
def config():
    path = os.path.join(os.path.dirname(__file__), "..", "config", "filter_config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def _snap_in_zone():
    # Kurs 139,25 mitten in der Zone 139–141 (MRK-Anlassfall)
    return FakeSnap(
        symbol="MRK.DE", price=139.25, rsi14=53.0,
        today_open=137.85, today_high=140.0, today_low=134.95, today_close=139.25,
        prev_open=137.0, prev_close=138.0,
    )


def test_hourglass_mit_preis_wird_ausgewertet(config):
    """⏳ + Preis-Zone → NICHT mehr übersprungen (der Blindfleck-Fix)."""
    t = ParsedTrigger(
        label="A", raw="Touch 139-141€ [pullback]",
        price_low=139.0, price_high=141.0, price_op="in_range",
        zone_kind="pullback", gate="⏳",
    )
    ts = _evaluate_trigger(t, _snap_in_zone(), "LONG", config, now_utc_hour=14)
    assert "wartet" not in ts.summary          # nicht mehr der Skip-Pfad
    assert ts.proximity != "far"               # wird real gebucketet


def test_hourglass_preislos_bleibt_skip(config):
    """⏳ ohne Preis (Event-Leg) → weiterhin 'far' übersprungen."""
    t = ParsedTrigger(label="A", raw="nach Earnings Gap-up", price_op=None, gate="⏳")
    ts = _evaluate_trigger(t, _snap_in_zone(), "LONG", config, now_utc_hour=14)
    assert ts.proximity == "far"
    assert "wartet" in ts.summary


def test_tot_gate_bleibt_immer_skip(config):
    """🔴 wird unverändert immer übersprungen (Kontroll-Fall)."""
    t = ParsedTrigger(
        label="A", raw="Touch 139-141€", price_low=139.0, price_high=141.0,
        price_op="in_range", gate="🔴",
    )
    ts = _evaluate_trigger(t, _snap_in_zone(), "LONG", config, now_utc_hour=14)
    assert ts.proximity == "far"
    assert "tot" in ts.summary
