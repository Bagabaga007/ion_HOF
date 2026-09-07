"""所有 CLI 子命令的系统级接口测试。"""

from pathlib import Path
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import bppa_hof.dispatch as dispatch
import bppa_hof.workflow as workflow
from bppa_hof.cli import main

pytestmark = pytest.mark.system


def _xyz(path: Path, name="h.xyz") -> str:
    target = path / name
    target.write_text("1\nhydrogen\nH 0 0 0\n")
    return str(target)


def _neutral_config(path: Path, *, reference=False, label=False) -> str:
    target = path / "neutral.toml"
    label_line = 'label = "pair"\n' if label else ""
    reference_line = "reference = 1.0\n" if reference else ""
    target.write_text(
        f"""
[method]
name = "test"
[method.atom_enthalpies_hartree]
H = -0.5
[[salt]]
{label_line}{reference_line}  [[salt.ion]]
  formula = "H"
  charge = -1
  enthalpy_hartree = -0.5
  volume_cm3_mol = 10.0
  [[salt.ion]]
  formula = "H"
  charge = 1
  enthalpy_hartree = -0.5
  volume_cm3_mol = 10.0
"""
    )
    return str(target)


def test_batch_unlabeled_and_report_without_references(tmp_path, capsys):
    config = _neutral_config(tmp_path)
    assert main(["batch", config]) == 0
    assert "H2" in capsys.readouterr().out
    assert main(["report", config]) == 1
    assert "无 reference" in capsys.readouterr().err


def test_parse_cli_with_and_without_enthalpy(tmp_path, capsys):
    energy = tmp_path / "energy.log"
    energy.write_text(
        "Entering Gaussian System\nSCF Done: E(RHF) = -1.000000 A.U.\n"
        "Normal termination of Gaussian 16\n"
    )
    assert main(["parse", str(energy)]) == 0
    assert "-1.0" in capsys.readouterr().out

    volume = tmp_path / "volume.log"
    volume.write_text(
        "Entering Gaussian System\nMolar volume = 12.000 cm**3/mol\n"
        "Normal termination of Gaussian 16\n"
    )
    assert main(["parse", str(volume)]) == 0
    assert "不足以计算" in capsys.readouterr().out


def test_gen_input_cli_all_modes(tmp_path, capsys):
    xyz = _xyz(tmp_path)
    optimized = _xyz(tmp_path, "optimized.xyz")
    outdir = tmp_path / "orca_inputs"
    assert main(
        [
            "gen-input",
            xyz,
            "--program",
            "orca",
            "--optimized-xyz",
            optimized,
            "--outdir",
            str(outdir),
            "--atoms",
            "H",
            "--atom-program",
            "gaussian",
        ]
    ) == 0
    assert (outdir / "h_optfreq.inp").exists()
    assert (outdir / "h_sp.inp").exists()
    assert (outdir / "atom_H.gjf").exists()
    assert "已生成" in capsys.readouterr().out

    no_optimized = tmp_path / "no_optimized"
    assert main(
        [
            "gen-input",
            xyz,
            "--program",
            "orca",
            "--outdir",
            str(no_optimized),
            "--no-volume",
        ]
    ) == 0
    assert (no_optimized / "h_optfreq.inp").exists()
    assert not (no_optimized / "h_sp.inp").exists()

    atoms_only = tmp_path / "atoms_only"
    assert main(
        [
            "gen-input",
            "--program",
            "orca",
            "--outdir",
            str(atoms_only),
            "--atoms",
            "H",
        ]
    ) == 0
    assert (atoms_only / "atom_H.inp").exists()

    empty = tmp_path / "empty"
    assert main(["gen-input", "--outdir", str(empty)]) == 1
    assert "未生成任何输入" in capsys.readouterr().err


def test_submit_cli_forwards_options(tmp_path, monkeypatch, capsys):
    input_file = tmp_path / "x.gjf"
    input_file.write_text("input")
    seen = {}

    def fake_run_jobs(inputs, **kwargs):
        seen.update(kwargs)
        return {"x": str(tmp_path / "x.log")}

    monkeypatch.setattr(dispatch, "run_jobs", fake_run_jobs)
    assert main(
        [
            "submit",
            str(input_file),
            "--program",
            "gaussian",
            "--machine",
            "machine.yaml",
            "--resources",
            "resources.yaml",
            "--nodes",
            "2",
            "--keep-temp",
            "--script",
            "custom.sh",
        ]
    ) == 0
    assert seen["cleanup"] is False
    assert seen["nodes"] == 2 and seen["script_path"] == "custom.sh"
    assert seen["max_retries"] == 0
    assert "回收 1" in capsys.readouterr().out


def test_orca_thermo_cli(tmp_path, monkeypatch, capsys):
    xyz = _xyz(tmp_path)
    seen = {}

    def fake_workflow(molecule, **kwargs):
        seen["molecule"] = molecule
        seen.update(kwargs)
        return SimpleNamespace(label=molecule.name, enthalpy_hartree=-1.234)

    monkeypatch.setattr(workflow, "run_orca_thermochemistry", fake_workflow)
    work = tmp_path / "workflow"
    assert main(
        [
            "orca-thermo",
            xyz,
            "--charge",
            "-1",
            "--mult",
            "2",
            "--label",
            "h_atom",
            "--machine",
            "machine.yaml",
            "--resources",
            "resources.yaml",
            "--work-base",
            str(work),
            "--nodes",
            "3",
            "--script",
            "orca.sh",
        ]
    ) == 0
    assert seen["molecule"].charge == -1 and seen["molecule"].multiplicity == 2
    assert seen["nodes"] == 3 and seen["script_path"] == "orca.sh"
    assert seen["max_retries"] == 0
    assert "-1.234000000000" in capsys.readouterr().out


def test_packaged_h5n7_example_script_runs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, str(root / "examples/h5n7/run_demo.py")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = __import__("json").loads(completed.stdout)
    assert payload["salts"][0]["label"] == "1a+1c"
    assert payload["salts"][0]["solid_hof_kcal_mol"] == pytest.approx(102.596942, abs=1e-6)
