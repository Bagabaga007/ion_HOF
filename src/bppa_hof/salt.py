"""盐 (Salt): 组合阴阳离子, 计算气相/晶格/固态生成焓。

固态生成焓 (文档式 11):
    ΔHf(盐, cr) = ΔHf,gas(盐) − ΔH_L
其中 ΔHf,gas 由原子化能法对中性化后的整盐求得, ΔH_L 由 VBT 求得。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

from .atom_data import AtomData
from .gas_phase import gas_phase_hof
from .lattice import lattice_enthalpy_kcal
from .models import Ion


@dataclass
class HofResult:
    """生成焓计算结果 (kcal/mol)。"""

    method: str
    composition: dict[str, int]
    gas_phase_hof: float
    lattice_enthalpy: float
    solid_hof: float

    def __str__(self) -> str:
        comp = "".join(
            f"{el}{n if n > 1 else ''}"
            for el, n in sorted(self.composition.items())
        )
        return (
            f"[{self.method}] {comp}: "
            f"gas={self.gas_phase_hof:.2f}, "
            f"lattice={self.lattice_enthalpy:.2f}, "
            f"solid={self.solid_hof:.2f} kcal/mol"
        )


class Salt:
    """由若干离子构成的离子盐。

    参数
    ----
    ions:   离子列表 (至少一个阳离子与一个阴离子); 电荷须配平为中性。
    method: 计算方法标签, 如 "G4" / "M06-2X" (仅用于标注与选取原子能量)。
    atom_enthalpies_hartree:
            该方法下各元素单原子总焓 (Hartree), 供气相原子化能法使用。
    atom_data: 单原子实验生成焓数据源。
    label:  可选的盐编码/名称。
    """

    def __init__(
        self,
        ions: Iterable[Ion],
        *,
        method: str = "unspecified",
        atom_enthalpies_hartree: Optional[dict[str, float]] = None,
        atom_data: Optional[AtomData] = None,
        label: Optional[str] = None,
    ) -> None:
        self.ions = list(ions)
        if not self.ions:
            raise ValueError("盐至少需要一个离子")
        self.method = method
        self.atom_enthalpies_hartree = atom_enthalpies_hartree or {}
        self.atom_data = atom_data or AtomData.default()
        self.label = label
        self._check_neutral()

    def _check_neutral(self) -> None:
        net = sum(ion.charge * ion.count for ion in self.ions)
        if net != 0:
            raise ValueError(
                f"盐电荷未配平: 净电荷 = {net} (label={self.label!r})"
            )

    # -- 组成与聚合量 ------------------------------------------------------
    def composition(self) -> dict[str, int]:
        """中性化整盐的元素组成 {元素: 原子数}。"""
        total: Counter[str] = Counter()
        for ion in self.ions:
            for element, n in ion.composition.items():
                total[element] += n * ion.count
        return dict(total)

    def total_enthalpy_hartree(self) -> float:
        """整盐计算总焓 (Hartree) = Σ 各离子焓 × 计数。"""
        total = 0.0
        for ion in self.ions:
            if ion.enthalpy_hartree is None:
                raise ValueError(
                    f"离子 {ion.formula!r} 缺少 enthalpy_hartree"
                )
            total += ion.enthalpy_hartree * ion.count
        return total

    def total_volume_cm3_mol(self) -> float:
        """整盐分子体积 (cm^3/mol) = Σ 各离子体积 × 计数。"""
        total = 0.0
        for ion in self.ions:
            if ion.volume_cm3_mol is None:
                raise ValueError(
                    f"离子 {ion.formula!r} 缺少 volume_cm3_mol"
                )
            total += ion.volume_cm3_mol * ion.count
        return total

    # -- 生成焓 ------------------------------------------------------------
    def gas_phase_hof(self) -> float:
        """气相生成焓 (kcal/mol), 原子化能法。"""
        return gas_phase_hof(
            self.total_enthalpy_hartree(),
            self.composition(),
            self.atom_enthalpies_hartree,
            self.atom_data,
        )

    def lattice_enthalpy(self) -> float:
        """晶格焓 (kcal/mol), VBT 方法。"""
        return lattice_enthalpy_kcal(self.total_volume_cm3_mol(), self.ions)

    def solid_hof(self) -> float:
        """固态 (晶体) 生成焓 (kcal/mol) = 气相生成焓 − 晶格焓。"""
        return self.gas_phase_hof() - self.lattice_enthalpy()

    def compute(self) -> HofResult:
        """一次性计算并返回完整结果。"""
        gas = self.gas_phase_hof()
        lat = self.lattice_enthalpy()
        return HofResult(
            method=self.method,
            composition=self.composition(),
            gas_phase_hof=gas,
            lattice_enthalpy=lat,
            solid_hof=gas - lat,
        )
