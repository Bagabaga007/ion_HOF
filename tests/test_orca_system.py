"""ORCA 分阶段系统测试：本地 dpdispatcher + 可执行桩。"""

import json
import stat
import textwrap

import pytest

from bppa_hof.geometry import Molecule
from bppa_hof.workflow import run_orca_thermochemistry

pytestmark = pytest.mark.system

STUB_ORCA = textwrap.dedent(
    """\
    #!/bin/bash
    inp="$1"
    base="$(basename "${inp%.*}")"
    if [[ "$base" == *_optfreq ]]; then
      cat > "${base}.xyz" <<'XYZ'
    2
    optimized H2
    H 0.0 0.0 0.0
    H 0.0 0.0 0.74
    XYZ
      cat <<'OUT'
                           * O   R   C   A *
    THE OPTIMIZATION HAS CONVERGED
       1:       4400.000000 cm**-1
    FINAL SINGLE POINT ENERGY      -100.000000000
    Total Enthalpy                  -99.900000000 Eh
    ORCA TERMINATED NORMALLY
    OUT
    else
      cat <<'OUT'
                           * O   R   C   A *
    FINAL SINGLE POINT ENERGY      -110.000000000
    ORCA TERMINATED NORMALLY
    OUT
    fi
    """
)


def _write_exec(path, content):
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write_configs(tmp_path, stub):
    machine = tmp_path / "machine.yaml"
    machine.write_text(
        textwrap.dedent(
            f"""\
            batch_type: "Shell"
            context_type: "LocalContext"
            local_root: "./"
            remote_root: "{tmp_path / 'remote'}"
            remote_profile:
              symlink: false
            """
        )
    )
    resources = tmp_path / "resources.yaml"
    resources.write_text(
        textwrap.dedent(
            f"""\
            number_node: 1
            cpu_per_node: 1
            gpu_per_node: 0
            group_size: 1
            queue_name: "local"
            envs:
              ORCA_EXE: "{stub}"
              ORCA_ENV: ""
            """
        )
    )
    return str(machine), str(resources)


def test_orca_staged_thermochemistry_system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub = tmp_path / "orca"
    _write_exec(stub, STUB_ORCA)
    machine, resources = _write_configs(tmp_path, stub)
    molecule = Molecule(
        [("H", 0.0, 0.0, 0.0), ("H", 0.0, 0.0, 0.8)],
        name="h2",
    )

    result = run_orca_thermochemistry(
        molecule,
        work_base=str(tmp_path / "workflow"),
        machine_path=machine,
        resources_path=resources,
    )

    assert result.enthalpy_hartree == pytest.approx(-109.9)
    assert result.formula == {"H": 2}
    report = json.loads((tmp_path / "workflow" / "thermochemistry.json").read_text())
    assert report["label"] == "h2"
    assert report["enthalpy_hartree"] == pytest.approx(-109.9)
