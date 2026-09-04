"""命令行接口: ion_HOF。

子命令:
  batch  <config.toml>   批量计算配置中所有盐, 输出气相/晶格/固态生成焓
  report <config.toml>   在 batch 基础上, 对含 reference 的盐计算 MAE/RMSD 偏差表
  parse  <output_file>   解析单个 QM 输出, 打印提取到的能量与体积
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from .config import load_config
from .deviation import deviation_report
from .parsers.base import parse_output


def _cmd_batch(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    print(f"方法: {cfg.method}    盐数量: {len(cfg.salts)}")
    print(
        f"{'编码':<16}{'气相':>12}{'晶格焓':>12}{'固态':>12}"
    )
    print("-" * 52)
    for salt in cfg.salts:
        r = salt.compute()
        label = salt.label or "".join(
            f"{e}{n if n > 1 else ''}" for e, n in sorted(r.composition.items())
        )
        print(
            f"{label:<16}{r.gas_phase_hof:>12.2f}"
            f"{r.lattice_enthalpy:>12.2f}{r.solid_hof:>12.2f}"
        )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    predictions: dict[str, float] = {}
    for salt in cfg.salts:
        if salt.label is None:
            continue
        predictions[salt.label] = salt.solid_hof()

    if not cfg.references:
        print("配置中无 reference 实验值, 无法生成偏差报告。", file=sys.stderr)
        return 1

    report = deviation_report(predictions, cfg.references)
    print(f"方法: {cfg.method}")
    print(report.format_table())
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    result = parse_output(args.output_file)
    print(f"来源: {result.source}")
    print(f"SCF (Hartree):            {result.scf_hartree}")
    print(f"热力学焓校正 (Hartree):   {result.thermal_enthalpy_correction_hartree}")
    print(f"总焓 (Hartree):           {result.total_enthalpy_hartree}")
    try:
        print(f"焓 enthalpy() (Hartree):  {result.enthalpy()}")
    except ValueError:
        print("焓 enthalpy():            <不足以计算>")
    print(f"分子体积 (cm^3/mol):      {result.molar_volume_cm3_mol}")
    return 0


def _cmd_geninput(args: argparse.Namespace) -> int:
    from .geometry import Molecule
    from .inputgen import atom_inputs, ion_inputs

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    written: list[str] = []

    if args.xyz:
        mol = Molecule.from_xyz(
            args.xyz, charge=args.charge, multiplicity=args.mult
        )
        optimized = None
        if args.optimized_xyz:
            optimized = Molecule.from_xyz(
                args.optimized_xyz,
                charge=args.charge,
                multiplicity=args.mult,
            )
        inputs = ion_inputs(
            mol,
            program=args.program,
            high_level_sp=not args.no_sp,
            optimized_molecule=optimized,
            volume=not args.no_volume,
            mc_points=args.mc_points,
        )
        for purpose, (fname, text) in inputs.items():
            path = os.path.join(outdir, fname)
            with open(path, "w") as fh:
                fh.write(text)
            written.append(f"{path}  [{purpose}]")

    if args.atoms:
        atom_prog = args.atom_program or (
            "gaussian" if args.program == "gaussian" else "orca"
        )
        for el, (fname, text) in atom_inputs(
            args.atoms, program=atom_prog
        ).items():
            path = os.path.join(outdir, fname)
            with open(path, "w") as fh:
                fh.write(text)
            written.append(f"{path}  [atom {el}]")

    if not written:
        print("未生成任何输入 (需提供 xyz 或 --atoms)。", file=sys.stderr)
        return 1
    print("已生成输入文件:")
    for w in written:
        print(f"  {w}")
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    from .dispatch import run_jobs

    outputs = run_jobs(
        args.inputs,
        work_base=args.work_base,
        machine_path=args.machine,
        resources_path=args.resources,
        program=args.program,
        nodes=args.nodes,
        cleanup=not args.keep_temp,
        script_path=args.script,
        max_retries=args.max_retries,
    )
    print(f"完成, 回收 {len(outputs)} 个输出文件:")
    for base, path in sorted(outputs.items()):
        print(f"  {base}: {path}")
    return 0


def _cmd_orca_thermo(args: argparse.Namespace) -> int:
    from .geometry import Molecule
    from .workflow import run_orca_thermochemistry

    molecule = Molecule.from_xyz(
        args.xyz,
        charge=args.charge,
        multiplicity=args.mult,
        name=args.label,
    )
    result = run_orca_thermochemistry(
        molecule,
        work_base=args.work_base,
        machine_path=args.machine,
        resources_path=args.resources,
        nodes=args.nodes,
        script_path=args.script,
        max_retries=args.max_retries,
    )
    print(f"ORCA 分阶段热化学完成: {result.label}")
    print(f"总焓 (Hartree): {result.enthalpy_hartree:.12f}")
    print(f"结果: {os.path.join(args.work_base, 'thermochemistry.json')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ion_HOF",
        description="全氮/富氮离子盐生成焓计算工作流",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_batch = sub.add_parser("batch", help="批量计算配置中所有盐的生成焓")
    p_batch.add_argument("config", help="TOML 配置文件路径")
    p_batch.set_defaults(func=_cmd_batch)

    p_report = sub.add_parser("report", help="计算偏差 (MAE/RMSD) 报告")
    p_report.add_argument("config", help="TOML 配置文件路径")
    p_report.set_defaults(func=_cmd_report)

    p_parse = sub.add_parser("parse", help="解析单个 QM 输出文件")
    p_parse.add_argument("output_file", help="Gaussian/ORCA 输出文件路径")
    p_parse.set_defaults(func=_cmd_parse)

    p_gen = sub.add_parser("gen-input", help="生成 ORCA/Gaussian 输入文件")
    p_gen.add_argument("xyz", nargs="?", help="离子 xyz 结构文件 (可选)")
    p_gen.add_argument("--charge", type=int, default=0, help="离子电荷 (默认 0)")
    p_gen.add_argument("--mult", type=int, default=1, help="自旋多重度 (默认 1)")
    p_gen.add_argument(
        "--program", choices=["orca", "gaussian"], default="orca",
        help="目标计算程序 (默认 orca)",
    )
    p_gen.add_argument("--outdir", default="./inputs", help="输出目录")
    p_gen.add_argument(
        "--optimized-xyz",
        default=None,
        help="已优化的 XYZ；提供后才生成 ORCA 高水平单点输入",
    )
    p_gen.add_argument("--no-sp", action="store_true", help="不生成高精度单点输入 (orca)")
    p_gen.add_argument("--no-volume", action="store_true", help="不生成体积计算输入")
    p_gen.add_argument("--mc-points", type=int, default=10000, help="体积蒙特卡洛采样点数")
    p_gen.add_argument(
        "--atoms", nargs="+", metavar="EL", help="额外生成这些元素的单原子输入, 如 --atoms N H"
    )
    p_gen.add_argument(
        "--atom-program", choices=["orca", "gaussian"], default=None,
        help="单原子输入使用的程序 (默认跟随 --program)",
    )
    p_gen.set_defaults(func=_cmd_geninput)

    p_sub = sub.add_parser("submit", help="通过 dpdispatcher 提交 QM 作业")
    p_sub.add_argument("inputs", nargs="+", help="输入文件路径 (.gjf/.inp)")
    p_sub.add_argument(
        "--program", choices=["orca", "gaussian"], required=True, help="QM 程序"
    )
    p_sub.add_argument("--machine", required=True, help="dpdispatcher machine 配置 (json/yaml)")
    p_sub.add_argument("--resources", required=True, help="dpdispatcher resources 配置 (json/yaml)")
    p_sub.add_argument("--work-base", default="./work", help="提交工作根目录")
    p_sub.add_argument("--nodes", type=int, default=1, help="分发节点数")
    p_sub.add_argument("--keep-temp", action="store_true", help="保留临时 pop 目录")
    p_sub.add_argument("--script", default=None, help="覆盖内置 QM 执行脚本")
    p_sub.add_argument(
        "--max-retries", type=int, default=0, help="作业终止后的最大重投次数 (默认 0)"
    )
    p_sub.set_defaults(func=_cmd_submit)

    p_orca = sub.add_parser(
        "orca-thermo",
        help="分阶段运行 ORCA 优化频率和高水平单点并合成总焓",
    )
    p_orca.add_argument("xyz", help="初始 XYZ 结构")
    p_orca.add_argument("--charge", type=int, required=True, help="电荷")
    p_orca.add_argument("--mult", type=int, required=True, help="自旋多重度")
    p_orca.add_argument("--label", required=True, help="任务标签/安全文件名前缀")
    p_orca.add_argument("--machine", required=True, help="dpdispatcher machine 配置")
    p_orca.add_argument("--resources", required=True, help="dpdispatcher resources 配置")
    p_orca.add_argument("--work-base", required=True, help="全新的工作流目录")
    p_orca.add_argument("--nodes", type=int, default=1, help="每阶段分发节点数")
    p_orca.add_argument("--script", default=None, help="覆盖内置 ORCA 执行脚本")
    p_orca.add_argument(
        "--max-retries", type=int, default=0, help="每阶段最大重投次数 (默认 0)"
    )
    p_orca.set_defaults(func=_cmd_orca_thermo)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
