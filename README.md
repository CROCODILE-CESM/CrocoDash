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


## Documentation: 

Check out our documentation at the website: [https://crocodile-cesm.github.io/CrocoDash/](https://crocodile-cesm.github.io/CrocoDash/).

