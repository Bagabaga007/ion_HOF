"""端到端集成测试: 输入生成 → dpdispatcher 实际提交 (本地 Shell) → 解析 → 生成焓。

使用桩 (stub) QM 可执行文件产出文档验证例 (H5N7, G4) 的能量/体积, 从而在无真实
ORCA/Gaussian 的环境下验证整条工作流的配管 (含真实的 dpdispatcher run_submission)。
dpdispatcher 是开发/测试必需依赖；缺少时测试收集必须失败，不能静默跳过。
"""

import stat
import textwrap

import pytest

from bppa_hof import Ion, Salt
from bppa_hof.geometry import Molecule
from bppa_hof.inputgen import atom_inputs, ion_inputs
from bppa_hof.dispatch import run_jobs
from bppa_hof.parsers.base import parse_output

pytestmark = pytest.mark.system

STUB_G16 = textwrap.dedent(
    """\
    #!/bin/bash
    gjf="$1"
    base="$(basename "${gjf%.*}")"
    log="${base}.log"
    scf="-100.0"; enth=""; vol=""
    case "$base" in
      N5)       enth="-273.664407" ;;
      N2H5)     enth="-112.120023" ;;
      atom_N)   enth="-54.571306" ;;
      atom_H)   enth="-0.499060" ;;
      N5_vol)   vol="44.640"; scf="-273.5" ;;
      N2H5_vol) vol="28.479"; scf="-112.0" ;;
    esac
    {
      echo " SCF Done:  E(RB3LYP) =  ${scf}     A.U."
      if [ -n "$enth" ]; then echo " G4 Enthalpy=          ${enth} G4 Free Energy=  ${enth}"; fi
      if [ -n "$vol" ]; then echo "     Molar volume =   ${vol} cm**3/mol"; fi
      echo " Normal termination of Gaussian 16"
    } > "$log"
    """
)


def _write_exec(path, content):
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _write_configs(tmp_path, stub_dir):
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
              PATH: "{stub_dir}:$PATH"
            """
        )
    )
    return str(machine), str(resources)


def test_gaussian_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    _write_exec(stub_dir / "g16", STUB_G16)

    # 生成输入 (两个离子的 G4 能量+体积, 单原子 N/H)
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    n5 = Molecule([("N", 0.0, 0.0, float(i)) for i in range(5)], charge=-1, name="N5")
    n2h5 = Molecule(
        [("N", 0.0, 0.0, 0.4), ("N", 0.0, 0.0, -0.4)]
        + [("H", float(i), 0.0, 0.7) for i in range(5)],
        charge=1,
        name="N2H5",
    )
    to_write = []
    for mol in (n5, n2h5):
        to_write.extend(ion_inputs(mol, program="gaussian").values())
    to_write.extend(atom_inputs(["N", "H"], program="gaussian").values())
    for fname, text in to_write:
        (inputs_dir / fname).write_text(text)

    input_files = [str(p) for p in inputs_dir.glob("*.gjf")]
    assert len(input_files) == 6

    machine, resources = _write_configs(tmp_path, stub_dir)

    # 真实的 dpdispatcher 提交 (本地 Shell)
    outputs = run_jobs(
        input_files,
        work_base=str(tmp_path / "work"),
        machine_path=machine,
        resources_path=resources,
        program="gaussian",
        nodes=2,
    )
    assert set(outputs) == {"N5", "N5_vol", "N2H5", "N2H5_vol", "atom_N", "atom_H"}

    # 解析回收的真实输出并计算生成焓
    atom_e = {
        "N": parse_output(outputs["atom_N"]).enthalpy(),
        "H": parse_output(outputs["atom_H"]).enthalpy(),
    }
    anion = Ion(
        "N5", charge=-1,
        enthalpy_hartree=parse_output(outputs["N5"]).enthalpy(),
        volume_cm3_mol=parse_output(outputs["N5_vol"]).molar_volume_cm3_mol,
    )
    cation = Ion(
        "N2H5", charge=1,
        enthalpy_hartree=parse_output(outputs["N2H5"]).enthalpy(),
        volume_cm3_mol=parse_output(outputs["N2H5_vol"]).molar_volume_cm3_mol,
    )
    salt = Salt([anion, cation], method="G4", atom_enthalpies_hartree=atom_e)
    result = salt.compute()
    # 复现文档验证例 102.58 kcal/mol
    assert result.solid_hof == pytest.approx(102.58, abs=0.6)
