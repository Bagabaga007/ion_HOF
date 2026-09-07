"""配置加载与 CLI 集成测试, 使用 examples/h5n7/config.toml。"""

import os
from pathlib import Path

import pytest

from bppa_hof.cli import build_parser, main
from bppa_hof.config import load_config

pytestmark = pytest.mark.config

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "..", "examples", "h5n7", "config.toml"
)


def test_load_example_config():
    cfg = load_config(EXAMPLE)
    assert cfg.method == "G4"
    assert len(cfg.salts) == 1
    assert cfg.references["1a+1c"] == pytest.approx(103.70)


def test_operable_example_contract():
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs/usage.md").is_file()
    assert (root / "examples/h5n7/README.md").is_file()
    assert (root / "examples/h5n7/run_demo.py").is_file()
    assert (root / "examples/qm/n5_anion.xyz").read_text().splitlines()[0] == "5"
    assert "ion_HOF batch examples/h5n7/config.toml" in (root / "docs/usage.md").read_text()


def test_public_project_name_is_ion_hof():
    """用户可见的发行版和 CLI 名称必须与 HEMERA 组件名一致。"""
    assert build_parser().prog == "ion_HOF"


def test_example_config_reproduces_solid_hof():
    cfg = load_config(EXAMPLE)
    result = cfg.salts[0].compute()
    assert result.solid_hof == pytest.approx(102.58, abs=0.6)


def test_cli_batch_runs(capsys):
    rc = main(["batch", EXAMPLE])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1a+1c" in out
    assert "G4" in out


def test_cli_report_runs(capsys):
    rc = main(["report", EXAMPLE])
    assert rc == 0
    out = capsys.readouterr().out
    assert "MAE" in out
