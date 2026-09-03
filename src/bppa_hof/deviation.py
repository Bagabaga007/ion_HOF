"""偏差分析: MAE / RMSD 与逐物质偏差表 (文档 3.2.1 / 指标2)。

平均绝对误差 (文档式 6/12):
    MAE = (1/m) Σ |y_pred − y_std|
均方根偏差:
    RMSD = sqrt((1/m) Σ (y_pred − y_std)^2)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class DeviationEntry:
    label: str
    predicted: float
    reference: float

    @property
    def error(self) -> float:
        """带符号偏差 y_pred − y_std。"""
        return self.predicted - self.reference

    @property
    def abs_error(self) -> float:
        return abs(self.error)


@dataclass
class DeviationReport:
    entries: list[DeviationEntry]

    @property
    def n(self) -> int:
        return len(self.entries)

    @property
    def mae(self) -> float:
        if not self.entries:
            raise ValueError("无数据, 无法计算 MAE")
        return sum(e.abs_error for e in self.entries) / self.n

    @property
    def rmsd(self) -> float:
        if not self.entries:
            raise ValueError("无数据, 无法计算 RMSD")
        return math.sqrt(sum(e.error**2 for e in self.entries) / self.n)

    @property
    def max_positive(self) -> DeviationEntry:
        return max(self.entries, key=lambda e: e.error)

    @property
    def max_negative(self) -> DeviationEntry:
        return min(self.entries, key=lambda e: e.error)

    def format_table(self) -> str:
        """生成对齐的文本偏差表 (kcal/mol)。"""
        header = f"{'编码':<16}{'预测值':>12}{'实验值':>12}{'绝对误差':>12}"
        lines = [header, "-" * len(header)]
        for e in self.entries:
            lines.append(
                f"{e.label:<16}{e.predicted:>12.2f}"
                f"{e.reference:>12.2f}{e.abs_error:>12.2f}"
            )
        lines.append("-" * len(header))
        lines.append(f"{'MAE':<16}{'':>12}{'':>12}{self.mae:>12.2f}")
        lines.append(f"{'RMSD':<16}{'':>12}{'':>12}{self.rmsd:>12.2f}")
        return "\n".join(lines)


def deviation_report(
    predictions: dict[str, float],
    references: dict[str, float],
) -> DeviationReport:
    """构造偏差报告。仅对 predictions 与 references 共有的编码求偏差。"""
    labels = [k for k in predictions if k in references]
    if not labels:
        raise ValueError("预测值与参考值无共同编码")
    entries = [
        DeviationEntry(label, predictions[label], references[label])
        for label in labels
    ]
    return DeviationReport(entries)
