"""分发输入契约、machine/resources 加载和失败语义集成测试。"""

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import dpdispatcher
import pytest

import bppa_hof.dispatch as dispatch
from bppa_hof.dispatch import GAUSSIAN_PROFILE, prepare_task_dirs, run_jobs

pytestmark = pytest.mark.integration


def _input(path: Path, name: str = "x.gjf") -> str:
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("input\n")
    return str(target)


def test_prepare_task_dirs_rejects_ambiguous_or_stale_inputs(tmp_path):
    with pytest.raises(ValueError, match="至少需要"):
        prepare_task_dirs([], str(tmp_path / "work"), GAUSSIAN_PROFILE)

    wrong = _input(tmp_path, "x.inp")
    with pytest.raises(ValueError, match="必须使用"):
        prepare_task_dirs([wrong], str(tmp_path / "work"), GAUSSIAN_PROFILE)

    a = _input(tmp_path / "a", "same.gjf")
    b = _input(tmp_path / "b", "same.gjf")
    with pytest.raises(ValueError, match="基名必须唯一"):
        prepare_task_dirs([a, b], str(tmp_path / "work"), GAUSSIAN_PROFILE)

    good = _input(tmp_path, "good.gjf")
    with pytest.raises(FileNotFoundError, match="运行脚本"):
        prepare_task_dirs(
            [good],
            str(tmp_path / "work"),
            GAUSSIAN_PROFILE,
            script_path=str(tmp_path / "missing.sh"),
        )

    stale = tmp_path / "stale" / "pop0"
    stale.mkdir(parents=True)
    (stale / "old.log").write_text("old")
    with pytest.raises(FileExistsError, match="拒绝复用"):
        prepare_task_dirs([good], str(tmp_path / "stale"), GAUSSIAN_PROFILE)


def test_prepare_task_dirs_caps_nodes_and_adds_artifacts(tmp_path):
    source = _input(tmp_path, "one.gjf")
    script = tmp_path / "custom.sh"
    script.write_text("#!/bin/bash\n")
    specs = prepare_task_dirs(
        [source],
        str(tmp_path / "work"),
        GAUSSIAN_PROFILE,
        nodes=5,
        script_path=str(script),
        extra_output_suffixes=(".chk",),
    )
    assert len(specs) == 1
    assert "one.chk" in specs[0].backward_files


class _FakeConfig:
    context_type = "LocalContext"
    batch_type = "Shell"

    @classmethod
    def load_from_json(cls, path):
        data = json.loads(Path(path).read_text())
        obj = cls()
        obj.context_type = data.get("context_type", cls.context_type)
        obj.batch_type = data.get("batch_type", cls.batch_type)
        return obj

    @classmethod
    def load_from_yaml(cls, path):
        data = {}
        for line in Path(path).read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip().strip("'\"")
        obj = cls()
        obj.context_type = data.get("context_type", cls.context_type)
        obj.batch_type = data.get("batch_type", cls.batch_type)
        return obj

    def serialize(self):
        return {
            "context_type": self.context_type,
            "batch_type": self.batch_type,
            "remote_profile": {},
        }


def test_machine_resources_formats_contexts_and_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(dpdispatcher, "Machine", _FakeConfig)
    monkeypatch.setattr(dpdispatcher, "Resources", _FakeConfig)
    resources = tmp_path / "resources.json"
    resources.write_text("{}")

    local = tmp_path / "local.yaml"
    local.write_text("context_type: LocalContext\nbatch_type: Shell\n")
    _, _, parent = dispatch.machine_resources_prep(str(local), str(resources))
    assert parent == ""

    remote = tmp_path / "remote.yml"
    remote.write_text("context_type: SSHContext\nbatch_type: Shell\n")
    caplog.set_level(logging.WARNING)
    _, _, parent = dispatch.machine_resources_prep(str(remote), str(resources))
    assert parent == "data/"
    assert "登录节点" in caplog.text

    unsupported = tmp_path / "unsupported.yaml"
    unsupported.write_text("context_type: DockerContext\nbatch_type: Shell\n")
    with pytest.raises(KeyError, match="context_type"):
        dispatch.machine_resources_prep(str(unsupported), str(resources))

    bad = tmp_path / "machine.txt"
    bad.write_text("x")
    with pytest.raises(KeyError, match="配置文件类型"):
        dispatch.machine_resources_prep(str(bad), str(resources))


class _FakeTask:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeSubmission:
    writer = None
    last_machine = None

    def __init__(self, *, work_base, machine, resources, task_list):
        self.work_base = Path(work_base)
        self.task_list = task_list
        _FakeSubmission.last_machine = machine

    def run_submission(self):
        if self.writer:
            for task in self.task_list:
                self.writer(self.work_base / task.task_work_path, task)


def _install_fake_dispatch(monkeypatch, writer, parent=""):
    _FakeSubmission.writer = staticmethod(writer) if writer else None
    monkeypatch.setattr(dpdispatcher, "Task", _FakeTask)
    monkeypatch.setattr(dpdispatcher, "Submission", _FakeSubmission)
    monkeypatch.setattr(
        dispatch,
        "machine_resources_prep",
        lambda machine, resources: (SimpleNamespace(), SimpleNamespace(), parent),
    )


def test_run_jobs_rejects_missing_and_wrong_program_outputs(tmp_path, monkeypatch):
    source = _input(tmp_path, "missing.gjf")
    _install_fake_dispatch(monkeypatch, writer=None)
    work = tmp_path / "missing_work"
    with pytest.raises(RuntimeError, match="缺少或为空"):
        run_jobs(
            [source],
            str(work),
            "machine",
            "resources",
            program="gaussian",
        )
    assert (work / "pop0").exists()

    def wrong_writer(task_dir, task):
        (task_dir / "wrong.log").write_text(
            "* O   R   C   A *\nFINAL SINGLE POINT ENERGY -1.0\n"
            "ORCA TERMINATED NORMALLY\n"
        )

    wrong = _input(tmp_path, "wrong.gjf")
    _install_fake_dispatch(monkeypatch, wrong_writer)
    with pytest.raises(RuntimeError, match="程序不匹配"):
        run_jobs(
            [wrong],
            str(tmp_path / "wrong_work"),
            "machine",
            "resources",
            program="gaussian",
        )


def test_run_jobs_empty_output_and_remote_cleanup_without_validation(tmp_path, monkeypatch):
    def empty_writer(task_dir, task):
        (task_dir / "empty.log").write_text("")

    empty = _input(tmp_path, "empty.gjf")
    _install_fake_dispatch(monkeypatch, empty_writer)
    with pytest.raises(RuntimeError, match="为空"):
        run_jobs(
            [empty],
            str(tmp_path / "empty_work"),
            "machine",
            "resources",
            program="gaussian",
        )

    def arbitrary_writer(task_dir, task):
        (task_dir / "ok.log").write_text("not a QM output\n")

    source = _input(tmp_path, "ok.gjf")
    _install_fake_dispatch(monkeypatch, arbitrary_writer, parent="data/")
    work = tmp_path / "remote_work"
    outputs = run_jobs(
        [source],
        str(work),
        "machine",
        "resources",
        program="gaussian",
        validate_outputs=False,
    )
    assert Path(outputs["ok"]).read_text() == "not a QM output\n"
    assert not (work / "data").exists()


def test_run_jobs_cleanup_false_preserves_task_dir(tmp_path, monkeypatch):
    def gaussian_writer(task_dir, task):
        (task_dir / "keep.log").write_text(
            "Entering Gaussian System\nSCF Done: E(RHF) = -1.0 A.U.\n"
            "Normal termination of Gaussian 16\n"
        )

    source = _input(tmp_path, "keep.gjf")
    _install_fake_dispatch(monkeypatch, gaussian_writer)
    work = tmp_path / "keep_work"
    outputs = run_jobs(
        [source],
        str(work),
        "machine",
        "resources",
        program="gaussian",
        cleanup=False,
        max_retries=0,
    )
    assert "keep" in outputs and (work / "pop0").exists()
    assert _FakeSubmission.last_machine.retry_count == 0

    with pytest.raises(ValueError, match="max_retries"):
        run_jobs(
            [source],
            str(tmp_path / "invalid_retry"),
            "machine",
            "resources",
            program="gaussian",
            max_retries=-1,
        )
