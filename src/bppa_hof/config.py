"""TOML 配置加载: 定义方法、单原子能量与一批待计算的盐。

示例见 examples/h5n7/config.toml。配置结构:

    [method]
    name = "G4"
    [method.atom_enthalpies_hartree]   # 该方法下单原子总焓 (Hartree)
    H = -0.49906
    N = -54.571306

    [atom_exp_hof_kcal_mol]            # 可选: 覆盖单原子实验生成焓
    # N = 112.970

    [[salt]]
    label = "1a+1c"
    reference = 103.70                 # 可选: 实验标准值 (kcal/mol)
      [[salt.ion]]
      formula = "N2H5"
      charge = 1
      enthalpy_hartree = -273.664407   # 或 energy_file = "test1.log"
      volume_cm3_mol = 44.640          # 或 volume_file = "test1v.log"
      shape = "nonlinear"
      count = 1
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    import tomli as _toml  # type: ignore

from .atom_data import AtomData
from .gas_phase import single_point_atom_enthalpy_hartree
from .models import Ion, combine_single_point_and_thermal
from .parsers.base import parse_output
from .salt import Salt


@dataclass
class Config:
    method: str
    atom_enthalpies_hartree: dict[str, float]
    atom_data: AtomData
    salts: list[Salt]
    references: dict[str, float] = field(default_factory=dict)


def _resolve(path: Optional[str], base_dir: str) -> Optional[str]:
    if path is None:
        return None
    return path if os.path.isabs(path) else os.path.join(base_dir, path)


def _enthalpy_from_files(
    energy_file: str,
    base_dir: str,
    *,
    thermal_file: Optional[str] = None,
    apply_single_atom_correction: bool = False,
) -> float:
    """从正常终止的 QM 输出构造焓，支持高水平 SP + 低水平热校正。"""
    energy = parse_output(_resolve(energy_file, base_dir))
    if thermal_file is not None:
        if apply_single_atom_correction:
            raise ValueError("thermal_file 与 apply_single_atom_correction 不能同时使用")
        thermal = parse_output(_resolve(thermal_file, base_dir))
        return combine_single_point_and_thermal(energy, thermal)
    if apply_single_atom_correction:
        if energy.scf_hartree is None:
            raise ValueError("单原子校正需要可解析的 SCF/单点能")
        return single_point_atom_enthalpy_hartree(energy.scf_hartree)
    return energy.enthalpy()


def _ion_from_config(data: dict[str, Any], base_dir: str) -> Ion:
    enthalpy = data.get("enthalpy_hartree")
    volume = data.get("volume_cm3_mol")

    energy_file = _resolve(data.get("energy_file"), base_dir)
    volume_file = _resolve(data.get("volume_file"), base_dir)
    thermal_file = _resolve(data.get("thermal_file"), base_dir)

    if enthalpy is None and energy_file:
        enthalpy = _enthalpy_from_files(
            energy_file,
            base_dir="",
            thermal_file=thermal_file,
        )
    elif thermal_file:
        raise ValueError("thermal_file 需要 energy_file，且不能与 enthalpy_hartree 同时使用")
    if volume is None and volume_file:
        volume = parse_output(volume_file).molar_volume_cm3_mol

    return Ion(
        formula=data["formula"],
        charge=int(data["charge"]),
        enthalpy_hartree=enthalpy,
        volume_cm3_mol=volume,
        shape=data.get("shape", "nonlinear"),
        count=int(data.get("count", 1)),
    )


def load_config(path: str) -> Config:
    """从 TOML 文件加载配置。"""
    base_dir = os.path.dirname(os.path.abspath(path))
    with open(path, "rb") as fh:
        raw = _toml.load(fh)

    method_cfg = raw.get("method", {})
    method_name = method_cfg.get("name", "unspecified")
    atom_enthalpies = {
        k: float(v)
        for k, v in method_cfg.get("atom_enthalpies_hartree", {}).items()
    }
    # 支持从文件解析单原子能量: [method.atom_energy_files]
    for element, spec in method_cfg.get("atom_energy_files", {}).items():
        if isinstance(spec, str):
            atom_enthalpies[element] = _enthalpy_from_files(spec, base_dir)
        elif isinstance(spec, dict):
            energy_file = spec.get("energy_file") or spec.get("path")
            if not energy_file:
                raise ValueError(f"atom_energy_files.{element} 缺少 energy_file")
            atom_enthalpies[element] = _enthalpy_from_files(
                energy_file,
                base_dir,
                thermal_file=spec.get("thermal_file"),
                apply_single_atom_correction=bool(
                    spec.get("apply_single_atom_correction", False)
                ),
            )
        else:
            raise TypeError(f"atom_energy_files.{element} 必须是路径或表")

    atom_data = AtomData.default()
    exp_override = raw.get("atom_exp_hof_kcal_mol")
    if exp_override:
        atom_data = atom_data.with_overrides(
            exp_hof_kcal_mol={k: float(v) for k, v in exp_override.items()}
        )

    salts: list[Salt] = []
    references: dict[str, float] = {}
    for salt_cfg in raw.get("salt", []):
        ions = [_ion_from_config(i, base_dir) for i in salt_cfg.get("ion", [])]
        label = salt_cfg.get("label")
        salt = Salt(
            ions,
            method=method_name,
            atom_enthalpies_hartree=atom_enthalpies,
            atom_data=atom_data,
            label=label,
        )
        salts.append(salt)
        if "reference" in salt_cfg and label is not None:
            references[label] = float(salt_cfg["reference"])

    return Config(
        method=method_name,
        atom_enthalpies_hartree=atom_enthalpies,
        atom_data=atom_data,
        salts=salts,
        references=references,
    )
