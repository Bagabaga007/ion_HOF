"""ORCA 输出解析 (SCF、热力学焓校正、总焓)。

文档 (指标2 步骤8) 提取的关键量:
  - "FINAL SINGLE POINT ENERGY": 含核间排斥的电子总能 E_total
  - "Total correction":          振动+平动+转动能之和
  - "Thermal Enthalpy correction": k_B·T
ORCA 若已输出 "Total Enthalpy" 则直接采用; 否则由 SCF + 校正合成。
"""

from __future__ import annotations

import os
import re

from ..models import QMResult
from .base import _FLOAT, search_last

_FINAL_SP = re.compile(r"FINAL SINGLE POINT ENERGY\s+(" + _FLOAT + r")")
_TOTAL_ENTHALPY = re.compile(r"Total Enthalpy\s*\.*\s*(" + _FLOAT + r")")
_THERMAL_ENTHALPY_CORR = re.compile(
    r"Thermal Enthalpy correction\s*\.*\s*(" + _FLOAT + r")"
)
_TOTAL_CORR = re.compile(r"Total correction\s*\.*\s*(" + _FLOAT + r")")
_NORMAL_TERMINATION = re.compile(r"ORCA TERMINATED NORMALLY", re.I)
_OPTIMIZATION_CONVERGED = re.compile(r"THE OPTIMIZATION HAS CONVERGED", re.I)
_FREQUENCY = re.compile(
    r"^\s*\d+:\s+(" + _FLOAT + r")\s+cm\*\*-1", re.M
)


def parse_orca(
    source: str,
    *,
    require_normal_termination: bool = True,
) -> QMResult:
    """解析 ORCA 输出；默认要求包含正常终止标志。"""
    if os.path.exists(source):
        with open(source, "r", errors="replace") as fh:
            text = fh.read()
        src_label = os.path.abspath(source)
    else:
        text = source
        src_label = None

    terminated_normally = _NORMAL_TERMINATION.search(text) is not None
    if require_normal_termination and not terminated_normally:
        raise ValueError("ORCA 输出未正常终止或输出不完整")

    result = QMResult(
        program="orca",
        terminated_normally=terminated_normally,
        optimization_converged=_OPTIMIZATION_CONVERGED.search(text) is not None,
        frequencies_cm1=tuple(
            float(value.replace("D", "E").replace("d", "e"))
            for value in _FREQUENCY.findall(text)
        ),
        source=src_label,
    )
    result.scf_hartree = search_last(_FINAL_SP.pattern, text)
    total_enthalpy = search_last(_TOTAL_ENTHALPY.pattern, text)

    if total_enthalpy is not None:
        result.total_enthalpy_hartree = total_enthalpy
        # 记录焓校正 = 总焓 − 电子总能, 便于替换高水平单点能后重算
        if result.scf_hartree is not None:
            result.thermal_enthalpy_correction_hartree = (
                total_enthalpy - result.scf_hartree
            )
    else:
        # 由 SCF + (Total correction + Thermal Enthalpy correction) 合成
        total_corr = search_last(_TOTAL_CORR.pattern, text)
        therm_h = search_last(_THERMAL_ENTHALPY_CORR.pattern, text)
        if total_corr is not None or therm_h is not None:
            result.thermal_enthalpy_correction_hartree = (total_corr or 0.0) + (
                therm_h or 0.0
            )
    return result
