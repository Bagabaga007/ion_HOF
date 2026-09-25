import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.config
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_preflight.py"


def _run(*arguments, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments, "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_release_manifest_has_independent_core_and_dispatch_locks():
    manifest = json.loads((ROOT / "delivery/release-manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["project"] == "ion_HOF"
    assert manifest["release_status"] in {"candidate_uncommitted", "frozen"}
    if manifest["release_status"] == "frozen":
        assert manifest["source_revision"]["dirty"] is False
    assert set(manifest["profiles"]) == {"core", "dispatch"}
    for name in ("core", "dispatch"):
        lock = ROOT / manifest["profiles"][name]["lock"]
        payload = json.loads(lock.read_text())
        assert payload["profile"] == name
        assert payload["version"] == manifest["version"]


@pytest.mark.parametrize("profile", ["core", "dispatch"])
def test_release_preflight_profile_passes(profile):
    completed = _run("--profile", profile)
    payload = json.loads(completed.stdout)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert payload["ok"] is True
    assert all(check["status"] == "PASS" for check in payload["checks"])


def test_release_preflight_backend_visibility_is_strict_when_requested():
    env = os.environ.copy()
    env["G16_EXE"] = str(ROOT / "does-not-exist" / "g16")
    completed = _run("--profile", "dispatch", "--backend-check", "gaussian", env=env)
    payload = json.loads(completed.stdout)
    failed = {check["id"] for check in payload["checks"] if check["status"] == "FAIL"}
    assert completed.returncode == 1
    assert failed == {"dispatch.backend.gaussian"}


def test_release_preflight_rejects_unpaired_dispatch_config():
    completed = _run(
        "--profile",
        "dispatch",
        "--machine",
        str(ROOT / "examples/server/local_machine.yaml"),
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert any(
        check["id"] == "dispatch.config_pair" and check["status"] == "FAIL"
        for check in payload["checks"]
    )


def test_release_preflight_rejects_lock_source_drift(tmp_path):
    manifest = json.loads((ROOT / "delivery/release-manifest.json").read_text())
    manifest["source_revision"]["trees"]["core"]["sha256"] = "0" * 64
    changed = tmp_path / "release-manifest.json"
    changed.write_text(json.dumps(manifest), encoding="utf-8")
    completed = _run("--profile", "core", "--manifest", str(changed))
    payload = json.loads(completed.stdout)
    failed = {check["id"] for check in payload["checks"] if check["status"] == "FAIL"}
    assert completed.returncode == 1
    assert {"source.core", "lock.core.identity"} <= failed
