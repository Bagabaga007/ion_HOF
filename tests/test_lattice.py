"""晶格焓 (VBT) 测试, 锚定文档验证例 H5N7 = 139.2 kcal/mol。"""

import pytest

from bppa_hof import Ion, ionic_strength, lattice_enthalpy_kcal
from bppa_hof.lattice import lattice_energy_kj
from bppa_hof.constants import CM3_MOL_TO_NM3

pytestmark = pytest.mark.unit


def _h5n7_ions():
    anion = Ion("N5", charge=-1, volume_cm3_mol=44.640, shape="nonlinear")
    cation = Ion("N2H5", charge=1, volume_cm3_mol=28.479, shape="nonlinear")
    return [anion, cation]


def test_h5n7_lattice_enthalpy():
    ions = _h5n7_ions()
    volume = 44.640 + 28.479  # cm^3/mol
    dh_l = lattice_enthalpy_kcal(volume, ions)
    # 文档: 晶格焓为 139.240 kcal/mol
    assert dh_l == pytest.approx(139.240, abs=0.5)


def test_ionic_strength_1_1_salt():
    assert ionic_strength(_h5n7_ions()) == pytest.approx(1.0)


def test_upot_below_threshold_uses_alpha_beta():
    # 1:1 盐典型体积落在 U_POT < 5000 分支
    volume_nm3 = 73.119 * CM3_MOL_TO_NM3
    upot = lattice_energy_kj(volume_nm3, 1.0)
    assert upot < 5000.0
    assert upot == pytest.approx(577.0, abs=5.0)


def test_lattice_energy_scales_inverse_with_volume():
    # 体积越小晶格能越大 (文档: 离子尺寸越小晶格能越大)
    small = lattice_energy_kj(0.05, 1.0)
    large = lattice_energy_kj(0.20, 1.0)
    assert small > large
