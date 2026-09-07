# H5N7 生成焓可运行案例

这个案例对应方法文档中的五唑肼盐（`1a + 1c`，总式 `N7H5`）。它有意分成两条路径：

1. **离线复算路径**：配置中已经记录经过验证的 QM 总焓和分子体积，不需要 Gaussian、ORCA
   或远程服务器，适合第一次安装后的冒烟验证。
2. **真实 QM 路径**：使用 `examples/qm/*.xyz` 生成 Gaussian/ORCA 输入，再将真实输出填入
   TOML 配置或交给 `orca-thermo` 分阶段工作流。该路径需要外部程序和调度资源。

## 1. 安装与离线复算

在项目根目录执行：

```bash
python -m pip install -e ".[dev]"
ion_HOF batch examples/h5n7/config.toml
ion_HOF report examples/h5n7/config.toml
python examples/h5n7/run_demo.py
```

预期数值（浮点格式可能有末位差异）：

```text
气相生成焓 ≈ 241.82 kcal/mol
晶格焓     ≈ 139.23 kcal/mol
固态生成焓 ≈ 102.60 kcal/mol
实验参考值 = 103.70 kcal/mol
```

`run_demo.py` 会把同一配置通过 Python API 重新计算并输出 JSON；它不读取或修改项目外
的文件。该步骤验证的是公式、VBT 参数、TOML 解析和偏差报告，不代表重新运行了 QM。

## 2. 生成真实 QM 输入

示例 XYZ 只是输入生成演示用的几何快照，不能替代经过结构优化的研究结构。先检查并替换
为你自己的优化坐标，再生成输入：

```bash
mkdir -p work/h5n7/inputs
ion_HOF gen-input examples/qm/n5_anion.xyz \
  --charge -1 --mult 1 --program orca \
  --outdir work/h5n7/inputs/n5 --atoms H N

ion_HOF gen-input examples/qm/n2h5_cation.xyz \
  --charge 1 --mult 1 --program gaussian \
  --outdir work/h5n7/inputs/n2h5 --atoms H N
```

对于 ORCA，建议用 `orca-thermo` 一次性执行“优化+频率 → 结构门禁 → 高水平单点 →
热校正合并”：

```bash
ion_HOF orca-thermo examples/qm/n5_anion.xyz \
  --charge -1 --mult 1 --label n5_anion \
  --machine examples/server/jlu184_machine.yaml \
  --resources examples/server/jlu184_resources.yaml \
  --work-base work/h5n7/n5_orca
```

它要求优化正常终止、优化收敛、频率可解析且没有显著虚频，然后才会提交高水平单点。
默认计算配方是 `RIJCOSX-B3LYP/def2-SVP Opt Freq` 和 `M062X/def2-TZVP SP`；
`M062X` 是 ORCA 关键字，文献通常写成 M06-2X。

## 3. JLU184/远程作业配置

复制模板并只替换占位符，不要把密码、私钥或真实主机地址提交到仓库：

```bash
cp examples/server/jlu184_machine.yaml work/h5n7/jlu184_machine.yaml
cp examples/server/jlu184_resources.yaml work/h5n7/jlu184_resources.yaml
# 编辑 work/h5n7/*.yaml 中的 hostname、username、key_filename
export ORCA_EXE=/data/home/miwenhui/soft/orca_6_1_0_avx2/orca
export ORCA_ENV=/data/home/miwenhui/soft/orca.sh
```

若使用 `submit` 手动提交，先确认输入文件和资源配置，再执行：

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

提交成功不等于科学结果有效。必须检查每个回收输出文件非空、程序类型正确、正常终止，
再用：

```bash
ion_HOF parse work/h5n7/dispatch/outputs/n5_optfreq.out
```

将解析出的总焓、体积和方法填入工作配置后，运行 `ion_HOF batch`/`report`。远程失败时
保留 `work/` 目录用于诊断；默认 `--max-retries 0`，避免不透明地重复消耗计算资源。

## 4. 结果解释

- `gas_phase_hof`：原子化能法气相生成焓。
- `lattice_enthalpy`：VBT 晶格焓；内置系数仅对文档标定的 `I=1`、1:1 盐有效。
- `solid_hof`：气相生成焓减晶格焓。
- 内置模型不是通用含能材料预测器；多价或非 1:1 盐默认拒绝，不能只为得到数字而打开
  `allow_extrapolation`。

完整方法限制、公开数据复验和不确定性说明见项目根目录 `README.md` 与 `docs/验证与适用范围_20260903.md`。
