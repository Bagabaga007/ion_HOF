"""基于 dpdispatcher 的作业提交 (本地 / 远程 HPC)。

设计参照 /workplace/home/yangze/ion_CSP 中 dpdisp_gaussian_tasks 的成熟模式:
  1. machine_resources_prep: 加载 machine/resources 配置, 判定本地/远程前缀 parent
  2. prepare_task_dirs: 把运行脚本 + 输入文件轮询分发到 {parent}pop{i} 目录 (纯函数, 可测)
  3. run_jobs: 构造 dpdispatcher Task/Submission, run_submission (阻塞), 回收输出

dpdispatcher 为可选依赖: 仅在真正提交 (run_jobs / machine_resources_prep) 时导入。
输入文件生成与任务目录准备不依赖 dpdispatcher。
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 程序档案: 每种 QM 程序的脚本、输入后缀、命令与回传产物
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProgramProfile:
    name: str
    script: str  # 打包内置的运行脚本文件名
    input_suffix: str  # ".gjf" / ".inp"
    command: str  # 传给 Task.command
    output_suffixes: tuple[str, ...]  # 每个输入对应回传的输出后缀


GAUSSIAN_PROFILE = ProgramProfile(
    name="gaussian",
    script="g16_sub.sh",
    input_suffix=".gjf",
    command="chmod +x g16_sub.sh && ./g16_sub.sh",
    output_suffixes=(".log",),
)
ORCA_PROFILE = ProgramProfile(
    name="orca",
    script="orca_sub.sh",
    input_suffix=".inp",
    command="chmod +x orca_sub.sh && ./orca_sub.sh",
    output_suffixes=(".out",),
)
_PROFILES = {"gaussian": GAUSSIAN_PROFILE, "orca": ORCA_PROFILE}


def get_profile(program: str) -> ProgramProfile:
    key = program.lower()
    if key not in _PROFILES:
        raise ValueError(f"未知 program: {program!r} (可选 gaussian/orca)")
    return _PROFILES[key]


def _bundled_script_path(script: str) -> Path:
    """定位打包内置脚本 (src/bppa_hof/scripts/<script>)。"""
    from importlib.resources import files

    return Path(str(files("bppa_hof").joinpath("scripts", script)))


# ---------------------------------------------------------------------------
# 任务规格 (与 dpdispatcher 解耦, 便于单测)
# ---------------------------------------------------------------------------
@dataclass
class TaskSpec:
    command: str
    task_work_path: str
    forward_files: list[str]
    backward_files: list[str]
    input_bases: list[str] = field(default_factory=list)


def distribute_jobs(n_files: int, nodes: int) -> list[list[int]]:
    """将 n 个任务轮询分配给 nodes 个节点, 返回每节点的文件索引列表。"""
    if nodes < 1:
        raise ValueError("nodes 必须 >= 1")
    node_jobs: list[list[int]] = [[] for _ in range(nodes)]
    for index in range(n_files):
        node_jobs[index % nodes].append(index)
    return node_jobs


def prepare_task_dirs(
    input_files: list[str],
    work_base: str,
    profile: ProgramProfile,
    *,
    parent: str = "",
    nodes: int = 1,
    script_path: Optional[str] = None,
    extra_output_suffixes: tuple[str, ...] = (),
) -> list[TaskSpec]:
    """创建 {work_base}/{parent}pop{i} 目录, 复制脚本与输入文件, 返回任务规格。

    纯文件准备, 不导入 dpdispatcher; 供 run_jobs 与测试共用。
    """
    input_paths = [Path(f) for f in input_files]
    if not input_paths:
        raise ValueError("至少需要一个输入文件")
    for p in input_paths:
        if not p.exists():
            raise FileNotFoundError(f"输入文件不存在: {p}")
        if p.suffix.lower() != profile.input_suffix:
            raise ValueError(
                f"{profile.name} 输入必须使用 {profile.input_suffix}: {p}"
            )

    bases = [p.stem for p in input_paths]
    if len(bases) != len(set(bases)):
        raise ValueError("输入文件基名必须唯一，避免输出覆盖")

    work_base_path = Path(work_base)
    script_src = Path(script_path) if script_path else _bundled_script_path(profile.script)
    if not script_src.exists():
        raise FileNotFoundError(f"运行脚本不存在: {script_src}")

    node_jobs = distribute_jobs(len(input_paths), min(nodes, len(input_paths)))
    specs: list[TaskSpec] = []
    for pop, job_indices in enumerate(node_jobs):
        rel_dir = f"{parent}pop{pop}"
        task_dir = work_base_path / rel_dir
        if task_dir.exists() and any(task_dir.iterdir()):
            raise FileExistsError(f"任务目录非空，拒绝复用可能含旧输出的目录: {task_dir}")
        task_dir.mkdir(parents=True, exist_ok=True)

        # 复制运行脚本
        shutil.copyfile(str(script_src), str(task_dir / profile.script))
        forward_files = [profile.script]
        backward_files: list[str] = ["log", "err"]  # 调度器 stdout/stderr
        input_bases: list[str] = []

        for job_i in job_indices:
            src = input_paths[job_i]
            shutil.copyfile(str(src), str(task_dir / src.name))
            forward_files.append(src.name)
            base = src.stem
            input_bases.append(base)
            for suffix in profile.output_suffixes:
                backward_files.append(f"{base}{suffix}")
            for suffix in extra_output_suffixes:
                backward_files.append(f"{base}{suffix}")

        specs.append(
            TaskSpec(
                command=profile.command,
                task_work_path=rel_dir,
                forward_files=forward_files,
                backward_files=backward_files,
                input_bases=input_bases,
            )
        )
    return specs


# ---------------------------------------------------------------------------
# 配置加载 (需要 dpdispatcher)
# ---------------------------------------------------------------------------
def machine_resources_prep(machine_path: str, resources_path: str):
    """加载 machine / resources 配置, 返回 (machine, resources, parent)。

    parent: 远程 SSHContext -> "data/"; 本地 LocalContext -> ""。
    (逻辑参照 ion_CSP/log_and_time.py, 以统一本地/远程任务目录命名。)
    """
    try:
        from dpdispatcher import Machine, Resources
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "作业提交需要 dpdispatcher, 请安装: pip install 'ion_HOF[dispatch]'"
        ) from exc

    def _load(path, cls):
        if path.endswith(".json"):
            return cls.load_from_json(path)
        if path.endswith(".yaml") or path.endswith(".yml"):
            return cls.load_from_yaml(path)
        raise KeyError(f"不支持的配置文件类型: {path}")

    machine = _load(machine_path, Machine)
    resources = _load(resources_path, Resources)

    info = machine.serialize()
    context_type = info.get("context_type")
    batch_type = info.get("batch_type")
    if (
        isinstance(context_type, str)
        and context_type == "SSHContext"
        and isinstance(batch_type, str)
        and batch_type.lower() == "shell"
    ):
        logger.warning(
            "machine 使用 batch_type='Shell' + context_type='SSHContext': "
            "任务将通过 ssh 直接在远程主机运行, 不经调度器。若为集群登录节点, "
            "重计算 (Gaussian/ORCA) 会压垮该节点。集群提交请用 Slurm/LSF/PBS。"
        )

    if context_type == "SSHContext":
        parent = "data/"
    elif context_type == "LocalContext":
        parent = ""
    else:
        raise KeyError(f"不支持的 context_type: {context_type!r}")
    return machine, resources, parent


# ---------------------------------------------------------------------------
# 提交与回收
# ---------------------------------------------------------------------------
def run_jobs(
    input_files: list[str],
    work_base: str,
    machine_path: str,
    resources_path: str,
    *,
    program: str,
    nodes: int = 1,
    cleanup: bool = True,
    script_path: Optional[str] = None,
    required_artifact_suffixes: tuple[str, ...] = (),
    validate_outputs: bool = True,
    max_retries: int = 0,
) -> dict[str, str]:
    """提交一批 QM 输入并阻塞至完成, 返回 {输入基名: 输出文件绝对路径}。

    参数
    ----
    input_files:   待提交的输入文件路径列表 (.gjf 或 .inp)。
    work_base:     提交工作根目录 (task_work_path 相对于此)。
    machine_path/resources_path: dpdispatcher 配置 (json/yaml)。
    program:       "gaussian" | "orca"。
    nodes:         分发的节点数 (轮询均分)。
    cleanup:       完成后是否删除临时 pop 目录 (输出已回收)。
    """
    from dpdispatcher import Submission, Task

    profile = get_profile(program)
    if max_retries < 0:
        raise ValueError("max_retries 必须 >= 0")
    machine, resources, parent = machine_resources_prep(machine_path, resources_path)
    machine.retry_count = max_retries

    specs = prepare_task_dirs(
        input_files,
        work_base,
        profile,
        parent=parent,
        nodes=nodes,
        script_path=script_path,
        extra_output_suffixes=required_artifact_suffixes,
    )
    task_list = [
        Task(
            command=s.command,
            task_work_path=s.task_work_path,
            forward_files=s.forward_files,
            backward_files=s.backward_files,
        )
        for s in specs
    ]

    submission = Submission(
        work_base=str(work_base),
        machine=machine,
        resources=resources,
        task_list=task_list,
    )
    submission.run_submission()

    # 回收输出到 {work_base}/outputs/, 再清理临时 pop 目录 (避免删掉回传文件)
    work_base_path = Path(work_base)
    results_dir = work_base_path / "outputs"
    results_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, str] = {}
    failures: list[str] = []
    required_suffixes = profile.output_suffixes + required_artifact_suffixes
    for spec in specs:
        task_dir = work_base_path / spec.task_work_path
        for base in spec.input_bases:
            for suffix in required_suffixes:
                candidate = task_dir / f"{base}{suffix}"
                if not candidate.is_file() or candidate.stat().st_size == 0:
                    failures.append(f"{base}: 缺少或为空 {candidate.name}")
                    continue
                dest = results_dir / candidate.name
                shutil.copyfile(str(candidate), str(dest))
                if suffix in profile.output_suffixes:
                    outputs[base] = str(dest.resolve())

    expected_bases = {p.stem for p in map(Path, input_files)}
    missing_primary = expected_bases - set(outputs)
    failures.extend(f"{base}: 缺少主输出" for base in sorted(missing_primary))

    if validate_outputs:
        from .parsers.base import parse_output

        for base, path in sorted(outputs.items()):
            try:
                result = parse_output(path)
                if result.program != profile.name:
                    raise ValueError(
                        f"程序不匹配: 期望 {profile.name}, 实际 {result.program}"
                    )
            except (OSError, ValueError) as exc:
                failures.append(f"{base}: 输出验证失败: {exc}")

    if failures:
        raise RuntimeError(
            "QM 作业输出不完整；保留任务目录供诊断:\n- " + "\n- ".join(failures)
        )

    if cleanup:
        if parent:
            shutil.rmtree(work_base_path / parent.rstrip("/"), ignore_errors=True)
        else:
            for spec in specs:
                shutil.rmtree(
                    work_base_path / spec.task_work_path, ignore_errors=True
                )
    return outputs
