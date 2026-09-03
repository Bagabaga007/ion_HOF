"""盐固态生成焓全链路测试, 锚定 H5N7 = 102.58 kcal/mol。"""

import pytest

from bppa_hof import Ion, Salt

pytestmark = pytest.mark.unit


def _h5n7_salt():
    anion = Ion(
        "N5", charge=-1,
        enthalpy_hartree=-273.664407, volume_cm3_mol=44.640,
        shape="nonlinear",
    )
    cation = Ion(
        "N2H5", charge=1,
        enthalpy_hartree=-112.120023, volume_cm3_mol=28.479,
        shape="nonlinear",
    )
    return Salt(
        [anion, cation],
        method="G4",
        atom_enthalpies_hartree={"H": -0.49906, "N": -54.571306},
        label="1a+1c",
    )


def test_h5n7_solid_hof():
    salt = _h5n7_salt()
    result = salt.compute()
    assert result.composition == {"N": 7, "H": 5}
    assert result.gas_phase_hof == pytest.approx(241.825, abs=0.5)
    assert result.lattice_enthalpy == pytest.approx(139.240, abs=0.5)
    # 文档: 固态生成焓为 102.58 kcal/mol
    assert result.solid_hof == pytest.approx(102.58, abs=0.6)


def test_non_neutral_salt_rejected():
    a = Ion("N5", charge=-1, enthalpy_hartree=-273.0, volume_cm3_mol=44.0)
    with pytest.raises(ValueError, match="电荷未配平"):
        Salt([a], method="G4")


def test_missing_enthalpy_raises():
    a = Ion("N5", charge=-1, volume_cm3_mol=44.0)
    c = Ion("N2H5", charge=1, volume_cm3_mol=28.0)
    salt = Salt([a, c], method="G4", atom_enthalpies_hartree={"H": 0, "N": 0})
    with pytest.raises(ValueError, match="缺少 enthalpy_hartree"):
        salt.gas_phase_hof()
