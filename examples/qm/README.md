# QM 输入生成示例

目录中的 XYZ 文件只用于演示 `ion_HOF gen-input` 的输入格式和文件命名，不是经过验证的
最终研究几何。实际计算前应替换为 MSD/CSP 或 Gaussian/ORCA 优化得到的结构，并核对
电荷、总自旋和元素计量。

```bash
ion_HOF gen-input examples/qm/n5_anion.xyz \
  --charge -1 --mult 1 --program orca --outdir work/qm/n5

ion_HOF gen-input examples/qm/n2h5_cation.xyz \
  --charge 1 --mult 1 --program gaussian --outdir work/qm/n2h5
```

输出目录中会出现 ORCA 优化/频率、Gaussian 体积和（在提供优化坐标时）高水平单点输入。
真实提交、正常终止检查和输出解析请按 [`../h5n7/README.md`](../h5n7/README.md) 操作。
