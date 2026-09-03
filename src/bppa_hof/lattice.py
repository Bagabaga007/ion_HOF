"""晶格焓: VBT (基于体积理论) 方法 (文档 2.2.2 节)。

晶格焓:
    ΔH_L = U_POT + [Σ_i count_i·(n_i/2 − 2)]·RT

晶格能 U_POT (kJ/mol), V_m 为式单位体积 (nm^3):
    U_POT < 5000:  U_POT = 2·I·(α/V_m^(1/3) + β)      α=117.3, β=51.9
    U_POT > 5000:  U_POT = A·I·(2·I/V_m^(1/3))         A=121.4

其中 I 为晶格离子强度系数 I = 0.5·Σ_i count_i·z_i^2 (1:1 盐为 1)。
n_i 由离子形状决定: 单原子 3, 线性 5, 非线性 6。
"""

from __future__ import annotations

from typing import Iterable

from .constants import (
    CM3_MOL_TO_NM3,
    ION_SHAPE_N,
    KJ_TO_KCAL,
    RT_KCAL_MOL,
    VBT_A,
    VBT_ALPHA,
    VBT_BETA,
    VBT_UPOT_THRESHOLD_KJ,
)
from .models import Ion


def ionic_strength(ions: Iterable[Ion]) -> float:
    """晶格离子强度系数 I = 0.5·Σ count_i·z_i^2。"""
    return 0.5 * sum(ion.count * ion.charge**2 for ion in ions)


def lattice_energy_kj(
    volume_nm3: float,
    ionic_strength_i: float,
    *,
    allow_extrapolation: bool = False,
) -> float:
    """VBT 晶格能 U_POT (kJ/mol)。

    内置 α/β 参数来自项目方法文档中的 I=1、1:1 盐体系。其他离子强度的
    系数与阴阳离子比例有关，默认拒绝直接外推；仅可显式用于诊断性比较。
    """
    if volume_nm3 <= 0:
        raise ValueError("体积必须为正")
    if ionic_strength_i != 1.0 and not allow_extrapolation:
        raise ValueError(
            "内置 VBT 参数仅适用于 I=1 的 1:1 盐；"
            "其他计量比需专用参数，或显式 allow_extrapolation=True 用于诊断"
        )
    v_cbrt = volume_nm3 ** (1.0 / 3.0)

    upot = 2.0 * ionic_strength_i * (VBT_ALPHA / v_cbrt + VBT_BETA)
    if upot > VBT_UPOT_THRESHOLD_KJ:
        # 高晶格能分支
        upot = VBT_A * ionic_strength_i * (2.0 * ionic_strength_i / v_cbrt)
    return upot


def _rt_correction_kcal(ions: Iterable[Ion]) -> float:
    """晶格焓 RT 校正项 [Σ count_i·(n_i/2 − 2)]·RT (kcal/mol)。"""
    factor = sum(
        ion.count * (ION_SHAPE_N[ion.shape] / 2.0 - 2.0) for ion in ions
    )
    return factor * RT_KCAL_MOL


def lattice_enthalpy_kcal(
    volume_cm3_mol: float,
    ions: Iterable[Ion],
    *,
    allow_extrapolation: bool = False,
) -> float:
    """晶格焓 ΔH_L (kcal/mol)。

    参数
    ----
    volume_cm3_mol: 整个式单位的分子体积 (cm^3/mol), 即各离子体积之和。
    ions:           构成盐的离子列表 (提供电荷、形状、计数)。
    """
    ions = list(ions)
    volume_nm3 = volume_cm3_mol * CM3_MOL_TO_NM3
    i_strength = ionic_strength(ions)

    upot_kj = lattice_energy_kj(
        volume_nm3,
        i_strength,
        allow_extrapolation=allow_extrapolation,
    )
    upot_kcal = upot_kj * KJ_TO_KCAL
    return upot_kcal + _rt_correction_kcal(ions)
