"""Gaussian 输出解析 (含 G4 组合方法与分子体积计算)。"""

from __future__ import annotations

import os
import re

from ..models import QMResult
from .base import _FLOAT, search_last, to_float

# G4 组合方法直接给出焓: "G4 Enthalpy=           -273.664407 G4 Free Energy=..."
_G4_ENTHALPY = re.compile(r"G4 Enthalpy=\s*(" + _FLOAT + r")")
# 通用组合方法焓 (CBS-QB3 / ccCA 等亦以 "... Enthalpy=" 形式出现)
_ANY_ENTHALPY = re.compile(r"\b\w[\w()-]*\s+Enthalpy=\s*(" + _FLOAT + r")")
# 自洽场能: "SCF Done:  E(RB3LYP) =  -xxx  A.U. ..."
_SCF_DONE = re.compile(r"SCF Done:\s*E\([^)]*\)\s*=\s*(" + _FLOAT + r")")
# 热力学焓校正: "Thermal correction to Enthalpy=       0.005236"
_THERMAL_ENTHALPY = re.compile(
    r"Thermal correction to Enthalpy=\s*(" + _FLOAT + r")"
)
# 分子体积: "Molar volume =   44.640 cm**3/mol" (文档: 提取 "Molar volume")
_MOLAR_VOLUME = re.compile(
    r"Molar volume\s*=?\s*(" + _FLOAT + r")\s*(?:cm\*\*3|cm3|cm\^3)?", re.I
)
_NORMAL_TERMINATION = re.compile(r"Normal termination of Gaussian", re.I)
_OPTIMIZATION_COMPLETED = re.compile(r"Optimization completed", re.I)
_FREQUENCY_LINE = re.compile(r"^\s*Frequencies\s+--\s+(.+)$", re.M)


def parse_gaussian(
    source: str,
    *,
    require_normal_termination: bool = True,
) -> QMResult:
    """解析 Gaussian 输出；默认要求包含正常终止标志。"""
    if os.path.exists(source):
        with open(source, "r", errors="replace") as fh:
            text = fh.read()
        src_label = os.path.abspath(source)
    else:
        text = source
        src_label = None

    terminated_normally = _NORMAL_TERMINATION.search(text) is not None
    if require_normal_termination and not terminated_normally:
        raise ValueError("Gaussian 输出未正常终止或输出不完整")

    result = QMResult(
        program="gaussian",
        terminated_normally=terminated_normally,
        optimization_converged=_OPTIMIZATION_COMPLETED.search(text) is not None,
        source=src_label,
    )
    result.frequencies_cm1 = tuple(
        float(value)
        for line in _FREQUENCY_LINE.findall(text)
        for value in line.split()
    )

    # 焓: 优先 G4 Enthalpy, 否则回退到通用 "<方法> Enthalpy="
    g4 = _G4_ENTHALPY.findall(text)
    if g4:
        result.total_enthalpy_hartree = to_float(g4[-1])
    else:
        generic = _ANY_ENTHALPY.findall(text)
        if generic:
            result.total_enthalpy_hartree = to_float(generic[-1])

    result.scf_hartree = search_last(_SCF_DONE.pattern, text)
    result.thermal_enthalpy_correction_hartree = search_last(
        _THERMAL_ENTHALPY.pattern, text
    )
    result.molar_volume_cm3_mol = search_last(_MOLAR_VOLUME.pattern, text)
    return result
