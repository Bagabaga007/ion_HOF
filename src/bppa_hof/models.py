"""数据模型: 化学式解析、离子 (Ion)、盐 (Salt) 与 QM 结果 (QMResult)。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")

VALID_SHAPES = ("monatomic", "linear", "nonlinear")


def parse_formula(formula: str) -> dict[str, int]:
    """将化学式字符串解析为 {元素: 计数}。

    支持形如 "N2H5", "C2H5N4O2", "Li" 的分子式 (不支持括号嵌套)。
    """
    formula = formula.strip()
    if not formula:
        raise ValueError("化学式不能为空")

    counts: Counter[str] = Counter()
    pos = 0
    for match in _FORMULA_TOKEN.finditer(formula):
        if match.start() != pos:
            raise ValueError(f"无法解析化学式 {formula!r} 于位置 {pos}")
        element, num = match.group(1), match.group(2)
        counts[element] += int(num) if num else 1
        pos = match.end()
    if pos != len(formula):
        raise ValueError(f"无法解析化学式 {formula!r} 于位置 {pos}")
    return dict(counts)


@dataclass
class QMResult:
    """从量子化学输出文件解析出的能量/体积数据 (单位: Hartree, cm^3/mol)。"""

    program: Optional[str] = None
    terminated_normally: Optional[bool] = None
    optimization_converged: Optional[bool] = None
    frequencies_cm1: tuple[float, ...] = ()
    scf_hartree: Optional[float] = None
    thermal_enthalpy_correction_hartree: Optional[float] = None
    total_enthalpy_hartree: Optional[float] = None
    molar_volume_cm3_mol: Optional[float] = None
    source: Optional[str] = None

    def imaginary_frequencies(self, *, threshold_cm1: float = -10.0) -> tuple[float, ...]:
        """返回低于阈值的显著虚频；小幅数值噪声默认不计。"""
        if threshold_cm1 > 0:
            raise ValueError("虚频阈值必须 <= 0 cm^-1")
        return tuple(freq for freq in self.frequencies_cm1 if freq < threshold_cm1)

    def enthalpy(self, *, require_thermal_correction: bool = False) -> float:
        """返回总焓 (Hartree)。

        优先使用已直接读取的 total_enthalpy; 否则由 SCF + 热力学焓校正合成。
        """
        if self.total_enthalpy_hartree is not None:
            return self.total_enthalpy_hartree
        if self.scf_hartree is not None:
            if (
                require_thermal_correction
                and self.thermal_enthalpy_correction_hartree is None
            ):
                raise ValueError("QMResult 缺少热力学焓校正")
            corr = self.thermal_enthalpy_correction_hartree or 0.0
            return self.scf_hartree + corr
        raise ValueError(
            "QMResult 缺少焓数据: 需要 total_enthalpy_hartree 或 scf_hartree"
        )


def combine_single_point_and_thermal(
    single_point: QMResult,
    thermal: QMResult,
) -> float:
    """用高水平单点能与低水平频率热校正构造总焓。

    H(high//low) = E_high + [H_low - E_low]。两个结果必须来自正常终止的
    计算；频率结果必须包含可解析的热力学焓校正。
    """
    for label, result in (("single_point", single_point), ("thermal", thermal)):
        if result.terminated_normally is not True:
            raise ValueError(f"{label} 计算未确认正常终止")
    if single_point.scf_hartree is None:
        raise ValueError("single_point 缺少 SCF/单点能")
    if thermal.thermal_enthalpy_correction_hartree is None:
        raise ValueError("thermal 结果缺少热力学焓校正")
    return single_point.scf_hartree + thermal.thermal_enthalpy_correction_hartree


@dataclass
class Ion:
    """构成盐的一个离子基元。

    formula: 化学式, 如 "N5", "N2H5"
    charge:  带符号电荷, 如 -1, +1
    enthalpy_hartree: 该离子的总焓 (Hartree)。G4/直接优化可直接给出;
                      单点法可由 scf + thermal_corr 合成 (见 from_qm)。
    volume_cm3_mol:   分子体积 (cm^3/mol), 用于 VBT 晶格能。
    shape:            monatomic | linear | nonlinear, 决定晶格焓 RT 项 n 值。
    count:            该离子在式单位中的个数 (默认 1)。
    """

    formula: str
    charge: int
    enthalpy_hartree: Optional[float] = None
    volume_cm3_mol: Optional[float] = None
    shape: str = "nonlinear"
    count: int = 1
    composition: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        if self.shape not in VALID_SHAPES:
            raise ValueError(
                f"未知 shape {self.shape!r}; 可选: {VALID_SHAPES}"
            )
        if self.count < 1:
            raise ValueError("count 必须 >= 1")
        self.composition = parse_formula(self.formula)

    @classmethod
    def from_qm(
        cls,
        formula: str,
        charge: int,
        qm: QMResult,
        *,
        shape: str = "nonlinear",
        count: int = 1,
    ) -> "Ion":
        """由 QMResult 构造离子 (焓与体积从解析结果读取)。"""
        return cls(
            formula=formula,
            charge=charge,
            enthalpy_hartree=qm.enthalpy(),
            volume_cm3_mol=qm.molar_volume_cm3_mol,
            shape=shape,
            count=count,
        )
