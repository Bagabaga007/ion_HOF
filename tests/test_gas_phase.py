"""气相生成焓测试, 锚定文档验证例 H5N7 (五唑肼盐) = 241.8 kcal/mol。"""

import pytest

from bppa_hof import gas_phase_hof, single_point_atom_enthalpy_hartree
from bppa_hof.atom_data import AtomData
from bppa_hof.constants import SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE

pytestmark = pytest.mark.unit


def test_h5n7_gas_phase_g4():
    # 整盐总焓 = 1a(N5-) + 1c(N2H5+) 的 G4 焓之和
    molecule_h = -273.664407 + -112.120023  # Hartree
    composition = {"N": 7, "H": 5}
    atom_enthalpies = {"H": -0.49906, "N": -54.571306}

    hof = gas_phase_hof(molecule_h, composition, atom_enthalpies)
    # 文档: 1a+1c 气态生成焓为 241.825 kcal/mol
    assert hof == pytest.approx(241.825, abs=0.5)


def test_single_point_atom_correction():
    scf = -54.5
    got = single_point_atom_enthalpy_hartree(scf)
    assert got == pytest.approx(scf + SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE)


def test_missing_atom_energy_raises():
    with pytest.raises(KeyError):
        gas_phase_hof(-100.0, {"N": 2, "C": 1}, {"N": -54.5})


def test_default_atom_data_values():
    data = AtomData.default()
    assert data.exp_hof("N") == pytest.approx(112.970)
    assert data.exp_hof("H") == pytest.approx(52.103)
    assert data.multiplicity_of("N") == 4
