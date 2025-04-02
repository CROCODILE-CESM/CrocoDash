# CrocoDash

CrocoDash is a Python package designed to setup regional Modular Ocean Model 6 (MOM6) cases within the Community Earth System Model (CESM). CrocoDash takes advantage and integrates several MOM6 and CESM tools into an unified workflow for regional MOM6 case configuration.

## Installation: 

Installation:
1. The first step is cloning *WITH* the submodules:
`git clone --recurse-submodules git@github.com:CROCODILE-CESM/CrocoDash.git`
2. Install the environment (which we fail if the submodules aren't installed):
`mamba env create -f environment.yml`
3. Activate the environment:
`mamba activate CrocoDash`
4. Test installation with:
`pytest tests/test_installation.py`

## Background
CrocoDash is part of the [CROCODILE project](https://github.com/CROCODILE-CESM/regional-mom6), and spun off of the [regional-mom6 (RM6) package](https://github.com/CROCODILE-CESM/regional-mom6), an independent package that sets up a regional MOM run. CrocoDash wraps RM6 (for OBC construction & some grid generation) to setup a workflow inside the CESM.

## Motivation: 
Please see the overall CROCODILE project for scientific motivation. CrocoDash provides a platform  to combine many MOM6 and CESM tools to create an sum greater than the parts for regional cases.

## Description: 
The framework here is called CrocoDash.CrocoDash brings regional MOM6 inside the CESM. It is a lightweight package that ties together each part of the MOM6 in CESM setup process into one package.
1. Grid Generation (Through [mom6_bathy](https://github.com/NCAR/mom6_bathy) and [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6))
2. CESM Setup (Through [VisualCaseGen](https://github.com/CROCODILE-CESM/VisualCaseGen))
3. Forcing + OBC Setup (Through CESM & [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6))

CrocoDash also provides a variety of helper tools to help setup a case, for example, a tool to edit bathymetry (TopoEditor) or a tool to download public datasets simply (data_access module). 

## Demos:

Going with this flow, there are a few demos to get used to the CrocoDash. 

1. One is called [minimal_demo_rect](demos/minimal_demo_rect.ipynb). It creates a rectangular case from grid generation to CESM case submission. 

2. Another demo is called [minimal_demo_subset_global](demos/minimal_demo_subset_global.ipynb), which is similar to the previous demo with but subsets a global grid instead of generating a rectangular grid. 

3. Another demo showcases the ability to have less than four boundaries in a regional domain. The demo is [minimal_demo_three_boundary](demos/minimal_demo_three_boundary.ipynb).

## Documentation: 

Check out our documentation in the [docs/ folder](docs/), or at the website: [https://crocodile-cesm.github.io/CrocoDash/](https://crocodile-cesm.github.io/CrocoDash/).

