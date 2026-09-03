"""可恢复的分阶段量子化学工作流。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from .dispatch import run_jobs
from .geometry import Molecule
from .inputgen import ORCA_HIGH_SP, ORCA_OPT_FREQ, OrcaRecipe, build_orca
from .models import combine_single_point_and_thermal
from .parsers.base import parse_output

_SAFE_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")


@dataclass(frozen=True)
class OrcaThermochemistryResult:
    """ORCA 低水平热校正与高水平单点能的可追溯结果。"""

    label: str
    optimized_xyz: str
    thermal_output: str
    single_point_output: str
    enthalpy_hartree: float
    formula: dict[str, int]
    charge: int
    multiplicity: int


def _prepare_stage(root: Path, name: str) -> tuple[Path, Path]:
    stage = root / name
    inputs = stage / "inputs"
    inputs.mkdir(parents=True, exist_ok=False)
    return stage, inputs


def run_orca_thermochemistry(
    molecule: Molecule,
    *,
    work_base: str,
    machine_path: str,
    resources_path: str,
    nodes: int = 1,
    script_path: Optional[str] = None,
    opt_recipe: OrcaRecipe = ORCA_OPT_FREQ,
    sp_recipe: OrcaRecipe = ORCA_HIGH_SP,
    max_retries: int = 0,
    runner: Callable[..., dict[str, str]] = run_jobs,
) -> OrcaThermochemistryResult:
    """运行 ORCA opt+freq，再基于优化坐标运行高水平 SP 并合成总焓。

    每个阶段使用独立工作目录；已有非空目录会被拒绝，避免混入旧输出。
    只有第一阶段正常终止并回收优化后的 XYZ，第二阶段才会提交。
    """
    label = molecule.name
    if not _SAFE_LABEL.fullmatch(label):
        raise ValueError("任务标签只能包含字母、数字、点、下划线和连字符")
    root = Path(work_base)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"ORCA 工作流目录非空: {root}")
    root.mkdir(parents=True, exist_ok=True)
    opt_stage, opt_inputs = _prepare_stage(root, "01_optfreq")
    opt_base = f"{label}_optfreq"
    opt_path = opt_inputs / f"{opt_base}.inp"
    opt_path.write_text(build_orca(molecule, opt_recipe))

    opt_outputs = runner(
        [str(opt_path)],
        work_base=str(opt_stage / "dispatch"),
        machine_path=machine_path,
        resources_path=resources_path,
        program="orca",
        nodes=nodes,
        cleanup=True,
        script_path=script_path,
        required_artifact_suffixes=(".xyz",),
        max_retries=max_retries,
    )
    thermal_output = opt_outputs[opt_base]
    thermal = parse_output(thermal_output)
    if thermal.optimization_converged is not True:
        raise ValueError("ORCA 几何优化未确认收敛；不提交高水平单点")
    if len(molecule.atoms) > 1 and not thermal.frequencies_cm1:
        raise ValueError("ORCA 优化频率输出中未解析到振动频率")
    imaginary = thermal.imaginary_frequencies()
    if imaginary:
        values = ", ".join(f"{freq:.2f}" for freq in imaginary)
        raise ValueError(f"ORCA 优化结构存在显著虚频 (cm^-1): {values}")
    optimized_xyz = opt_stage / "dispatch" / "outputs" / f"{opt_base}.xyz"
    optimized = Molecule.from_xyz(
        str(optimized_xyz),
        charge=molecule.charge,
        multiplicity=molecule.multiplicity,
        name=f"{label}_sp",
    )
    if optimized.composition() != molecule.composition():
        raise ValueError("ORCA 优化后 XYZ 的元素组成发生变化")

    sp_stage, sp_inputs = _prepare_stage(root, "02_high_sp")
    sp_base = f"{label}_sp"
    sp_path = sp_inputs / f"{sp_base}.inp"
    sp_path.write_text(build_orca(optimized, sp_recipe))
    sp_outputs = runner(
        [str(sp_path)],
        work_base=str(sp_stage / "dispatch"),
        machine_path=machine_path,
        resources_path=resources_path,
        program="orca",
        nodes=nodes,
        cleanup=True,
        script_path=script_path,
        max_retries=max_retries,
    )
    single_point_output = sp_outputs[sp_base]
    single_point = parse_output(single_point_output)
    enthalpy = combine_single_point_and_thermal(single_point, thermal)

    result = OrcaThermochemistryResult(
        label=label,
        optimized_xyz=str(optimized_xyz.resolve()),
        thermal_output=str(Path(thermal_output).resolve()),
        single_point_output=str(Path(single_point_output).resolve()),
        enthalpy_hartree=enthalpy,
        formula=molecule.composition(),
        charge=molecule.charge,
        multiplicity=molecule.multiplicity,
    )
    (root / "thermochemistry.json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n"
    )
    return result
