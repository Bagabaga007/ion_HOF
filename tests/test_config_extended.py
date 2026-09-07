"""TOML、文件解析和方法配置契约测试。"""

from pathlib import Path

import pytest

from bppa_hof.config import (
    _enthalpy_from_files,
    _ion_from_config,
    _resolve,
    load_config,
)
from bppa_hof.constants import SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE

pytestmark = pytest.mark.config

GAUSSIAN_ENERGY = """Entering Gaussian System
SCF Done: E(RHF) = -1.100000 A.U.
G4 Enthalpy= -1.000000 G4 Free Energy= -1.010000
Normal termination of Gaussian 16
"""

GAUSSIAN_VOLUME = """Entering Gaussian System
Molar volume = 10.500 cm**3/mol
Normal termination of Gaussian 16
"""

ORCA_SP = """* O   R   C   A *
FINAL SINGLE POINT ENERGY -2.000000
ORCA TERMINATED NORMALLY
"""

ORCA_THERMAL = """* O   R   C   A *
THE OPTIMIZATION HAS CONVERGED
FINAL SINGLE POINT ENERGY -1.000000
Total Enthalpy -0.900000 Eh
ORCA TERMINATED NORMALLY
"""


def _write(path: Path, text: str) -> str:
    path.write_text(text)
    return str(path)


def test_resolve_and_enthalpy_file_modes(tmp_path):
    assert _resolve(None, str(tmp_path)) is None
    absolute = str((tmp_path / "absolute.out").resolve())
    assert _resolve(absolute, "ignored") == absolute
    assert _resolve("relative.out", str(tmp_path)) == str(tmp_path / "relative.out")

    gaussian = _write(tmp_path / "g.log", GAUSSIAN_ENERGY)
    sp = _write(tmp_path / "sp.out", ORCA_SP)
    thermal = _write(tmp_path / "thermal.out", ORCA_THERMAL)
    assert _enthalpy_from_files(gaussian, "") == -1.0
    assert _enthalpy_from_files(sp, "", thermal_file=thermal) == pytest.approx(-1.9)
    assert _enthalpy_from_files(
        sp, "", apply_single_atom_correction=True
    ) == pytest.approx(-2.0 + SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE)
    with pytest.raises(ValueError, match="不能同时"):
        _enthalpy_from_files(
            sp,
            "",
            thermal_file=thermal,
            apply_single_atom_correction=True,
        )
    no_energy = _write(
        tmp_path / "no_energy.log",
        "Entering Gaussian System\nNormal termination of Gaussian 16\n",
    )
    with pytest.raises(ValueError, match="SCF"):
        _enthalpy_from_files(no_energy, "", apply_single_atom_correction=True)


def test_ion_config_uses_energy_thermal_and_volume_files(tmp_path):
    _write(tmp_path / "sp.out", ORCA_SP)
    thermal = _write(tmp_path / "thermal.out", ORCA_THERMAL)
    _write(tmp_path / "volume.log", GAUSSIAN_VOLUME)
    ion = _ion_from_config(
        {
            "formula": "H",
            "charge": 1,
            "energy_file": "sp.out",
            "thermal_file": "thermal.out",
            "volume_file": "volume.log",
        },
        str(tmp_path),
    )
    assert ion.enthalpy_hartree == pytest.approx(-1.9)
    assert ion.volume_cm3_mol == 10.5

    with pytest.raises(ValueError, match="thermal_file"):
        _ion_from_config(
            {
                "formula": "H",
                "charge": 1,
                "enthalpy_hartree": -1.0,
                "thermal_file": thermal,
            },
            str(tmp_path),
        )


def test_load_config_all_atom_file_forms_and_overrides(tmp_path):
    _write(tmp_path / "h.log", GAUSSIAN_ENERGY)
    _write(tmp_path / "n.out", ORCA_SP)
    config = tmp_path / "config.toml"
    config.write_text(
        """
[method]
name = "mixed"
[method.atom_energy_files]
H = "h.log"
[method.atom_energy_files.N]
path = "n.out"
apply_single_atom_correction = true

[atom_exp_hof_kcal_mol]
H = 53.0

[[salt]]
label = "pair"
reference = 1.5
  [[salt.ion]]
  formula = "H"
  charge = -1
  enthalpy_hartree = -1.0
  volume_cm3_mol = 10.0
  [[salt.ion]]
  formula = "H"
  charge = 1
  enthalpy_hartree = -1.0
  volume_cm3_mol = 10.0

[[salt]]
  [[salt.ion]]
  formula = "H"
  charge = -1
  enthalpy_hartree = -1.0
  volume_cm3_mol = 10.0
  [[salt.ion]]
  formula = "H"
  charge = 1
  enthalpy_hartree = -1.0
  volume_cm3_mol = 10.0
"""
    )
    cfg = load_config(str(config))
    assert cfg.method == "mixed"
    assert cfg.atom_enthalpies_hartree["H"] == -1.0
    assert cfg.atom_enthalpies_hartree["N"] == pytest.approx(
        -2.0 + SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE
    )
    assert cfg.atom_data.exp_hof("H") == 53.0
    assert len(cfg.salts) == 2
    assert cfg.references == {"pair": 1.5}

    empty = tmp_path / "empty.toml"
    empty.write_text("")
    empty_cfg = load_config(str(empty))
    assert empty_cfg.method == "unspecified" and empty_cfg.salts == []


@pytest.mark.parametrize(
    "atom_section, error, message",
    [
        ("[method.atom_energy_files.N]\n", ValueError, "缺少 energy_file"),
        ("[method.atom_energy_files]\nN = 42\n", TypeError, "必须是路径或表"),
    ],
)
def test_invalid_atom_energy_specs(tmp_path, atom_section, error, message):
    config = tmp_path / "invalid.toml"
    config.write_text("[method]\nname='x'\n" + atom_section)
    with pytest.raises(error, match=message):
        load_config(str(config))


def test_source_manifest_includes_test_gate_and_validation_docs():
    root = Path(__file__).resolve().parents[1]
    manifest = (root / "MANIFEST.in").read_text()
    assert "recursive-include tests *.py" in manifest
    assert "recursive-include docs *.md" in manifest
    assert "recursive-include examples" in manifest


def test_project_profile_metadata_contract():
    root = Path(__file__).resolve().parents[1]
    profile = (root / "docs/project-profile.md").read_text()
    assert "enthalpy-of-formation" in profile
    assert "Gaussian" in profile and "ORCA" in profile
