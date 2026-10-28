"""2026-10-28 (User „A und C jetzt“): TP1-Klasse, Flag-Abstand, Dreh-Ort, Gegenfakt TP1 am Flag."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import mfe_mae as mm  # noqa: E402


def test_abstaende_in_r_long_und_short():
    m = mm.tp1_messung("Long", 100.0, 95.0, 1.2, 0.5, tp1=110.0, flag1=104.0, tp1_klasse="stark")
    assert m["TP1_R"] == 2.0 and m["Flag1_R"] == 0.8 and m["TP1_Klasse"] == "stark"
    s = mm.tp1_messung("Short", 100.0, 105.0, 1.0, None, tp1=90.0, flag1=96.0)
    assert s["TP1_R"] == 2.0 and s["Flag1_R"] == 0.8


def test_dreh_ort_klassen():
    f = lambda mfe: mm.tp1_messung("Long", 100, 95, mfe, -1.0, tp1=110, flag1=104)["Dreh_Ort"]
    assert f(0.3) == "vor Flag"
    assert f(0.9) == "am Flag"
    assert f(1.5) == "zwischen Flag und TP1"
    assert f(2.1) == "TP1 erreicht"
    assert mm.tp1_messung("Long", 100, 95, 1.0, -1.0, tp1=110, flag1=None)["Dreh_Ort"] == "vor TP1 (kein Flag)"


def test_gegenfakt_tp1_am_flag():
    m = mm.tp1_messung("Long", 100, 95, 0.9, -1.0, tp1=110, flag1=104)
    assert m["CF_TP1_Flag"] == round(0.8 / 3 + 2 / 3 * -1.0, 2)
    n = mm.tp1_messung("Long", 100, 95, 0.5, -1.0, tp1=110, flag1=104)
    assert n["CF_TP1_Flag"] == -1.0


def test_spalten_und_report():
    for c in mm.TP1_COLS:
        assert c in mm.CSV_OUT_COLS
    rep = "\n".join(mm.render_tp1_klasse([{"Status": "ok", "Dreh_Ort": "am Flag", "R": -1.0, "CF_TP1_Flag": -0.4}]))
    assert "| am Flag | 1 | -1.00 | -0.40 |" in rep


def test_flag1_klasse_und_kriterium():
    m = mm.tp1_messung("Long", 100, 95, 0.9, -1.0, tp1=110, flag1=104, flag1_klasse="Mittel")
    assert m["Flag1_Klasse"] == "mittel" and "Flag1_Klasse" in mm.CSV_OUT_COLS
    rows = [{"Status": "ok", "Dreh_Ort": "am Flag", "Flag1_Klasse": "mittel", "R": -1.0, "CF_TP1_Flag": -0.4}] * 9 + \
           [{"Status": "ok", "Dreh_Ort": "TP1 erreicht", "Flag1_Klasse": "mittel", "R": 1.5, "CF_TP1_Flag": 1.0}] * 11
    rep = "\n".join(mm.render_tp1_klasse(rows))
    assert "| mittel | 20 | 9 | 45% | erfuellt |" in rep
    rep2 = "\n".join(mm.render_tp1_klasse(rows[:5]))
    assert "| mittel | 5 | 5 | 100% | n < 20 |" in rep2
