"""单原子参考数据: 气相实验生成焓与自旋多重度。

气相生成焓实验值 (kcal/mol):
  - 文档 3.2 / 指标2 采用 ATcT 值: C, H, N, O = 171.290, 52.103, 112.970, 59.555
  - 文档 2.2.1 采用 NIST 值并补充 Li = 38.074
自旋多重度 (单原子计算需设置):
  - 文档: C=3, H=2, N=4, O=3, F=2, Li=2
"""

from __future__ import annotations

from dataclasses import dataclass

# 单原子气相标准生成焓实验值 (kcal/mol)
# 采用文档指标2/3.2 节引用的 ATcT 值; Li 采用 NIST 值 (文档 2.2.1)。
ATOM_EXP_HOF_KCAL_MOL: dict[str, float] = {
    "H": 52.103,
    "C": 171.290,
    "N": 112.970,
    "O": 59.555,
    "Li": 38.074,
}

# 单原子计算的自旋多重度 (文档 2.2.1)
ATOM_MULTIPLICITY: dict[str, int] = {
    "H": 2,
    "C": 3,
    "N": 4,
    "O": 3,
    "F": 2,
    "Li": 2,
}


@dataclass(frozen=True)
class AtomData:
    """单原子参考数据的查询封装, 允许运行时覆盖默认值。"""

    exp_hof_kcal_mol: dict[str, float]
    multiplicity: dict[str, int]

    @classmethod
    def default(cls) -> "AtomData":
        return cls(
            exp_hof_kcal_mol=dict(ATOM_EXP_HOF_KCAL_MOL),
            multiplicity=dict(ATOM_MULTIPLICITY),
        )

    def exp_hof(self, element: str) -> float:
        try:
            return self.exp_hof_kcal_mol[element]
        except KeyError as exc:
            raise KeyError(
                f"元素 {element!r} 无实验生成焓数据; 已知元素: "
                f"{sorted(self.exp_hof_kcal_mol)}"
            ) from exc

    def multiplicity_of(self, element: str) -> int:
        try:
            return self.multiplicity[element]
        except KeyError as exc:
            raise KeyError(
                f"元素 {element!r} 无多重度数据; 已知元素: "
                f"{sorted(self.multiplicity)}"
            ) from exc

    def with_overrides(
        self,
        exp_hof_kcal_mol: dict[str, float] | None = None,
        multiplicity: dict[str, int] | None = None,
    ) -> "AtomData":
        exp = dict(self.exp_hof_kcal_mol)
        mult = dict(self.multiplicity)
        if exp_hof_kcal_mol:
            exp.update(exp_hof_kcal_mol)
        if multiplicity:
            mult.update(multiplicity)
        return AtomData(exp_hof_kcal_mol=exp, multiplicity=mult)
