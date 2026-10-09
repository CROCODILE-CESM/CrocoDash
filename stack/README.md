# Shared stack environment

One locked environment for CrocoDash, model2obs, pyDARTdiags and dartobsgen.
CrocoDash maintains it because it carries the tightest constraints (ESMF,
xesmf, Python version, mom6_forge's dask pin).

| File | What it is |
|---|---|
| `environment.yml` | Third-party dependencies of all four packages, with the bounds that actually bind. Edit this. |
| `conda-lock.yml` | Fully solved lock for linux-64 and osx-arm64. Generated, never hand-edited. |
| `install_packages.sh` | Installs the four packages editable with `--no-deps` on top of the lock. |

The split: each package's own `pyproject.toml` says what it *can* run with
(loose ranges); this lockfile says what the stack *does* run with (exact).

## Using it

```bash
# once: conda install -c conda-forge conda-lock   (or use micromamba directly)
conda-lock install -n croc-stack stack/conda-lock.yml
#   or: micromamba create -n croc-stack -f stack/conda-lock.yml
conda activate croc-stack
stack/install_packages.sh ~/path/with/model2obs/pyDARTdiags/dartobsgen
pip check
```

`install_packages.sh` installs CrocoDash and its submodules from this
checkout, then any of `model2obs`, `pyDARTdiags`, `dartobsgen` found in the
given directory (default: the directory containing this CrocoDash checkout).

ESMF's build is left to the solver, so the lock can carry an MPI build and
users can run regridding in parallel. Only the CI test job swaps in the
serial (`nompi_*`) build of the same version, because MPI aborts on GitHub
runners.

## CI (`.github/workflows/stack.yml`)

- **Push touching `stack/`** — tests the committed lock against every package.
- **Weekly (Mon 06:00 UTC), or dispatch with `relock`** — re-solves
  `environment.yml`, runs every package's tests and `pip check` against the
  new lock, and opens a PR (`stack/relock`) only if all of it passes.

The four test suites run as separate jobs, so a red result names the package.
`pip check` runs on its own and fails when a package declares a range that
excludes a locked version (e.g. a stale `<=` cap).

## Changing a dependency

1. A package needs a new dependency or a different range: change its
   `pyproject.toml` *and* this `environment.yml` (copy the bound only if it
   binds; note the source in a comment).
2. Regenerate: `conda-lock lock --micromamba -f stack/environment.yml --lockfile stack/conda-lock.yml`
3. Commit both files; the push runs the stack CI.

## Testing against the stack from another repo

Add a job to model2obs / pyDARTdiags / dartobsgen CI so a change that breaks
the shared stack is caught in that repo's PR:

```yaml
  stack:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: curl -fsSL -o croc-stack-lock.yml https://raw.githubusercontent.com/CROCODILE-CESM/CrocoDash/main/stack/conda-lock.yml
      - uses: mamba-org/setup-micromamba@v2
        with:
          environment-name: croc-stack
          environment-file: croc-stack-lock.yml
          cache-environment: true
      - shell: bash -el {0}
        run: |
          pip install --no-deps -e .
          pytest
```
