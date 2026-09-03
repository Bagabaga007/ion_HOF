"""气相生成焓: 原子化能法 (文档 2.2.1 节)。

核心公式 (以 kcal/mol 计):

    ΔHf,gas = H_calc(分子)·C + Σ_i n_i · [ΔHf,exp(原子_i) − H_calc(原子_i)·C]

其中 C = 627.51 (Hartree→kcal/mol), n_i 为分子中元素 i 的原子数,
H_calc 为计算总焓 (Hartree), ΔHf,exp 为单原子实验生成焓 (kcal/mol)。

等价于文档式 (2.2.1.12):
    H_f,prediction = H_obj + Σ_i (H_f,exp,SA,i − H_calc,SA,i)
"""

from __future__ import annotations

from .atom_data import AtomData
from .constants import (
    HARTREE_TO_KCAL_MOL,
    SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE,
)


def single_point_atom_enthalpy_hartree(scf_hartree: float) -> float:
    """单点法下单原子总焓 = SCF 自洽场能 + 固定热力学焓校正 0.00236048 Ha。

    文档: 单原子仅需单点能计算获得 E_total, 焓的其它项加和为 0.00236048 Hartree。
    (G4/ccCA 等直接给出焓的方法不应使用本函数, 直接读取焓即可。)
    """
    return scf_hartree + SINGLE_ATOM_ENTHALPY_CORRECTION_HARTREE


def gas_phase_hof(
    molecule_enthalpy_hartree: float,
    composition: dict[str, int],
    atom_enthalpies_hartree: dict[str, float],
    atom_data: AtomData | None = None,
) -> float:
    """计算气相生成焓 (kcal/mol)。

    参数
    ----
    molecule_enthalpy_hartree:
        目标 (中性化) 分子的计算总焓 H_obj (Hartree)。
    composition:
        分子元素组成 {元素: 原子数}。
    atom_enthalpies_hartree:
        各元素单原子在同一计算水平下的总焓 (Hartree)。
        单点法可用 single_point_atom_enthalpy_hartree 由 SCF 合成。
    atom_data:
        单原子实验生成焓数据源, 默认使用内置 ATcT/NIST 值。
    """
    atom_data = atom_data or AtomData.default()

    hof = molecule_enthalpy_hartree * HARTREE_TO_KCAL_MOL
    for element, n in composition.items():
        if element not in atom_enthalpies_hartree:
            raise KeyError(
                f"缺少元素 {element!r} 的单原子计算能量 "
                f"(atom_enthalpies_hartree)"
            )
        exp = atom_data.exp_hof(element)
        calc = atom_enthalpies_hartree[element] * HARTREE_TO_KCAL_MOL
        hof += n * (exp - calc)
    return hof
