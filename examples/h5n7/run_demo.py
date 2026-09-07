"""Run the deterministic, no-QM H5N7 enthalpy example.

Usage from the repository root after ``pip install -e .``::

    python examples/h5n7/run_demo.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bppa_hof.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline ion_HOF H5N7 example")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.toml")),
        help="TOML configuration (default: this directory/config.toml)",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    rows = []
    for salt in config.salts:
        result = salt.compute()
        rows.append(
            {
                "label": salt.label,
                "gas_phase_hof_kcal_mol": result.gas_phase_hof,
                "lattice_enthalpy_kcal_mol": result.lattice_enthalpy,
                "solid_hof_kcal_mol": result.solid_hof,
            }
        )
    print(json.dumps({"method": config.method, "salts": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
