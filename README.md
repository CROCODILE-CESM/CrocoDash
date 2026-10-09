# CrocoDash

CrocoDash is a Python package designed to setup regional Modular Ocean Model 6 (MOM6) cases within the Community Earth System Model (CESM).
CrocoDash takes advantage and integrates several MOM6 and CESM tools into an unified workflow for regional MOM6 case configuration.
CrocoDash is part of the CROCODILE project. Please see the [project description](https://github.com/CROCODILE-CESM) for scientific motivation.

Full documentation: [https://crocodile-cesm.github.io/CrocoDash/](https://crocodile-cesm.github.io/CrocoDash/)

## Tested configurations

Each week, cases built by CrocoDash `main` run MOM_interface's regional smoke tests on Derecho, against the `crocodash` branch of [CROCODILE-CESM/CESM](https://github.com/CROCODILE-CESM/CESM) (see [crocontainer's `cesm_tests`](https://github.com/CROCODILE-CESM/crocontainer/tree/main/cesm_tests)):

| Compset | Components | SMS_D_Ld2 |
|---|---|---|
| `CR_JRA_GLOFAS` | MOM6 + GLOFAS runoff | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.CR_JRA_GLOFAS.json) |
| `CR1850MARBL_JRA_GLOFAS` | + MARBL | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.CR1850MARBL_JRA_GLOFAS.json) |
| `GR_JRA_GLOFAS` | + CICE | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.GR_JRA_GLOFAS.json) |
| `CWR_JRA_GLOFAS` | + WW3 | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.CWR_JRA_GLOFAS.json) |
| `GWR1850MARBL_JRA_GLOFAS` | MOM6 + CICE + WW3 + MARBL + GLOFAS | ![](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/CROCODILE-CESM/crocontainer/test-results/SMS_D_Ld2.GWR1850MARBL_JRA_GLOFAS.json) |

## Description

CrocoDash brings regional MOM6 inside CESM. It's a lightweight package that
orchestrates four steps, one module per step:

1. **Grids** — horizontal grid, bathymetry, and vertical grid (via [mom6_forge](https://github.com/NCAR/mom6_forge))
2. **Case setup** — create a CESM regional MOM6 case (via [VisualCaseGen](https://github.com/ESMCI/visualCaseGen))
3. **Configure forcings** — declare tides, BGC, rivers, ICs, etc. for your case
4. **Process forcings** — download, regrid, and format the actual data (via [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6))

CrocoDash also ships helpers like an interactive `TopoEditor` for bathymetry
editing and a `raw_data_access` registry for downloading public datasets.

## Quick install

1. Clone *with* the submodules:
   `git clone --recurse-submodules https://github.com/CROCODILE-CESM/CrocoDash.git -b v1.0.0`
2. Create the environment (this fails if the submodules aren't cloned):
   `conda env create -f environment.yml --yes`
3. Activate the environment:
   `conda activate CrocoDash`
4. Test the installation:
   `pytest tests/test_installation.py`

CrocoDash also needs a CESM install. See the [installation](https://crocodile-cesm.github.io/CrocoDash/latest/installation.html) page for the full steps.

## Get started

1. Walk through the [tutorials](https://crocodile-cesm.github.io/CrocoGallery/latest/crocodash/tutorial-ocn) for an easy introduction.
2. Browse the [gallery of demos](https://crocodile-cesm.github.io/CrocoGallery/latest/) for more use cases.
3. Read the [user guide](https://crocodile-cesm.github.io/CrocoDash/latest/for_users/index.html) for step-by-step docs.

## License

CrocoDash is released under the [Apache 2.0 License](https://github.com/CROCODILE-CESM/CrocoDash/blob/main/LICENSE.md).

## Citation

If you use CrocoDash in your research, please cite it! A `CITATION.cff` file is included in the repository. You can also cite it directly from GitHub using the "Cite this repository" button on the [CrocoDash GitHub page](https://github.com/CROCODILE-CESM/CrocoDash).
