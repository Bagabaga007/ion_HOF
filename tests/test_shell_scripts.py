"""QM 批处理脚本的环境加载和失败传播回归测试。"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

import bppa_hof

pytestmark = pytest.mark.integration


def _script(name: str) -> Path:
    return Path(bppa_hof.__file__).parent / "scripts" / name


def _executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_gaussian_environment_can_reference_unset_variable(tmp_path):
    shutil.copyfile(_script("g16_sub.sh"), tmp_path / "g16_sub.sh")
    (tmp_path / "h.gjf").write_text("input")
    env_script = tmp_path / "g16_env.sh"
    env_script.write_text("export LD_LIBRARY64_PATH=/vendor:${LD_LIBRARY64_PATH}\n")
    executable = tmp_path / "g16"
    _executable(
        executable,
        "#!/bin/bash\nbase=$(basename \"${1%.*}\")\n"
        "echo 'Normal termination of Gaussian 16' > \"${base}.log\"\n",
    )
    env = os.environ.copy()
    env.pop("LD_LIBRARY64_PATH", None)
    env.update(G16_ENV=str(env_script), G16_EXE=str(executable))
    result = subprocess.run(
        ["bash", "g16_sub.sh"], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_orca_environment_can_reference_unset_variable(tmp_path):
    shutil.copyfile(_script("orca_sub.sh"), tmp_path / "orca_sub.sh")
    (tmp_path / "h.inp").write_text("input")
    env_script = tmp_path / "orca_env.sh"
    env_script.write_text("export ORCA_VENDOR_PATH=/vendor:${ORCA_VENDOR_PATH}\n")
    executable = tmp_path / "orca"
    _executable(executable, "#!/bin/bash\necho 'ORCA TERMINATED NORMALLY'\n")
    env = os.environ.copy()
    env.pop("ORCA_VENDOR_PATH", None)
    env.update(ORCA_ENV=str(env_script), ORCA_EXE=str(executable))
    result = subprocess.run(
        ["bash", "orca_sub.sh"], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
