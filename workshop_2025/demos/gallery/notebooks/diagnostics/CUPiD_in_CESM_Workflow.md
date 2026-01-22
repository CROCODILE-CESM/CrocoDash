# Running CUPiD within CESM

CUPiD has been included in the CESM workflow,
which means you can run CUPiD from a CESM case directory with the familiar `case.submit` command.
For this project, we will run the notebooks Aidan put together to analyze a case you ran yourself.

## Background

This notebook originated as a third task in the [CUPiD Diagnostics Tutorial](CUPiD_for_regional_MOM6).
It still uses some of the same structure as the tutorial pages.

### Step 1: Log on to Derecho and Navigate to your CESM case

For the tutorial, we ran CUPiD on NCAR's Casper machine, which is very useful for diagnostics, data analysis, and visualization.
The CESM case that we made in Monday's practicum, **Using CrocoDash**, was set up to run on Derecho.
 CESM is picky about what machine it runs on because it tailors the configuration and run accordingly.
 Even though Derecho and Casper share a file system, they have very different hardware (and provide users with different modules).

You can either log in to Derecho directly from JupyterHub,
or log in to Casper through the JupyterHub and then ssh to Derecho from a terminal.

Once you are on derecho, change into the directory for the case you want to analyze.
The path to this directory might vary, but it will likely be located under the same `crocodile_2025` directory we have been working in so far.

### Step 2: Explore how CUPiD is Incorporated in a CESM Case

As you are likely familiar with at this point,
CESM uses XML files to manage the environment in which your case is run.
Each file contains variables pertaining to a different phase of the case generation process:

```bash
env_archive.xml
env_batch.xml
env_build.xml
env_case.xml
env_mach_pes.xml
env_mach_specific.xml
env_postprocessing.xml
env_run.xml
env_workflow.xml
```

We are interested in the CUPiD variables,
which are all defined in `env_postprocessing.xml`.
XML files are plain-text so we can inspect them directly,
but we'll use CIME's `xmlquery` tool instead.

<div class="alert alert-warning">
🚨 <strong>POP QUIZ!</strong> 🚨

How do you use `xmlquery` to see all the variables that contain `CUPID` in their name (along with their values)?
<details>

<summary>Solution</summary><br>

```
$ ./xmlquery -p CUPID
Results in group cupid_analysis
	CUPID_BASELINE_CASE: b.e23_alpha17f.BLT1850.ne30_t232.092
	CUPID_BASELINE_ROOT: /glade/derecho/scratch/mlevy/archive/CAcurrent.002/..
	CUPID_BASE_NYEARS: 100
	CUPID_BASE_STARTDATE: 0001-01-01
	CUPID_EXAMPLE: key_metrics
	CUPID_NYEARS: 1
	CUPID_STARTDATE: 0001-01-01
	CUPID_TS_DIR: /glade/derecho/scratch/mlevy/archive/CAcurrent.002/..

Results in group cupid_config
	CUPID_GEN_DIAGNOSTICS: TRUE
	CUPID_GEN_HTML: TRUE
	CUPID_GEN_TIMESERIES: TRUE
	CUPID_ROOT: /glade/work/mlevy/codes/CESM/cesm3_0_alpha07c_CROCO/tools/CUPiD

Results in group cupid_environments
	CUPID_ANALYSIS_ENV: cupid-analysis
	CUPID_INFRASTRUCTURE_ENV: cupid-infrastructure

Results in group cupid_run_components
	CUPID_MEM_PER_TASK: 10
	CUPID_NTASKS: 1
	CUPID_RUN_ADF: FALSE
	CUPID_RUN_ALL: TRUE
	CUPID_RUN_ATM: FALSE
	CUPID_RUN_GLC: FALSE
	CUPID_RUN_ICE: FALSE
	CUPID_RUN_LND: FALSE
	CUPID_RUN_OCN: FALSE
	CUPID_RUN_ROF: FALSE
	CUPID_TASKS_PER_NODE: 128
```
</details>
</div>

### Step 3: Configure and Run CUPiD

The first variable to talk about is `CUPID_ROOT`.
CUPiD is distributed with CESM in the `tools/CUPiD` subdirectory,
but you may wish to use a more recent version of CUPiD.
This could be handy if, for example,
you are attending a workshop where you took a CUPiD diagnostic and the first exercises were cloning CUPiD,
installing environments from this clone and then running a few examples.
In that case, you want to run

```bash
./xmlchange CUPID_ROOT=</path/to/CUPiD>
```

We also want to run the `regional_ocean` example,
which is set by the `CUPID_EXAMPLE` variable. 

```bash
./xmlchange CUPID_EXAMPLE=regional_ocean
```

Lastly, we don't need to generate time series files or build a webpage

```bash
./xmlchange CUPID_GEN_TIMESERIES=FALSE,CUPID_GEN_HTML=FALSE
```

When you are ready to run CUPiD, you can tell `case.submit` that you want to run the `case.cupid` job in the workflow.
Make sure you are logged in to Derecho (not Casper) and then run:

```bash
./case.submit --job case.cupid
```

This will add a job to the development queue on derecho,
and it hopefully will start running quickly.
When it finishes, output will be in the `computed_notebooks` subdirectory of your case directory.

## Side Quest: How Does CUPiD Tie in to CESM?

The details look complicated, but it's pretty simple from the user's perspective
(we're going to look at several files to understand what CESM is doing,
but in practice you won't need to modify any of them if you just want to run CUPiD).
The CESM workflow is defined in the [`ccs_config_cesm`](https://github.com/ESMCI/ccs_config_cesm) repository,
and the piece relevant to CUPiD is the [`machines/template.cupid`](https://github.com/ESMCI/ccs_config_cesm/blob/main/machines/template.cupid) file:

```bash
#!/bin/bash -e

# Batch system directives
{{ batchdirectives }}

# Set environment for CESM
source .env_mach_specific.sh

# Run shell script in CUPiD external
CUPID_ROOT=`./xmlquery --value CUPID_ROOT`
(. ${CUPID_ROOT}/helper_scripts/cesm_postprocessing.sh)
```

CIME parses everything in `{{ }}` and replaces it with machine-specific code;
the final file is `case.cupid` in your case directory.
On derecho, this looks like:

```bash
#!/bin/bash -e

# Batch system directives
#PBS -N cupid.{CASE}
#PBS  -r n
#PBS  -j oe
#PBS  -S /bin/bash
#PBS  -l select=1:ncpus=1:mpiprocs=1:ompthreads=1:mem=10GB

# Set environment for CESM
source .env_mach_specific.sh

# Run shell script in CUPiD external
CUPID_ROOT=`./xmlquery --value CUPID_ROOT`
(. ${CUPID_ROOT}/helper_scripts/cesm_postprocessing.sh)
```

In an attempt to keep all necessary code in the CUPiD repository,
you'll note that the last two lines are then calling [`helper_scripts/cesm_postprocessing.sh`](https://github.com/NCAR/CUPiD/blob/main/helper_scripts/cesm_postprocessing.sh) out of `CUPID_ROOT`.
CUPiD's [`helper_scripts/`](https://github.com/NCAR/CUPiD/blob/main/helper_scripts/) directory contains several scripts used to create configuration files,
and `cesm_postprocessing.sh` is the driver that ties everything together.
We won't walk through the entire script here,
but I want to highlight the comments in the script that list the processes:

```bash
# Set variables that come from environment or CESM XML files

# Create directory for running CUPiD
mkdir -p cupid-postprocessing
cd cupid-postprocessing

# Use cupid-infrastructure environment for running these scripts
conda activate ${CUPID_INFRASTRUCTURE_ENV}

# 1. Generate CUPiD config file
${CUPID_ROOT}/helper_scripts/generate_cupid_config_for_cesm_case.py

# 2. Generate ADF config file
if [ "${CUPID_RUN_ADF}" == "TRUE" ]; then

# 3. Generate ILAMB config file
if [ "${CUPID_RUN_ILAMB}" == "TRUE" ]; then

# 4. Generate LDF config file
if [ "${CUPID_RUN_LDF}" == "TRUE" ]; then

# 5. Generate timeseries files
if [ "${CUPID_GEN_TIMESERIES}" == "TRUE" ]; then

# 6. Run ADF
if [ "${CUPID_RUN_ADF}" == "TRUE" ]; then

# 7. Run ILAMB
if [ "${CUPID_RUN_ILAMB}" == "TRUE" ]; then

# 8. Run LDF
if [ "${CUPID_RUN_LDF}" == "TRUE" ]; then

# 9. Run CUPiD and build webpage
conda deactivate
conda activate ${CUPID_INFRASTRUCTURE_ENV}
if [ "${CUPID_GEN_DIAGNOSTICS}" == "TRUE" ]; then
  ${CUPID_ROOT}/cupid/run_diagnostics.py ${CUPID_FLAG_STRING}
fi
if [ "${CUPID_GEN_HTML}" == "TRUE" ]; then
  ${CUPID_ROOT}/cupid/generate_webpage.py
fi
```

You can see how the variables defined in `env_postprocessing.xml` impact what parts of CUPiD are run.
In the next task we will make sure these XML variables are set correctly and then ask CESM to run `case.cupid`.