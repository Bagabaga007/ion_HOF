"""ORCA 分阶段工作流的提交前科学门禁测试。"""

from pathlib import Path

import pytest

from bppa_hof.geometry import Molecule
from bppa_hof.inputgen import OrcaRecipe
from bppa_hof.workflow import run_orca_thermochemistry

pytestmark = pytest.mark.integration


def _runner(mode):
    calls = []

    def run(inputs, *, work_base, **kwargs):
        calls.append((inputs, kwargs))
        base = Path(inputs[0]).stem
        outputs = Path(work_base) / "outputs"
        outputs.mkdir(parents=True)
        output = outputs / f"{base}.out"
        if base.endswith("_optfreq"):
            converged = "" if mode == "not_converged" else "THE OPTIMIZATION HAS CONVERGED\n"
            if mode == "no_frequency" or mode == "single":
                frequency = ""
            elif mode == "imaginary":
                frequency = " 1: -100.000000 cm**-1\n"
            else:
                frequency = " 1: 1000.000000 cm**-1\n"
            output.write_text(
                "* O   R   C   A *\n"
                + converged
                + frequency
                + "FINAL SINGLE POINT ENERGY -10.000000\n"
                + "Total Enthalpy -9.900000 Eh\n"
                + "ORCA TERMINATED NORMALLY\n"
            )
            element = "He" if mode == "composition" else "H"
            atom_count = 1 if mode == "single" else 2
            xyz = outputs / f"{base}.xyz"
            coordinates = "\n".join(
                f"{element} 0.0 0.0 {0.7 * i}" for i in range(atom_count)
            )
            xyz.write_text(f"{atom_count}\noptimized\n{coordinates}\n")
        else:
            output.write_text(
                "* O   R   C   A *\nFINAL SINGLE POINT ENERGY -20.000000\n"
                "ORCA TERMINATED NORMALLY\n"
            )
        return {base: str(output)}

    run.calls = calls
    return run


def _h2(name="h2"):
    return Molecule(
        [("H", 0.0, 0.0, 0.0), ("H", 0.0, 0.0, 0.8)],
        name=name,
    )


def _run(tmp_path, molecule, runner):
    return run_orca_thermochemistry(
        molecule,
        work_base=str(tmp_path / "work"),
        machine_path="machine",
        resources_path="resources",
        runner=runner,
    )


def test_workflow_rejects_nonempty_root_and_unsafe_label(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "old").write_text("old")
    with pytest.raises(FileExistsError, match="非空"):
        _run(tmp_path, _h2(), _runner("good"))

    clean = tmp_path / "clean"
    with pytest.raises(ValueError, match="任务标签"):
        run_orca_thermochemistry(
            _h2("../unsafe"),
            work_base=str(clean),
            machine_path="machine",
            resources_path="resources",
            runner=_runner("good"),
        )


@pytest.mark.parametrize(
    "mode, message",
    [
        ("not_converged", "未确认收敛"),
        ("no_frequency", "未解析到振动频率"),
        ("imaginary", "显著虚频"),
        ("composition", "元素组成发生变化"),
    ],
)
def test_workflow_scientific_gates_stop_before_sp(tmp_path, mode, message):
    runner = _runner(mode)
    with pytest.raises(ValueError, match=message):
        _run(tmp_path, _h2(), runner)
    assert len(runner.calls) == 1


def test_single_atom_workflow_does_not_require_vibrational_modes(tmp_path):
    runner = _runner("single")
    result = _run(
        tmp_path,
        Molecule([("H", 0.0, 0.0, 0.0)], multiplicity=2, name="h_atom"),
        runner,
    )
    assert result.enthalpy_hartree == pytest.approx(-19.9)
    assert len(runner.calls) == 2


def test_workflow_accepts_resource_matched_recipes(tmp_path):
    runner = _runner("single")
    result = run_orca_thermochemistry(
        Molecule([("H", 0.0, 0.0, 0.0)], multiplicity=2, name="custom"),
        work_base=str(tmp_path / "custom"),
        machine_path="machine",
        resources_path="resources",
        opt_recipe=OrcaRecipe("B3LYP def2-SVP Opt Freq", nprocs=1),
        sp_recipe=OrcaRecipe("M062X def2-TZVP", nprocs=1),
        runner=runner,
    )
    opt_text = Path(runner.calls[0][0][0]).read_text()
    sp_text = Path(runner.calls[1][0][0]).read_text()
    assert "%pal" not in opt_text and "B3LYP def2-SVP" in opt_text
    assert "%pal" not in sp_text and "M062X def2-TZVP" in sp_text
    assert result.enthalpy_hartree == pytest.approx(-19.9)
