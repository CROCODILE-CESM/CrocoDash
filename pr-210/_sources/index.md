# Welcome to the CrocoDash Documentation!

CrocoDash is a Python package designed to setup regional Modular Ocean Model 6 (MOM6) cases within the Community Earth System Model (CESM).
CrocoDash takes advantage and integrates several MOM6 and CESM tools into an unified workflow for regional MOM6 case configuration.
CrocoDash is part of the CROCODILE project. Please see the [project description](https://github.com/CROCODILE-CESM) for scientific motivation.

## Description

CrocoDash brings regional MOM6 inside the CESM. It is a lightweight package that ties together each part of the MOM6 in CESM setup process into one package.

1. Grid Generation (Through [mom6_bathy](https://github.com/NCAR/mom6_bathy) and [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6))
2. CESM Setup (Through [VisualCaseGen](https://github.com/CROCODILE-CESM/VisualCaseGen))
3. Forcing + OBC Setup (Through [CESM](https://github.com/CROCODILE-CESM/CESM) & [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6))

CrocoDash also provides a variety of helper tools to help setup a case, for example, a tool to edit bathymetry (TopoEditor) or a tool to download public datasets simply (raw_data_access module).

## Get Started

1. Please see the {ref}`installation` page.
2. Walk through our [tutorials](https://crocodile-cesm.github.io/CrocoGallery/latest/notebooks/tutorials/crocodash-tutorial/) for an easy introduction
3. Check out our [gallery of demos](https://crocodile-cesm.github.io/CrocoGallery/latest/) for more use cases and cool features.

```{toctree}
:caption: 'Contents:'
:maxdepth: 1


installation
Tutorials & Gallery <https://crocodile-cesm.github.io/CrocoGallery/>
for_users/index
for_developers/index
api-docs/modules
Common Errors <https://github.com/CROCODILE-CESM/CrocoDash/discussions/84>
```
