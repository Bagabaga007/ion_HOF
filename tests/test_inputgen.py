"""几何与输入生成测试。"""

import pytest

from bppa_hof.geometry import Molecule, single_atom
from bppa_hof.inputgen import (
    G4,
    ORCA_OPT_FREQ,
    atom_inputs,
    build_gaussian,
    build_orca,
    ion_inputs,
)

pytestmark = pytest.mark.unit

XYZ = """3
water
O   0.000000   0.000000   0.117300
H   0.000000   0.757200  -0.469200
H   0.000000  -0.757200  -0.469200
"""


def _write_xyz(tmp_path):
    p = tmp_path / "water.xyz"
    p.write_text(XYZ)
    return str(p)


def test_from_xyz(tmp_path):
    mol = Molecule.from_xyz(_write_xyz(tmp_path), charge=0, multiplicity=1)
    assert mol.composition() == {"O": 1, "H": 2}
    assert mol.name == "water"
    assert len(mol.atoms) == 3


def test_single_atom_multiplicity():
    assert single_atom("N").multiplicity == 4
    assert single_atom("H").multiplicity == 2
    assert single_atom("C").multiplicity == 3


def test_single_atom_unknown_element():
    with pytest.raises(KeyError):
        single_atom("Xe")


def test_gaussian_g4_input():
    mol = Molecule([("N", 0.0, 0.0, 0.0), ("N", 0.0, 0.0, 1.1)], charge=-1, multiplicity=1, name="n2")
    text = build_gaussian(mol, G4)
    assert "#p G4" in text
    assert "%chk=n2.chk" in text
    assert "-1 1" in text
    assert text.count("N ") >= 1


def test_orca_opt_freq_input():
    mol = Molecule([("N", 0.0, 0.0, 0.0)], charge=-1, multiplicity=1, name="x")
    text = build_orca(mol, ORCA_OPT_FREQ)
    assert text.startswith("! RIJCOSX B3LYP def2-SVP def2/J Opt Freq")
    assert "* xyz -1 1" in text
    assert text.rstrip().endswith("*")


def test_ion_inputs_orca_set():
    mol = Molecule([("N", 0.0, 0.0, 0.0)] * 5, charge=-1, name="N5")
    got = ion_inputs(mol, program="orca")
    assert "opt_freq" in got and "sp" not in got and "volume" in got
    # 体积用 Gaussian 生成
    assert got["volume"][0].endswith(".gjf")
    assert "Volume" in got["volume"][1]

    optimized = Molecule(
        [("N", 0.0, 0.0, float(i)) for i in range(5)],
        charge=-1,
        name="optimized",
    )
    staged = ion_inputs(mol, program="orca", optimized_molecule=optimized)
    assert "sp" in staged
    assert staged["sp"][0] == "N5_sp.inp"


def test_ion_inputs_gaussian_set():
    mol = Molecule([("N", 0.0, 0.0, 0.0)] * 5, charge=-1, name="N5")
    got = ion_inputs(mol, program="gaussian")
    assert "energy" in got
    assert got["energy"][0].endswith(".gjf")
    assert "#p G4" in got["energy"][1]


def test_atom_inputs():
    got = atom_inputs(["N", "H"], program="gaussian")
    assert set(got) == {"N", "H"}
    # N 单原子多重度 4
    assert "0 4" in got["N"][1]
    assert "0 2" in got["H"][1]


def test_orca_high_level_uses_orca_keyword_spelling():
    got = atom_inputs(["H"], program="orca")["H"][1]
    assert "M062X" in got
    assert "M06-2X" not in got
