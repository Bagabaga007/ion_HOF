# ion_HOF 项目简介与主题

## 一句话定位

`ion_HOF` 是 HEMERA/BPPA 的离子盐生成焓研究执行管线：把 Gaussian/ORCA 输入生成、
本地或 dpdispatcher 远程作业、严格输出解析、原子化能法、VBT 晶格焓和实验偏差报告
串成可复查工作流。

## 主题关键词

`energetic-materials`, `enthalpy-of-formation`, `ionic-salts`, `quantum-chemistry`,
`Gaussian`, `ORCA`, `thermochemistry`, `dpdispatcher`, `HEMERA`。

## 输入与输出

- 输入：XYZ 结构、Gaussian/ORCA 输出、单原子参考焓、分子体积和盐计量配置。
- 中间过程：QM 输入生成、优化/频率/高水平单点、严格正常终止与频率门禁。
- 输出：气相生成焓、VBT 晶格焓、固态生成焓、MAE/RMSD 和可追踪 JSON/日志。

## 两条使用路径

1. [H5N7 离线案例](../examples/h5n7/README.md)：不需要外部 QM，用于安装与公式复算。
2. [完整使用指南](usage.md)：真实 Gaussian/ORCA、JLU184 分发、回收和结果解析。

## 科学边界

内置 VBT 系数只覆盖文档标定的 `I=1`、1:1 盐；多价或非 1:1 盐默认拒绝。离线案例的
QM 数值是已验证输入，不等价于重新运行量化计算；研究结论必须保存真实输入、作业号、
输出和解析记录。
