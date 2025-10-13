# CrocoDash

Please check out our documentation at the website: [https://crocodile-cesm.github.io/CrocoDash/](https://crocodile-cesm.github.io/CrocoDash/).

## Installation: 

Installation:
1. The first step is cloning *WITH* the submodules:
`git clone --recurse-submodules git@github.com:CROCODILE-CESM/CrocoDash.git -b v0.1.0-beta`
2. Install the environment (which we fail if the submodules aren't installed):
`mamba env create -f environment.yml`
3. Activate the environment:
`mamba activate CrocoDash`
4. Test installation with:
`pytest tests/test_installation.py`


