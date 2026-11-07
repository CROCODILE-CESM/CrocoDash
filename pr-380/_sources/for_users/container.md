# Running in a Container

[crocontainer](https://github.com/CROCODILE-CESM/crocontainer) images build and run a
CrocoDash case in CESM on a laptop (Podman or Docker) or on Derecho (Apptainer). There's
no CESM machine port and no batch queue: the case builds and runs where you are, on the
container's own CIME machine, `ubuntu-latest`.

## Images

| `ghcr.io/crocodile-cesm/crocontainer:` | What's inside | Runs on | MPI tasks | Download |
|---|---|---|---|---|
| `latest` | compilers, MPI, netCDF, ESMF, CESM (`crocodash` branch), CrocoDash `main` and its env | x86-64, ARM | 1 | 5.0 GB |
| `latest-intel` | the same, built with Intel's compilers and MPI | x86-64 | as many as you have cores | 6.7 GB |
| `slim` | compilers, MPI, netCDF, ESMF; you bring CESM and a CrocoDash env | x86-64, ARM | 1 | 0.5 GB |
| `slim-intel` | the same, with Intel's compilers and MPI | x86-64 | as many as you have cores | 2.1 GB |

- **`latest` or `slim`:** `latest` has everything and is rebuilt weekly, so it trails the
  newest work. Use `slim` when you keep your own CESM and CrocoDash up to date.
- **gnu or intel:** built with gfortran, MOM6 crashes on more than one MPI task (in
  FMS's grid read). The `intel` images build CESM with Intel's compilers, as on
  Derecho, and run on as many tasks as you give them.

## Mounts

| Container path | What goes there |
|---|---|
| `/root/cesm/inputdata` | CESM's input data (see [Input data](#input-data)) |
| `/root/cesm/scratch` | Where cases build and run. Put `caseroot` and `inputdir` under it too, so they outlast the container |
| `/croc` | `slim` on a laptop: your CESM, CrocoDash and env |

The run directory is `/root/cesm/scratch/<case>/run`; with short-term archiving on, the
output then moves to `/root/cesm/scratch/archive/<case>`.

## Starting a container

### On Derecho (Apptainer)

Build a writable sandbox once (about an hour):

```bash
module load apptainer
qcmd -l select=1:ncpus=8 -l walltime=01:00:00 -- \
  apptainer build --sandbox $SCRATCH/crocontainer docker://ghcr.io/crocodile-cesm/crocontainer:slim-intel
```

Then start it in a PBS job with the cores you want (a login node gives you one), e.g.
`qinteractive -l select=1:ncpus=8`:

```bash
module load apptainer
apptainer shell --writable --bind /glade \
  --bind /glade/campaign/cesm/cesmdata/inputdata:/root/cesm/inputdata \
  --bind $SCRATCH/croc_scratch:/root/cesm/scratch \
  $SCRATCH/crocontainer
```

`--bind /glade` makes everything on `/glade` visible at its usual path: your CESM,
CrocoDash, conda envs, configs and cases. `HOME` is `/root` inside (CIME reads the
container's machine from `~/.cime`). Your own home is at its `/glade` path, so point
tools that want a file in `~` at it there, e.g. `export CDSAPI_RC=/glade/u/home/<you>/.cdsapirc`.

### On a laptop (Podman or Docker)

```bash
podman run --rm -it \
  -v ./inputdata:/root/cesm/inputdata \
  -v ./scratch:/root/cesm/scratch \
  -v ~/croc:/croc \
  ghcr.io/crocodile-cesm/crocontainer:slim bash
```

The `~/croc` mount is only needed for `slim`. On Windows, run Podman inside WSL2. On a
Mac, run `podman machine init && podman machine start` first.

## Running a case

In your [YAML config](cli.md), set the CESM in the container, its machine, and paths under
the scratch mount:

```yaml
case:
  cesmroot: /workspace/CESM      # latest images; with slim, your own CESM
  machine: ubuntu-latest
  caseroot: /root/cesm/scratch/cases/mycase
  inputdir: /root/cesm/scratch/inputdir/mycase
```

CrocoDash wants the parent directories of `caseroot` and `inputdir` to exist, so
`mkdir -p` them first. Then, in the container:

```bash
crocodash create --config my_case.yaml
cd /root/cesm/scratch/cases/mycase
./xmlchange NTASKS=8 && ./case.setup --reset   # intel images only; the default is 1
./case.build
./case.submit
```

On this machine `case.submit` runs the model right away, and it prints `case.submit
success` even when the run fails. Check `CaseStatus` for `case.run success`.

Forcings need their source data. On Derecho, `crocodash create` reads it from GLADE as
usual. Elsewhere, make the case where the data is and bring it in as a
[bundle](#bringing-in-a-case-from-another-machine).

### With a `latest` image

`crocodash` is ready to use, and runs CrocoDash `main` from the image's env (for Python,
`micromamba run -p /opt/conda/envs/CrocoDash python`). To use your own CrocoDash anyway,
mount a checkout over `/workspace/CrocoDash`, which the env has installed in editable
mode; to use your own CESM, point `cesmroot` at it.

`/workspace/run_case.sh` makes a case at `/workspace/case`, builds it and runs it. It uses
a config mounted at `/workspace/case_config.yaml` (with `caseroot: /workspace/case` and
`inputdir: /workspace/inputdir`), or else a built-in Panama demo. `NTASKS` sets the tasks.
With only input data mounted, it's a quick test of the container:

```bash
podman run --rm -e NTASKS=4 \
  -v ./inputdata:/root/cesm/inputdata -v ./scratch:/root/cesm/scratch \
  ghcr.io/crocodile-cesm/crocontainer:latest-intel /workspace/run_case.sh
```

### With a `slim` image

You need a CESM checkout, a CrocoDash checkout, and a conda env with CrocoDash. Set them
up once, keep them outside the container, and mount them in each time.

**1. Get CESM and CrocoDash.** On Derecho, use `/glade/work/$USER/croc` rather than
`~/croc`, since your home is small.

```bash
git clone -b crocodash https://github.com/CROCODILE-CESM/CESM ~/croc/CESM
(cd ~/croc/CESM && ./bin/git-fleximod update)
git clone --recurse-submodules https://github.com/CROCODILE-CESM/CrocoDash ~/croc/CrocoDash
```

Any CESM on the `crocodash` branch works, or one compatible with the container's ESMF
8.9.1.

**2. Make the env.** On Derecho, on the host as usual; a Derecho env runs in the container
as it is:

```bash
module load conda
cd /glade/work/$USER/croc/CrocoDash
conda env create -p /glade/work/$USER/croc/env -f environment.yml
```

On a laptop, an env from macOS or Windows won't run in the (Linux) container, so make it
inside the container, into the mount:

```bash
cd /croc/CrocoDash && micromamba create -y -p /croc/env -f environment.yml
```

An env can't move, so always mount `~/croc` at `/croc`.

**3. Activate it in the container,** with the container's `micromamba` and the env's full
path (`~` is `/root` inside):

```bash
eval "$(micromamba shell hook -s bash)"
micromamba activate /glade/work/<you>/croc/env   # Derecho
micromamba activate /croc/env                    # laptop
```

Set `cesmroot` to your CESM (`/croc/CESM` on a laptop) and run the case as above. The env
can stay active for `case.build`, which uses the container's compilers whatever is on your
`PATH`.

## Input data

On Derecho, mount `/glade/campaign/cesm/cesmdata/inputdata` as above. Elsewhere,
crocontainer's
[`download_nyf_inputdata.sh`](https://github.com/CROCODILE-CESM/crocontainer/blob/main/scripts/download_nyf_inputdata.sh)
fetches what a normal-year-forcing (`DATM%NYF`) case needs, about 6.5 GB:

```bash
bash scripts/download_nyf_inputdata.sh ./inputdata          # from the CESM data server
bash scripts/download_nyf_inputdata.sh ./inputdata --from-glade <you>@derecho.hpc.ucar.edu
```

It resumes where it stopped, and uses `aria2c` when it's installed.

## Bringing in a case from another machine

A [bundle](shareable.md) carries a case's config, your changes to it, and its processed
forcings, so the case needs no data access in the container. Make it where the case is:

```bash
crocodash bundle --caseroot ~/croc_cases/mycase --output-dir ~/bundles
```

Then recreate it on the container's machine:

```bash
crocodash fork --bundle ~/bundles/mycase_case_bundle \
  --caseroot /root/cesm/scratch/cases/mycase --inputdir /root/cesm/scratch/inputdir/mycase \
  --cesmroot /workspace/CESM --machine ubuntu-latest --project none \
  --plan '{"xml_files": true, "user_nl": true, "source_mods": true, "xmlchanges": false}'
```

`"xmlchanges": false` leaves out `xmlchange`s made for the original machine, such as its
PE layout.

## Gotchas

- **`INPUTDIR` longer than 128 characters:** MOM6 truncates it, then can't open the OBC
  files. Keep `inputdir` paths short.
- **Files in your home on Derecho:** inside, `~` is `/root`; use the `/glade` path.
- **More than one task with `slim` or `latest`:** MOM6 crashes; use an `intel` image.

For how the images are built and tested, see crocontainer's
[`DEVELOPING.md`](https://github.com/CROCODILE-CESM/crocontainer/blob/main/DEVELOPING.md).
