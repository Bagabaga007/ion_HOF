"""解析器公共工具与自动分发。"""

from __future__ import annotations

import os
import re
from typing import Optional

from ..models import QMResult

_FLOAT = r"[-+]?\d+\.\d+(?:[eEdD][-+]?\d+)?"


def to_float(text: str) -> float:
    """解析浮点数, 兼容 Fortran 的 D 指数记法 (如 -1.23D+02)。"""
    return float(text.replace("D", "E").replace("d", "e"))


def search_last(pattern: str, text: str, group: int = 1) -> Optional[float]:
    """返回正则最后一次匹配的浮点数; 无匹配返回 None。"""
    matches = re.findall(pattern, text)
    if not matches:
        return None
    last = matches[-1]
    if isinstance(last, tuple):
        last = last[group - 1]
    return to_float(last)


def read_text(path: str) -> str:
    with open(path, "r", errors="replace") as fh:
        return fh.read()


def detect_program(text: str) -> str:
    """根据输出内容判断来源程序: 'gaussian' | 'orca'。"""
    head = text[:5000]
    if "O   R   C   A" in head or "* O   R   C   A *" in text[:20000]:
        return "orca"
    if "Gaussian" in head or "Entering Gaussian System" in head:
        return "gaussian"
    # 回退: G4 Enthalpy 是 Gaussian 特征
    if "G4 Enthalpy" in text:
        return "gaussian"
    if "FINAL SINGLE POINT ENERGY" in text:
        return "orca"
    raise ValueError("无法识别输出程序 (非 Gaussian / ORCA)")


def parse_output(
    path: str,
    *,
    require_normal_termination: bool = True,
) -> QMResult:
    """自动识别并解析输出文件，默认拒绝未正常终止的计算。"""
    from .gaussian import parse_gaussian
    from .orca import parse_orca

    text = read_text(path)
    program = detect_program(text)
    result = (
        parse_gaussian(text, require_normal_termination=require_normal_termination)
        if program == "gaussian"
        else parse_orca(text, require_normal_termination=require_normal_termination)
    )
    result.source = os.path.abspath(path)
    return result
