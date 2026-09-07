# ion_HOF 使用指南

本文档按“先离线复算、再真实 QM、最后远程分发”的顺序编写。所有命令均从
`ion_HOF` 项目根目录执行。项目只负责输入生成、输出解析、公式计算和作业编排；
Gaussian 16、ORCA、调度器和远程机器必须由用户自行提供。

## 1. 安装和自检

推荐使用隔离环境：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ion_HOF --help
```

如果只使用已经给定的 QM 数值，运行时只需要 Python 包和 TOML 支持；`.[dispatch]` 只在
使用 dpdispatcher 提交任务时安装：

```bash
python -m pip install -e ".[dispatch]"
```

## 2. 最短可运行路径：H5N7 离线复算

这个路径不连接远程服务器，也不调用 Gaussian/ORCA。配置中的能量和体积是方法验证例的
已核对输入，用来确认安装、TOML、原子化能法、VBT 和偏差报告链路：

```bash
ion_HOF batch examples/h5n7/config.toml
ion_HOF report examples/h5n7/config.toml
python examples/h5n7/run_demo.py
```

预期范围：气相约 `241.82 kcal/mol`，晶格焓约 `139.23 kcal/mol`，固态约
`102.60 kcal/mol`。`run_demo.py` 输出 JSON，可作为自动化流水线的最小参考。

配置中的离子可以直接写 `enthalpy_hartree` 和 `volume_cm3_mol`，也可以改为：

```toml
energy_file = "work/qm/n5_sp.out"
volume_file = "work/qm/n5_volume.out"
```

路径相对于 TOML 文件所在目录解析；绝对路径保持不变。Gaussian 需要正常终止，ORCA
需要 `ORCA TERMINATED NORMALLY`，解析器拒绝截断或异常输出。

## 3. 真实 QM 输入生成

### 3.1 准备结构

`examples/qm/n5_anion.xyz` 和 `n2h5_cation.xyz` 是输入格式演示，不是发表级结构。真实
工作流应使用 MSD/CSP 产出的结构或经过几何优化的 XYZ，并复核总电荷和多重度。

```bash
mkdir -p work/h5n7/inputs
ion_HOF gen-input examples/qm/n5_anion.xyz \
  --charge -1 --mult 1 --program orca \
  --outdir work/h5n7/inputs/n5 --atoms H N
ion_HOF gen-input examples/qm/n2h5_cation.xyz \
  --charge 1 --mult 1 --program gaussian \
  --outdir work/h5n7/inputs/n2h5 --atoms H N
```

`--atoms` 会生成原子参考输入。若不提供 `--optimized-xyz`，不会伪造 ORCA 高水平单点
输入，以避免把未优化坐标误当作高水平结构。

### 3.2 ORCA 分阶段工作流

更安全的默认路径是：

```bash
ion_HOF orca-thermo examples/qm/n5_anion.xyz \
  --charge -1 --mult 1 --label n5_anion \
  --machine examples/server/local_machine.yaml \
  --resources examples/server/local_resources.yaml \
  --work-base work/h5n7/n5_orca
```

本地模板只适用于本机已安装 ORCA 且 `orca` 在 PATH 中的情况。研究计算通常改用
`jlu184_machine.yaml` 和 `jlu184_resources.yaml`，并显式设置：

```bash
export ORCA_EXE=/data/home/miwenhui/soft/orca_6_1_0_avx2/orca
export ORCA_ENV=/data/home/miwenhui/soft/orca.sh
ion_HOF orca-thermo examples/qm/n5_anion.xyz \
  --charge -1 --mult 1 --label n5_anion \
  --machine work/h5n7/jlu184_machine.yaml \
  --resources work/h5n7/jlu184_resources.yaml \
  --work-base work/h5n7/n5_orca
```

阶段顺序为 `RIJCOSX-B3LYP/def2-SVP Opt Freq` → 结构/频率门禁 →
`M062X/def2-TZVP SP` → `H(high,SP) + Hcorr(low,freq)`。流程只在优化正常终止、收敛、
频率可解析且没有显著虚频时继续；失败目录会保留，便于诊断。

### 3.3 Gaussian 或 ORCA 手动分发

先生成输入，再提交：

```bash
ion_HOF submit work/h5n7/inputs/n5/*.inp \
  --program orca \
  --machine work/h5n7/jlu184_machine.yaml \
  --resources work/h5n7/jlu184_resources.yaml \
  --work-base work/h5n7/dispatch --nodes 1
```

Gaussian 输入单独提交时使用 `.gjf` 文件，并把程序参数切换为 `gaussian`：

```bash
ion_HOF submit work/h5n7/inputs/n2h5/*.gjf \
  --program gaussian \
  --machine work/h5n7/jlu184_machine.yaml \
  --resources work/h5n7/jlu184_resources.yaml \
  --work-base work/h5n7/gaussian --nodes 1
```

Gaussian 输入使用 `.gjf`，并将 `--program gaussian`；远程机器配置应使用 SSH 密钥，
不要把密码写进 YAML。`jlu184_resources.yaml` 中的 `custom_flags` 负责 LSF 头，
不需要把 `#BSUB` 写进运行脚本。

提交返回成功只表示调度器接受任务。回收后逐个解析：

```bash
ion_HOF parse work/h5n7/dispatch/outputs/n5_optfreq.out
```

检查输出中的程序、总焓、热校正和体积，再把路径写回 TOML，运行 `batch` 或 `report`。
默认 `--max-retries 0`；只有明确知道重投不会造成重复计算时才增加重试次数。

## 4. 配置和结果契约

| 字段 | 含义 |
|---|---|
| `method.name` | G4、ccCA、ORCA 等方法标签，仅作为结果追踪元数据 |
| `method.atom_enthalpies_hartree` | 与目标方法一致的单原子总焓 |
| `salt.ion.enthalpy_hartree` | QM 总焓；也可用 `energy_file`/`thermal_file` |
| `salt.ion.volume_cm3_mol` | 0.001 e/Bohr³ 等值面分子体积；也可用 `volume_file` |
| `shape` | `atomic`、`linear` 或 `nonlinear`，影响 VBT 形状项 |
| `count` | 盐式中离子计量数，必须保持电荷中性 |
| `reference` | 可选实验值，供 `report` 计算 MAE/RMSD |

内置 VBT 系数只覆盖文档标定的 `I=1`、1:1 盐。多价盐和非 1:1 盐默认拒绝，不能把
`allow_extrapolation` 当作科学有效性的开关。

## 5. 目录和排错

```text
work/h5n7/
├── inputs/          # 生成的 gjf/inp
├── dispatch/        # dpdispatcher 中间目录和回收输出
└── n5_orca/         # 分阶段 ORCA 工作流、日志和 thermochemistry.json
```

- 找不到 `dpdispatcher`：安装 `python -m pip install -e ".[dispatch]"`。
- 输出被判定为截断：查看原始 `.out/.log` 是否包含正常终止标志。
- 远程任务失败：保留 `work/`，检查 SSH、队列、`ORCA_EXE`/`ORCA_ENV` 和资源配置。
- 结果异常：先单独运行 `ion_HOF parse`，确认能量/热校正/体积来源，再检查 TOML 的
  计量数、形状和单原子参考焓。

## 6. 测试和发布前检查

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m pytest -q --cov=bppa_hof --cov-branch --cov-report=term-missing
python -m build
```

项目测试按 unit/integration/config/system 四层组织；普通测试不会隐式连接 JLU184。
真实 Gaussian/ORCA 验证应作为明确的远程作业单独记录输入、作业号、输出和解析结果。
