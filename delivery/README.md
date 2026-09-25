# ion_HOF release locks

`release-manifest.json` deliberately separates two acceptance profiles:

- `core`: package/version integrity plus the offline H5N7 numerical recomputation;
- `dispatch`: source/templates, dpdispatcher machine/resources parsing, Gaussian/ORCA
  input generation, packaged runner scripts, and optional compute-host executable
  visibility.

Run without submitting any job:

```bash
python scripts/release_preflight.py --profile core --json
python scripts/release_preflight.py --profile dispatch --json
```

Validate deployment-specific dispatcher files:

```bash
python scripts/release_preflight.py --profile dispatch \
  --machine /path/to/machine.yaml --resources /path/to/resources.yaml --json
```

On an actual compute host, require executable visibility explicitly:

```bash
python scripts/release_preflight.py --profile dispatch --backend-check gaussian --json
python scripts/release_preflight.py --profile dispatch --backend-check orca --json
```

Executable visibility is opt-in because Gaussian/ORCA normally live on the remote
worker selected by dpdispatcher, not necessarily on the orchestration host. Every
failed required check produces exit status 1. The preflight never submits work.

The frozen manifest records the tested source commit. It is committed separately
from that source snapshot so the manifest does not need to contain its own Git hash.
The release tag points to the manifest commit.
