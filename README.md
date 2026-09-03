# bppa-hof

全氮 / 富氮离子盐（五唑离子盐等）**生成焓计算工作流**。将《生成焓相关》方法文档中
已实现并验证的计算方法固化为稳定、可复用的 Python 包。

核心关系：

```
固态生成焓 = 气相生成焓 (原子化能法)  −  晶格焓 (VBT 基于体积理论)
```

## 方法概要

对照方法文档 2.2 节：

1. **气相生成焓 — 原子化能法** (2.2.1)

   ```
   ΔHf,gas = H_calc(分子)·627.51 + Σ_i n_i·[ΔHf,exp(原子_i) − H_calc(原子_i)·627.51]
   ```
   - 单原子实验生成焓 (kcal/mol)：C=171.290, H=52.103, N=112.970, O=59.555, Li=38.074
   - 单原子多重度：C=3, H=2, N=4, O=3, F=2, Li=2
   - 单点法单原子加固定焓校正 `0.00236048 Hartree`；G4/ccCA 直接读取焓
   - 支持在低水平优化的结构上，用高水平单点能替换 `E_total` 而保留热力学校正
   - ORCA 输入采用其合法关键字 `M062X`（文献名称写作 M06-2X）

2. **晶格焓 — VBT** (2.2.2)

   ```
   ΔH_L = U_POT + [Σ_i count_i·(n_i/2 − 2)]·RT
   U_POT<5000:  2I(α/Vm^(1/3) + β)      α=117.3, β=51.9
   U_POT>5000:  A·I(2I/Vm^(1/3))         A=121.4
   ```
   - `Vm` 为 0.001 e/Bohr³ 等值面分子体积（cm³/mol，内部换算为 nm³/式单位）
   - 离子形状 → n：单原子 3 / 线性 5 / 非线性 6
   - 内置 `α=117.3, β=51.9` 仅适用于方法文档标定的 `I=1`、1:1 盐；
     多价或非 1:1 盐默认拒绝套用，`allow_extrapolation=True` 只用于诊断比较

## 安装

```bash
pip install -e .
# 开发（pytest、覆盖率、dpdispatcher、YAML；不会因缺分发依赖而跳过系统测试）
pip install -e ".[dev]"
```

Python ≥ 3.9（3.11 以下需 `tomli`，见 `[toml]` 可选依赖）。

## 库用法

```python
from bppa_hof import Ion, Salt

anion  = Ion("N5",   charge=-1, enthalpy_hartree=-273.664407, volume_cm3_mol=44.640)
cation = Ion("N2H5", charge=+1, enthalpy_hartree=-112.120023, volume_cm3_mol=28.479)

salt = Salt([anion, cation], method="G4",
            atom_enthalpies_hartree={"H": -0.49906, "N": -54.571306},
            label="1a+1c")

r = salt.compute()
print(r)   # gas=241.82, lattice=139.23, solid=102.60 kcal/mol
```

### 从 QM 输出文件构造

```python
from bppa_hof.parsers import parse_output
from bppa_hof import Ion

qm = parse_output("test1.log")          # 自动识别，并默认要求正常终止
ion = Ion.from_qm("N5", -1, qm, shape="nonlinear")
```

支持的解析量：
- Gaussian：`G4 Enthalpy=`、`SCF Done`、`Molar volume`
- ORCA：`FINAL SINGLE POINT ENERGY`、`Total correction`、`Thermal Enthalpy correction`、`Total Enthalpy`

## 命令行

```bash
bppa-hof batch  examples/h5n7/config.toml   # 批量计算气相/晶格/固态生成焓
bppa-hof report examples/h5n7/config.toml   # 对含 reference 的盐输出 MAE/RMSD 偏差表
bppa-hof parse  test1.log                    # 解析单个 QM 输出文件
```

配置格式见 `examples/h5n7/config.toml`（离子能量/体积可直接给数值，或用
`energy_file` / `volume_file` 指向 QM 输出）。

## 端到端工作流（新算例）

第一性原理计算本身仍由 ORCA/Gaussian 完成，本包负责**输入生成**与**作业提交**，
把重复的手工步骤自动化。整链路：**生成输入 → 提交作业 → 解析输出 → 计算生成焓**。

### 1. 生成输入文件

```bash
# 为一个离子 (N5-) 生成 ORCA 优化+频率和 Gaussian 体积输入，
# 并额外生成单原子 N 的输入（多重度按 C=3/H=2/N=4/O=3/F=2/Li=2 自动设置）
bppa-hof gen-input n5.xyz --charge -1 --mult 1 --program orca \
    --outdir ./inputs --atoms N H
```

为避免误用未优化坐标，未提供 `--optimized-xyz` 时不会生成 ORCA 高水平单点输入。
推荐直接使用分阶段命令；它只在优化正常终止、确认收敛、解析到频率且无显著虚频后，
才会用回收的优化结构提交高水平单点，并按
`H(high//low) = E(high,SP) + Hcorr(low,freq)` 合成焓：

```bash
bppa-hof orca-thermo n5.xyz --charge -1 --mult 1 --label n5 \
    --machine examples/server/jlu184_machine.yaml \
    --resources examples/server/jlu184_resources.yaml \
    --work-base ./work/n5-orca
```

采用的计算水平对照文档：优化+频率 `RIJCOSX-B3LYP/def2-SVP`，高精度单点
`M06-2X/def2-TZVP`（ORCA 关键字为 `M062X`；可换 G4/ccCA），体积
`B3LYP/def2-SVP + Volume`。
库 API：`bppa_hof.ion_inputs(...)` / `atom_inputs(...)` / `build_orca` / `build_gaussian`。

### 2. 提交作业（dpdispatcher）

提交逻辑参照 `ion_CSP` 的成熟模式（轮询分发到多节点、`forward_files`/`backward_files`
回传、本地/远程 `parent` 前缀统一）。需安装可选依赖：

```bash
pip install -e ".[dispatch]"

# 本地无调度器测试
bppa-hof submit ./inputs/*.inp --program orca \
    --machine examples/server/local_machine.yaml \
    --resources examples/server/local_resources.yaml \
    --work-base ./work --nodes 1

# JLU184 服务器 (LSF 调度器 + SSH)：#BSUB 头由 resources 配置自动生成
bppa-hof submit ./inputs/*.inp --program orca \
    --machine examples/server/jlu184_machine.yaml \
    --resources examples/server/jlu184_resources.yaml \
    --work-base ./work --nodes 1
```

`submit` 和 `orca-thermo` 默认 `--max-retries 0`，防止作业终止后不透明地重复消耗
远程资源；只有明确评估过失败模式后才应提高该值。执行脚本会聚合每个输入的退出状态，
回收阶段要求每个输出存在、非空、程序匹配并正常终止。失败时保留任务目录，不返回部分成功。

machine/resources 模板见 `examples/server/`（本地 Shell、远程通用、以及 JLU184 LSF 专用）。
真正的计算命令写在内置脚本 `scripts/orca_sub.sh` / `scripts/g16_sub.sh` 中。ORCA 脚本已按
JLU184 (`param/sub_orca.sh`) 调整：`ulimit -s unlimited`、`source` ORCA 环境、并用 orca
**绝对路径**运行（并行必需）。可用环境变量覆盖，无需改脚本：

```bash
export ORCA_EXE=/data/home/miwenhui/soft/orca_6_1_0_avx2/orca   # orca 绝对路径
export ORCA_ENV=/data/home/miwenhui/soft/orca.sh                 # 运行前 source 的环境脚本
```

> 说明：调度器头 (`#BSUB -n 56 -q normal -R 'span[ptile=56]'` 等) 不写进运行脚本，
> 而由 dpdispatcher 依据 resources 配置 (`cpu_per_node`/`queue_name`/`custom_flags`) 自动生成。

### 3. 解析 + 计算

```bash
bppa-hof parse ./work/outputs/n5_sp.out    # 查看提取到的能量/体积
# 然后按 config.toml 填入 energy_file/volume_file，运行 batch/report
```

## 验证

包内回归测试锚定文档验证例（五唑肼盐 H₅N₇，G4 方法）：

| 量 | 文档值 | 本包计算 |
|---|---|---|
| 气相生成焓 | 241.825 | 241.82 |
| 晶格焓 | 139.240 | 139.23 |
| 固态生成焓 | 102.58 | 102.60 |
| 三盐 MAE | 1.30 | 1.30 |

```bash
pytest -q
pytest -q -m unit
pytest -q -m integration
pytest -q -m config
pytest -q -m system
pytest -q --cov=bppa_hof --cov-branch --cov-report=term-missing --cov-fail-under=100
```

每个测试必须且只能属于 `unit`、`integration`、`config`、`system` 四层之一；
收集钩子会拒绝未分层测试。2026-09-03 的验证基线为 **77 passed**，生产代码
**970/970 条语句、274/274 个分支，均为 100%**。真实 JLU184 验证另行记录，
不会让日常 pytest 隐式连接远程服务器。

## 适用范围与公开数据验证

真实 JLU184 上已验证 Gaussian 16 的 G4/体积输出和 ORCA 6.1 的分阶段
`B3LYP/def2-SVP Opt Freq → M062X/def2-TZVP SP` 工作流。公开数据外部验证使用：

- Zhong 等，*Communications Chemistry* 2025，DOI
  `10.1038/s42004-025-01544-9`：156 种含能材料；
- Habert 等，*ACS Omega* 2025，DOI `10.1021/acsomega.5c06705`，
  PMCID `PMC12593071`：21 种 energetic salts 的实验生成焓/晶格焓基准。

结论是：本包的计算与解析管线可重复，但固定参数 VBT 不能泛化为通用含能材料模型。
在参数定义覆盖的 8 种 MX/I=1 energetic salts 上，晶格焓 MAE 为
`205.84 kJ/mol`，且系统性低估；其余 13 种 M₂X 盐不属于内置参数适用域，生产 API
默认拒绝计算。当前版本只应作为文档同类 1:1 盐的研究性筛选工具，并显式披露较大的
模型不确定性；多价/非 1:1 盐需要另行验证的计量比参数或电荷分布感知晶格模型。

完整数据清单、来源校验和、脚本、逐项结果和报告位于：
`/workplace/home/yangze/results/BPPA_workflow_validation_20260902/public_data/`。

## 结构

```
src/bppa_hof/
  constants.py     物理常数、单位换算、VBT 系数
  atom_data.py     单原子实验生成焓与多重度
  models.py        Ion / Salt / QMResult + 化学式解析
  geometry.py      分子几何、xyz 读取、单原子构造
  inputgen.py      ORCA/Gaussian 输入文件生成 + 计算配方
  gas_phase.py     原子化能法气相生成焓
  lattice.py       VBT 晶格焓
  salt.py          盐组合与固态生成焓
  deviation.py     MAE / RMSD 偏差分析
  parsers/         Gaussian / ORCA 输出解析
  dispatch.py      dpdispatcher 作业提交 (本地/远程)
  scripts/         g16_sub.sh / orca_sub.sh 运行脚本
  config.py        TOML 批量配置
  cli.py           命令行入口 (batch/report/parse/gen-input/submit)
```
