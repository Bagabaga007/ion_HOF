"""QM 输出解析器测试 (最小文本片段)。"""

import pytest

from bppa_hof.parsers import parse_gaussian, parse_orca
from bppa_hof.parsers.base import detect_program

pytestmark = pytest.mark.unit

GAUSSIAN_G4 = """
 Entering Gaussian System, Link 0=g16
 SCF Done:  E(RB3LYP) =  -112.500000000     A.U. after   10 cycles
 G4 Enthalpy=          -112.120023 G4 Free Energy=          -112.150000
 Normal termination of Gaussian 16
"""

GAUSSIAN_VOLUME = """
 Entering Gaussian System, Link 0=g16
                Molar volume =       28.479 cm**3/mol (0.001 electron/bohr**3)
 Normal termination of Gaussian 16
"""

ORCA_FREQ = """
                       * O   R   C   A *
THE OPTIMIZATION HAS CONVERGED
   1:       -5.000000 cm**-1
   2:     1234.500000 cm**-1
FINAL SINGLE POINT ENERGY      -273.664407000
Total correction                           0.050000 Eh
Thermal Enthalpy correction                0.000944 Eh
Total Enthalpy                          -273.600000 Eh
ORCA TERMINATED NORMALLY
"""

ORCA_SINGLE_POINT = """
                       * O   R   C   A *
FINAL SINGLE POINT ENERGY      -54.571306000
ORCA TERMINATED NORMALLY
"""


def test_detect_program():
    assert detect_program(GAUSSIAN_G4) == "gaussian"
    assert detect_program(ORCA_FREQ) == "orca"


def test_parse_gaussian_g4_enthalpy():
    r = parse_gaussian(GAUSSIAN_G4)
    assert r.total_enthalpy_hartree == pytest.approx(-112.120023)
    assert r.scf_hartree == pytest.approx(-112.5)
    assert r.enthalpy() == pytest.approx(-112.120023)


def test_parse_gaussian_volume():
    r = parse_gaussian(GAUSSIAN_VOLUME)
    assert r.molar_volume_cm3_mol == pytest.approx(28.479)


def test_parse_orca_total_enthalpy():
    r = parse_orca(ORCA_FREQ)
    assert r.scf_hartree == pytest.approx(-273.664407)
    assert r.total_enthalpy_hartree == pytest.approx(-273.600000)
    assert r.enthalpy() == pytest.approx(-273.600000)
    assert r.optimization_converged is True
    assert r.frequencies_cm1 == pytest.approx((-5.0, 1234.5))
    assert r.imaginary_frequencies() == ()


def test_parse_orca_single_point():
    r = parse_orca(ORCA_SINGLE_POINT)
    assert r.scf_hartree == pytest.approx(-54.571306)
    # 无频率计算, 焓退化为 SCF
    assert r.enthalpy() == pytest.approx(-54.571306)
