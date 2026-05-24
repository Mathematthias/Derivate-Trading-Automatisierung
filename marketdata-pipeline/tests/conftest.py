"""pytest-Konfiguration fuer die marketdata-pipeline-Tests.

Legt `marketdata-pipeline/src` auf `sys.path`, damit die Testmodule die
Pipeline-Pakete (`filter_engine`, `market_data`, ...) direkt importieren
koennen — unabhaengig davon, ob die Suite als Ganzes (`pytest tests/`) oder
eine einzelne Datei (`pytest tests/test_filter_pending.py`) gestartet wird.

Hintergrund (2026-05-24): Die meisten Testdateien hatten ein eigenes
`sys.path.insert`; zwei (`test_filter_pending.py`, `test_state_parser_patches.py`)
jedoch nicht und importierten nur durch, weil eine alphabetisch fruehere Datei
den Pfad als Seiteneffekt gesetzt hatte. Ein Einzeldatei-Lauf dieser beiden
brach mit ModuleNotFoundError. pytest laedt conftest.py vor der Collection —
das behebt das invokations-unabhaengig. Die per-Datei-`sys.path.insert` sind
damit redundant, aber harmlos und bleiben unangetastet.
"""
import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
