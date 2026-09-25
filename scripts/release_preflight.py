#!/usr/bin/env python3
"""Verify the ion_HOF release locks without submitting any scientific job."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "delivery" / "release-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(paths: list[str]) -> tuple[str, int]:
    files: set[Path] = set()
    for pattern in paths:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(f"{sha256(path)}  {relative}\n".encode())
    return digest.hexdigest(), len(files)


def add_check(report: dict[str, Any], check_id: str, ok: bool, detail: str) -> None:
    report["checks"].append(
        {"id": check_id, "status": "PASS" if ok else "FAIL", "detail": detail}
    )
    report["ok"] = report["ok"] and ok


def validate_common(report: dict[str, Any], manifest: dict[str, Any], profile: str) -> None:
    add_check(report, "manifest.schema", manifest.get("schema_version") == 1, "schema_version=1")
    add_check(report, "manifest.project", manifest.get("project") == "ion_HOF", "project=ion_HOF")
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    add_check(
        report,
        "project.version",
        project_version == manifest.get("version"),
        f"pyproject={project_version}; manifest={manifest.get('version')}",
    )

    tree = manifest["source_revision"]["trees"][profile]
    actual_tree, count = tree_sha256(tree["paths"])
    add_check(
        report,
        f"source.{profile}",
        actual_tree == tree["sha256"] and count == tree["file_count"],
        f"sha256={actual_tree}; files={count}",
    )

    lock_path = ROOT / manifest["profiles"][profile]["lock"]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    add_check(
        report,
        f"lock.{profile}.identity",
        lock.get("project") == "ion_HOF"
        and lock.get("profile") == profile
        and lock.get("version") == manifest.get("version")
        and lock.get("source_tree_sha256") == tree["sha256"],
        f"lock={lock_path}",
    )
    for distribution, expected in lock["validated_environment"].items():
        if distribution == "python":
            actual = platform.python_version()
        else:
            try:
                actual = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                actual = None
        add_check(
            report,
            f"environment.{profile}.{distribution}",
            actual == expected,
            f"actual={actual}; expected={expected}",
        )

    for artifact in manifest["artifacts"]:
        if profile not in artifact["profiles"]:
            continue
        path = ROOT / artifact["path"]
        exists = path.is_file()
        actual_hash = sha256(path) if exists else None
        actual_size = path.stat().st_size if exists else None
        ok = exists and actual_hash == artifact["sha256"] and actual_size == artifact["size_bytes"]
        if artifact["required"]:
            add_check(
                report,
                f"artifact.{artifact['path']}",
                ok,
                f"sha256={actual_hash}; size_bytes={actual_size}",
            )


def validate_core(report: dict[str, Any], manifest: dict[str, Any]) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from bppa_hof import __version__
    from bppa_hof.config import load_config

    add_check(
        report,
        "core.package_version",
        __version__ == manifest["version"],
        f"bppa_hof.__version__={__version__}",
    )
    baseline = manifest["profiles"]["core"]["numerical_baseline"]
    config = load_config(str(ROOT / baseline["config"]))
    result = config.salts[0].compute()
    tolerance = float(baseline["absolute_tolerance"])
    observed = {
        "gas_phase_hof": result.gas_phase_hof,
        "lattice_enthalpy": result.lattice_enthalpy,
        "solid_hof": result.solid_hof,
    }
    for name, expected in baseline["expected"].items():
        actual = observed[name]
        add_check(
            report,
            f"core.baseline.{name}",
            abs(actual - float(expected)) <= tolerance,
            f"actual={actual:.12f}; expected={float(expected):.12f}; atol={tolerance}",
        )


def _resolve_backend(command: str, environment: str | None, fallback: str | None) -> str | None:
    configured = os.environ.get(environment, "") if environment else ""
    candidate = configured or shutil.which(command) or fallback or ""
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return str(path.resolve()) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate)


def validate_dispatch(
    report: dict[str, Any],
    manifest: dict[str, Any],
    machine_path: str | None,
    resources_path: str | None,
    backend_check: str,
) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from bppa_hof.dispatch import get_profile, machine_resources_prep
    from bppa_hof.geometry import Molecule
    from bppa_hof.inputgen import ion_inputs

    if bool(machine_path) != bool(resources_path):
        add_check(report, "dispatch.config_pair", False, "--machine 与 --resources 必须同时提供")
    else:
        machine = machine_path or str(ROOT / "examples/server/local_machine.yaml")
        resources = resources_path or str(ROOT / "examples/server/local_resources.yaml")
        try:
            machine_obj, resources_obj, parent = machine_resources_prep(machine, resources)
            machine_info = machine_obj.serialize()
            resources_info = resources_obj.serialize()
            valid_resources = all(
                isinstance(resources_info.get(key), int) and resources_info[key] >= minimum
                for key, minimum in (("number_node", 1), ("cpu_per_node", 1), ("gpu_per_node", 0))
            )
            valid_context = machine_info.get("context_type") in {"LocalContext", "SSHContext"}
            add_check(
                report,
                "dispatch.machine_resources",
                valid_resources and valid_context,
                f"context={machine_info.get('context_type')}; batch={machine_info.get('batch_type')}; parent={parent}",
            )
        except Exception as exc:
            add_check(report, "dispatch.machine_resources", False, f"{type(exc).__name__}: {exc}")

    molecule = Molecule.from_xyz(str(ROOT / "examples/qm/n5_anion.xyz"), charge=-1, multiplicity=1)
    gaussian = ion_inputs(molecule, program="gaussian")
    orca = ion_inputs(molecule, program="orca", optimized_molecule=molecule)
    gaussian_ok = set(gaussian) == {"energy", "volume"} and all(
        name.endswith(".gjf") and "#p " in text for name, text in gaussian.values()
    )
    orca_ok = set(orca) == {"opt_freq", "sp", "volume"} and (
        "Opt Freq" in orca["opt_freq"][1] and "M062X" in orca["sp"][1]
    )
    add_check(report, "dispatch.input_template.gaussian", gaussian_ok, f"outputs={sorted(gaussian)}")
    add_check(report, "dispatch.input_template.orca", orca_ok, f"outputs={sorted(orca)}")

    for program in ("gaussian", "orca"):
        profile = get_profile(program)
        script = ROOT / "src/bppa_hof/scripts" / profile.script
        add_check(
            report,
            f"dispatch.script.{program}",
            script.is_file() and script.read_text(encoding="utf-8").startswith("#!/bin/bash"),
            str(script),
        )

    requested = [] if backend_check == "none" else (
        ["gaussian", "orca"] if backend_check == "all" else [backend_check]
    )
    for name in requested:
        backend = manifest["profiles"]["dispatch"]["backends"][name]
        resolved = _resolve_backend(
            backend["command"], backend.get("environment"), backend.get("fallback")
        )
        add_check(
            report,
            f"dispatch.backend.{name}",
            resolved is not None,
            f"resolved={resolved}; environment={backend.get('environment')}",
        )


def run(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "project": "ion_HOF",
        "version": manifest.get("version"),
        "profile": args.profile,
        "manifest": str(manifest_path),
        "ok": True,
        "checks": [],
    }
    profiles = ["core", "dispatch"] if args.profile == "all" else [args.profile]
    for profile in profiles:
        validate_common(report, manifest, profile)
        if profile == "core":
            validate_core(report, manifest)
        else:
            validate_dispatch(report, manifest, args.machine, args.resources, args.backend_check)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify ion_HOF release locks without submitting jobs")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--profile", choices=("core", "dispatch", "all"), default="all")
    parser.add_argument("--machine", help="Optional dpdispatcher machine YAML/JSON to validate")
    parser.add_argument("--resources", help="Optional dpdispatcher resources YAML/JSON to validate")
    parser.add_argument(
        "--backend-check",
        choices=("none", "gaussian", "orca", "all"),
        default="none",
        help="Require selected executable(s) on this compute host; never submits a job",
    )
    parser.add_argument("--json", action="store_true", help="Emit one machine-readable JSON document")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args)
    except Exception as exc:
        report = {
            "project": "ion_HOF",
            "profile": args.profile,
            "ok": False,
            "checks": [
                {"id": "preflight.internal", "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}
            ],
        }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for check in report["checks"]:
            print(f"[{check['status']}] {check['id']}: {check['detail']}")
        print("PASS" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
