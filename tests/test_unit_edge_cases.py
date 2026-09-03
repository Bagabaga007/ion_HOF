"""纯函数、模型、解析器和数值边界的单元测试。"""

import pytest

from bppa_hof.atom_data import AtomData
from bppa_hof.deviation import DeviationEntry, DeviationReport
from bppa_hof.geometry import Molecule, single_atom
from bppa_hof.inputgen import (
    GaussianRecipe,
    OrcaRecipe,
    atom_inputs,
    build_gaussian,
    build_orca,
    gaussian_input,
    ion_inputs,
    orca_input,
)
from bppa_hof.lattice import lattice_energy_kj
from bppa_hof.models import (
    Ion,
    QMResult,
    combine_single_point_and_thermal,
    parse_formula,
)
from bppa_hof.parsers.base import detect_program, parse_output, search_last, to_float
from bppa_hof.parsers.gaussian import parse_gaussian
from bppa_hof.parsers.orca import parse_orca
from bppa_hof.salt import HofResult, Salt

pytestmark = pytest.mark.unit


def test_atom_data_unknown_and_overrides():
    data = AtomData.default()
    with pytest.raises(KeyError, match="无实验生成焓"):
        data.exp_hof("Xe")
    with pytest.raises(KeyError, match="无多重度"):
        data.multiplicity_of("Xe")
    same = data.with_overrides()
    assert same.exp_hof("H") == data.exp_hof("H")
    changed = data.with_overrides({"Xe": 1.25}, {"Xe": 3})
    assert changed.exp_hof("Xe") == 1.25
    assert changed.multiplicity_of("Xe") == 3


def test_deviation_empty_extrema_and_formatting():
    empty = DeviationReport([])
    with pytest.raises(ValueError, match="MAE"):
        _ = empty.mae
    with pytest.raises(ValueError, match="RMSD"):
        _ = empty.rmsd
    report = DeviationReport(
        [DeviationEntry("positive", 3.0, 1.0), DeviationEntry("negative", 0.0, 1.0)]
    )
    assert report.max_positive.label == "positive"
    assert report.max_negative.label == "negative"
    assert "RMSD" in report.format_table()


def test_molecule_validation_and_xyz_errors(tmp_path):
    with pytest.raises(ValueError, match="至少需要"):
        Molecule([])
    with pytest.raises(ValueError, match="多重度"):
        Molecule([("H", 0.0, 0.0, 0.0)], multiplicity=0)

    short = tmp_path / "short.xyz"
    short.write_text("1\ncomment\n")
    with pytest.raises(ValueError, match="内容不足"):
        Molecule.from_xyz(str(short))

    bad_n = tmp_path / "bad_n.xyz"
    bad_n.write_text("x\ncomment\nH 0 0 0\n")
    with pytest.raises(ValueError, match="首行"):
        Molecule.from_xyz(str(bad_n))

    missing_coord = tmp_path / "missing.xyz"
    missing_coord.write_text("2\ncomment\nH 0 0 0\nH 0 0\n")
    with pytest.raises(ValueError, match="实际解析"):
        Molecule.from_xyz(str(missing_coord))

    valid = tmp_path / "valid.xyz"
    valid.write_text("1\ncomment\nH 0 0 0\n")
    assert Molecule.from_xyz(str(valid), name="explicit").name == "explicit"
    assert single_atom("Xe", multiplicity=1).multiplicity == 1


def test_low_level_input_rendering_optional_fields():
    molecule = Molecule([("H", 0.0, 0.0, 0.0)], name="h")
    gaussian = gaussian_input(
        molecule,
        "HF/3-21G",
        nprocshared=0,
        mem="",
        chk=None,
        title="custom",
        extra_tail="tail\n",
    )
    assert gaussian.startswith("#p HF/3-21G")
    assert "%mem" not in gaussian and "custom" in gaussian and "tail" in gaussian
    no_tail = gaussian_input(molecule, "#p HF/3-21G", extra_tail="")
    assert "#p HF/3-21G" in no_tail

    orca = orca_input(
        molecule,
        "! HF 3-21G",
        nprocs=1,
        maxcore_mb=0,
        blocks="%scf MaxIter 5 end\n",
    )
    assert "%pal" not in orca and "%maxcore" not in orca
    assert "%scf MaxIter 5 end" in orca
    minimal = orca_input(molecule, "HF", nprocs=0, maxcore_mb=0)
    assert "%scf" not in minimal

    assert "%chk" not in build_gaussian(
        molecule, GaussianRecipe("#p HF", use_chk=False)
    )
    assert "%pal" not in build_orca(
        molecule, OrcaRecipe("HF", nprocs=1, maxcore_mb=0)
    )


def test_ion_and_atom_input_error_branches():
    molecule = Molecule([("N", 0.0, 0.0, 0.0)], charge=-1, name="n")
    no_volume = ion_inputs(molecule, program="gaussian", volume=False)
    assert set(no_volume) == {"energy"}
    no_sp = ion_inputs(molecule, program="orca", high_level_sp=False, volume=False)
    assert set(no_sp) == {"opt_freq"}
    with pytest.raises(ValueError, match="未知 program"):
        ion_inputs(molecule, program="unknown")

    wrong_atoms = Molecule([("H", 0.0, 0.0, 0.0)], charge=-1)
    with pytest.raises(ValueError, match="元素组成"):
        ion_inputs(molecule, program="orca", optimized_molecule=wrong_atoms)
    wrong_state = Molecule([("N", 0.0, 0.0, 0.0)], charge=0)
    with pytest.raises(ValueError, match="电荷或多重度"):
        ion_inputs(molecule, program="orca", optimized_molecule=wrong_state)

    assert atom_inputs(["N"], program="orca")["N"][0].endswith(".inp")
    with pytest.raises(ValueError, match="未知 program"):
        atom_inputs(["N"], program="psi4")


def test_lattice_high_energy_and_invalid_volume():
    with pytest.raises(ValueError, match="体积"):
        lattice_energy_kj(0.0, 1.0)
    with pytest.raises(ValueError, match="仅适用于"):
        lattice_energy_kj(1e-9, 4.0)
    assert lattice_energy_kj(1e-9, 4.0, allow_extrapolation=True) > 5000.0


def test_formula_qmresult_and_ion_error_branches():
    with pytest.raises(ValueError, match="不能为空"):
        parse_formula("  ")
    with pytest.raises(ValueError, match="位置"):
        parse_formula("N2-")

    q = QMResult(frequencies_cm1=(-20.0, -5.0, 100.0), scf_hartree=-10.0)
    assert q.imaginary_frequencies() == (-20.0,)
    with pytest.raises(ValueError, match="阈值"):
        q.imaginary_frequencies(threshold_cm1=1.0)
    with pytest.raises(ValueError, match="热力学"):
        q.enthalpy(require_thermal_correction=True)
    assert QMResult(total_enthalpy_hartree=-9.0).enthalpy() == -9.0
    with pytest.raises(ValueError, match="缺少焓数据"):
        QMResult().enthalpy()

    good_sp = QMResult(terminated_normally=True, scf_hartree=-10.0)
    good_thermal = QMResult(
        terminated_normally=True,
        thermal_enthalpy_correction_hartree=0.1,
    )
    assert combine_single_point_and_thermal(good_sp, good_thermal) == -9.9
    with pytest.raises(ValueError, match="single_point 计算"):
        combine_single_point_and_thermal(QMResult(), good_thermal)
    with pytest.raises(ValueError, match="thermal 计算"):
        combine_single_point_and_thermal(good_sp, QMResult())
    with pytest.raises(ValueError, match="单点能"):
        combine_single_point_and_thermal(
            QMResult(terminated_normally=True), good_thermal
        )
    with pytest.raises(ValueError, match="热力学焓校正"):
        combine_single_point_and_thermal(
            good_sp, QMResult(terminated_normally=True)
        )

    with pytest.raises(ValueError, match="shape"):
        Ion("H", 0, shape="bent")
    with pytest.raises(ValueError, match="count"):
        Ion("H", 0, count=0)
    ion = Ion.from_qm("H", 0, QMResult(total_enthalpy_hartree=-0.5))
    assert ion.enthalpy_hartree == -0.5


def test_parser_helpers_detection_and_incomplete_outputs(tmp_path):
    assert to_float("-1.25D+02") == -125.0
    assert search_last(r"x=(\d+\.\d+)", "none") is None
    assert search_last(r"x=((\d+\.\d+))", "x=1.25", group=2) == 1.25
    assert detect_program("G4 Enthalpy= -1.0") == "gaussian"
    assert detect_program("FINAL SINGLE POINT ENERGY -1.0") == "orca"
    with pytest.raises(ValueError, match="无法识别"):
        detect_program("unknown")
    with pytest.raises(ValueError, match="未正常终止"):
        parse_gaussian("Entering Gaussian System\nSCF Done: E(RHF) = -1.0 A.U.")
    partial_g = parse_gaussian(
        "Entering Gaussian System\nSCF Done: E(RHF) = -1.0 A.U.",
        require_normal_termination=False,
    )
    assert partial_g.terminated_normally is False
    with pytest.raises(ValueError, match="未正常终止"):
        parse_orca("* O   R   C   A *\nFINAL SINGLE POINT ENERGY -1.0")
    partial_o = parse_orca(
        "* O   R   C   A *\nFINAL SINGLE POINT ENERGY -1.0",
        require_normal_termination=False,
    )
    assert partial_o.terminated_normally is False

    gaussian_path = tmp_path / "g.log"
    gaussian_path.write_text(
        "Entering Gaussian System\n"
        "Optimization completed\n"
        "Frequencies -- -20.0 100.0 200.0\n"
        "CBS-QB3 Enthalpy= -2.500000\n"
        "Normal termination of Gaussian 16\n"
    )
    parsed_g = parse_gaussian(str(gaussian_path))
    assert parsed_g.source == str(gaussian_path.resolve())
    assert parsed_g.optimization_converged is True
    assert parsed_g.frequencies_cm1 == (-20.0, 100.0, 200.0)
    assert parsed_g.total_enthalpy_hartree == -2.5
    assert parse_output(str(gaussian_path)).program == "gaussian"

    orca_path = tmp_path / "o.out"
    orca_path.write_text(
        "* O   R   C   A *\n"
        "FINAL SINGLE POINT ENERGY -3.000000\n"
        "Total correction 0.050000 Eh\n"
        "Thermal Enthalpy correction 0.010000 Eh\n"
        "ORCA TERMINATED NORMALLY\n"
    )
    parsed_o = parse_orca(str(orca_path))
    assert parsed_o.source == str(orca_path.resolve())
    assert parsed_o.enthalpy() == pytest.approx(-2.94)
    assert parse_output(str(orca_path)).program == "orca"

    only_thermal = parse_orca(
        "* O   R   C   A *\n"
        "FINAL SINGLE POINT ENERGY -3.000000\n"
        "Thermal Enthalpy correction 0.010000 Eh\n"
        "ORCA TERMINATED NORMALLY\n"
    )
    assert only_thermal.enthalpy() == pytest.approx(-2.99)

    total_without_scf = parse_orca(
        "* O   R   C   A *\nTotal Enthalpy -4.000000 Eh\n"
        "ORCA TERMINATED NORMALLY\n"
    )
    assert total_without_scf.enthalpy() == -4.0


def test_salt_additional_error_and_string_branches():
    with pytest.raises(ValueError, match="至少需要"):
        Salt([])
    result = HofResult("x", {"H": 1, "N": 2}, 1.0, 2.0, -1.0)
    assert "H" in str(result) and "N2" in str(result)
    a = Ion("H", -1, enthalpy_hartree=-0.5)
    c = Ion("H", 1, enthalpy_hartree=-0.5)
    salt = Salt([a, c], atom_enthalpies_hartree={"H": -0.5})
    with pytest.raises(ValueError, match="volume"):
        salt.total_volume_cm3_mol()
