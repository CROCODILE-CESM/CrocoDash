# Welcome to the CrocoDash Documentation!

CrocoDash is a Python package designed to setup regional Modular Ocean Model 6 (MOM6) cases within the Community Earth System Model (CESM).
CrocoDash takes advantage and integrates several MOM6 and CESM tools into an unified workflow for regional MOM6 case configuration.
CrocoDash is part of the CROCODILE project. Please see the [project description](https://github.com/CROCODILE-CESM) for scientific motivation.

## Description

CrocoDash brings regional MOM6 inside CESM. It's a lightweight package that
orchestrates four steps, one module per step:

1. **Grids** — horizontal grid, bathymetry, and vertical grid (via [mom6_forge](https://github.com/NCAR/mom6_forge))
2. **Case setup** — create a CESM regional MOM6 case (via [VisualCaseGen](https://github.com/CROCODILE-CESM/VisualCaseGen))
3. **Configure forcings** — declare tides, BGC, rivers, ICs, etc. for your case
4. **Process forcings** — download, regrid, and format the actual data (via [regional-mom6](https://github.com/CROCODILE-CESM/regional-mom6))

CrocoDash also ships helpers like an interactive `TopoEditor` for bathymetry
editing and a `raw_data_access` registry for downloading public datasets.

## Get started

1. Install — see the [installation](installation.md) page.
2. Walk through the [tutorials](https://crocodile-cesm.github.io/CrocoGallery/latest/notebooks/tutorials/crocodash-tutorial/) for an easy introduction.
3. Browse the [gallery of demos](https://crocodile-cesm.github.io/CrocoGallery/latest/) for more use cases.
4. Read the [user guide](for_users/index.md) for step-by-step docs.

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

## License

CrocoDash is released under the [Apache 2.0 License](https://github.com/CROCODILE-CESM/CrocoDash/blob/main/LICENSE).

## Citation

If you use CrocoDash in your research, please cite it! A `CITATION.cff` file is included in the repository. You can also cite it directly from GitHub using the "Cite this repository" button on the [CrocoDash GitHub page](https://github.com/CROCODILE-CESM/CrocoDash).