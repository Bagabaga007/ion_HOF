"""分子几何: xyz 读取、组成统计、单原子构造。"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from .atom_data import ATOM_MULTIPLICITY

Atom = tuple[str, float, float, float]


@dataclass
class Molecule:
    """一个分子/离子的笛卡尔坐标与电子态。

    atoms:        [(元素, x, y, z), ...] 单位 Angstrom
    charge:       带符号电荷
    multiplicity: 自旋多重度
    name:         标签 (用于文件名/标题)
    """

    atoms: list[Atom]
    charge: int = 0
    multiplicity: int = 1
    name: str = "molecule"

    def __post_init__(self) -> None:
        if not self.atoms:
            raise ValueError("分子至少需要一个原子")
        if self.multiplicity < 1:
            raise ValueError("多重度必须 >= 1")

    @classmethod
    def from_xyz(
        cls,
        path: str,
        *,
        charge: int = 0,
        multiplicity: int = 1,
        name: Optional[str] = None,
    ) -> "Molecule":
        """从标准 xyz 文件读取 (第一行原子数, 第二行注释, 其后为坐标)。"""
        with open(path, "r") as fh:
            lines = fh.read().splitlines()
        if len(lines) < 3:
            raise ValueError(f"xyz 文件内容不足: {path}")
        try:
            n = int(lines[0].strip())
        except ValueError as exc:
            raise ValueError(f"xyz 首行应为原子数: {path}") from exc

        atoms: list[Atom] = []
        for line in lines[2 : 2 + n]:
            parts = line.split()
            if len(parts) < 4:
                continue
            el = parts[0]
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            atoms.append((el, x, y, z))
        if len(atoms) != n:
            raise ValueError(
                f"xyz 声明 {n} 个原子, 实际解析到 {len(atoms)} 个: {path}"
            )
        return cls(
            atoms=atoms,
            charge=charge,
            multiplicity=multiplicity,
            name=name or os.path.splitext(os.path.basename(path))[0],
        )

    def composition(self) -> dict[str, int]:
        counts: Counter[str] = Counter(el for el, *_ in self.atoms)
        return dict(counts)

    def coordinate_block(self, fmt: str = "{el:<3} {x:>14.8f} {y:>14.8f} {z:>14.8f}") -> str:
        """返回坐标文本块 (每行一个原子)。"""
        return "\n".join(
            fmt.format(el=el, x=x, y=y, z=z) for el, x, y, z in self.atoms
        )


def single_atom(element: str, *, multiplicity: Optional[int] = None) -> Molecule:
    """构造单原子分子 (置于原点), 多重度默认取文档规定值。

    文档: C=3, H=2, N=4, O=3, F=2, Li=2。
    """
    if multiplicity is None:
        if element not in ATOM_MULTIPLICITY:
            raise KeyError(
                f"元素 {element!r} 无默认多重度, 请显式提供 multiplicity"
            )
        multiplicity = ATOM_MULTIPLICITY[element]
    return Molecule(
        atoms=[(element, 0.0, 0.0, 0.0)],
        charge=0,
        multiplicity=multiplicity,
        name=f"atom_{element}",
    )
