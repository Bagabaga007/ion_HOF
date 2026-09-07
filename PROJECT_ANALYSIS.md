# ion_HOF project analysis

Generated for the HEMERA architecture review on 2026-09-03. This file is a project-level summary;
the HEMERA aggregate view is [HEMERA/BPPA/ion_HOF_ANALYSIS.md](/workplace/home/yangze/HEMERA/BPPA/ion_HOF_ANALYSIS.md).

## Identity and scope

- Distribution/CLI: `ion_HOF 0.1.0`; Python >=3.9, src-layout under `src/bppa_hof`.
- The `bppa_hof` import namespace is retained for Python API compatibility; the user-facing project and command name is `ion_HOF`.
- Scope: gas-phase atomization enthalpy, VBT lattice enthalpy, Ion/Salt models, Gaussian/ORCA input/output,
  dpdispatcher submission, CLI batch/report/parse/gen-input/submit and staged ORCA thermochemistry.
- Operable examples: `examples/h5n7/run_demo.py` for the offline H5N7 recalculation and
  `examples/qm/` for generating real Gaussian/ORCA input files; the complete procedure is in
  `docs/usage.md`.
- GitHub: <https://github.com/Bagabaga007/ion_HOF>, branch `main`; the current verified SHA is
  maintained in the HEMERA `system.json` manifest to avoid stale self-references in this report.
- External programs: Gaussian 16, ORCA, dpdispatcher and remote scheduler/SSH resources.

## Verification snapshot

- 81 pytest tests across unit/integration/config/system.
- 970/970 Python statements and 274/274 branches covered.
- Ruff, Python compileall, shell syntax, sdist/wheel build and isolated wheel runtime pass.
- Real JLU184: Gaussian 16 job 267589; ORCA 6.1 jobs 267593/267594; evidence is in
  `/workplace/home/yangze/archive/HEMERA_rebuild_work/20260903`.

## Scientific boundary

VBT alpha/beta defaults are only validated for I=1, 1:1 salts. M2X/multivalent extrapolation is rejected
unless explicitly enabled for diagnostics. Public 21-salt validation showed about 205.84 kJ/mol MX lattice
enthalpy MAE, so this is a reliable execution pipeline and narrow research tool, not a universal predictor.

## Maintenance

Keep QM outputs, credentials and scheduler configuration external to source control. Keep failed task
directories for diagnosis. Any change to parsers or thermochemistry must update normal-termination,
cross-method and independent-recomputation tests.
