"""作业分发准备逻辑测试 (不实际提交, 不依赖远程机器)。"""

import pytest

from bppa_hof.dispatch import (
    GAUSSIAN_PROFILE,
    ORCA_PROFILE,
    distribute_jobs,
    get_profile,
    prepare_task_dirs,
)

pytestmark = pytest.mark.integration


def test_distribute_jobs_round_robin():
    # 10 个任务分给 4 节点: [0,4,8],[1,5,9],[2,6],[3,7]
    assert distribute_jobs(10, 4) == [[0, 4, 8], [1, 5, 9], [2, 6], [3, 7]]


def test_distribute_jobs_invalid_nodes():
    with pytest.raises(ValueError):
        distribute_jobs(5, 0)


def test_get_profile():
    assert get_profile("orca") is ORCA_PROFILE
    assert get_profile("gaussian") is GAUSSIAN_PROFILE
    with pytest.raises(ValueError):
        get_profile("psi4")


def _make_inputs(tmp_path, n, suffix):
    files = []
    for i in range(n):
        p = tmp_path / f"mol{i}{suffix}"
        p.write_text(f"input {i}\n")
        files.append(str(p))
    return files


def test_prepare_task_dirs_orca(tmp_path):
    inputs = _make_inputs(tmp_path, 3, ".inp")
    work_base = tmp_path / "work"
    specs = prepare_task_dirs(
        inputs, str(work_base), ORCA_PROFILE, parent="", nodes=2
    )
    assert len(specs) == 2
    # 脚本被复制进每个 pop 目录
    assert (work_base / "pop0" / "orca_sub.sh").exists()
    # 输入文件被复制
    assert (work_base / "pop0" / "mol0.inp").exists()
    # 命令正确
    assert specs[0].command == "chmod +x orca_sub.sh && ./orca_sub.sh"
    # backward_files 含每个输入对应的 .out
    assert "mol0.out" in specs[0].backward_files
    # task_work_path 相对路径
    assert specs[0].task_work_path == "pop0"


def test_prepare_task_dirs_remote_parent(tmp_path):
    inputs = _make_inputs(tmp_path, 2, ".gjf")
    work_base = tmp_path / "work"
    specs = prepare_task_dirs(
        inputs, str(work_base), GAUSSIAN_PROFILE, parent="data/", nodes=1
    )
    assert specs[0].task_work_path == "data/pop0"
    assert (work_base / "data" / "pop0" / "g16_sub.sh").exists()
    assert "mol0.log" in specs[0].backward_files


def test_prepare_task_dirs_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_task_dirs(
            [str(tmp_path / "nope.inp")], str(tmp_path / "w"), ORCA_PROFILE
        )
