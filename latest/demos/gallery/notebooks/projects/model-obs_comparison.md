# Model-Observations Comparison

These tutorials and projects all use [CrocoCamp](https://github.com/CROCODILE-CESM/CrocoCamp/tree/2025-Crocodile-Workshop), and are expected to run on NCAR's Casper machine. If you want to run them outside of Casper, see [below](#CrocoCamp-outside-of-Casper).

## Installing CrocoCamp

To install CrocoCamp, open a terminal session and run

```
git clone https://github.com/CROCODILE-CESM/CrocoCamp.git --branch 2025-Crocodile-Workshop --single-branch
cd CrocoCamp
./install.sh
conda activate crococamp-2025
```

Note that the [CrocoLake's project](tutorial3_CrocoLake_map_temperature.ipynb) does not *need* CrocoCamp: CrocoLake is a dataset, not a python package, and installing dask, cartopy, and matplotlib is sufficient to read it and make maps. However, CrocoCamp comes with those packages, so if you have installed it already during the workshop, you can directly use the `crococamp-2025` environment to run CrocoLake's project too.

## CrocoCamp outside of Casper

CrocoCamp uses DART under the hood, and for this workshop we have set up a DART executable on Casper. If you need to run CrocoCamp outside of Casper, you basically need to compile DART on the machine where you want to run it.

#### On Derecho

Make sure the following modules are loaded (use `module load` to load them):
* ncarenv
* craype
* intel
* ncarcompilers
* cray-mpich
* hdf5
* netcdf

Build DART (I suggest in the work folder):
```
cd $WORK/
git clone https://github.com/CROCODILE-CESM/DART.git DART-derecho
cd DART-derecho
cd build_templates
cp mkmf.template.intel.linux mkmf.template
cd ../models/MOM6/work
./quickbuild.sh
```

<https://github.com/CROCODILE-CESM/DART.git> contains the latest developments made in the CROCODILE framework. They will be merged in the [official DART](https://github.com/NCAR/DART) when relevant.

You can now set up your config.yaml files to point to the correct path, replacing:
```
perfect_model_obs_dir: /path/to/DART/models/MOM6/work/
```
with
```
perfect_model_obs_dir: $WORK/DART-derecho/models/MOM6/work/
```
or the path you chose.

#### On your machine

Installing DART differs from machine to machine and we refer you to DART's installation guide.

Once you installed DART succesfully, you can set `perfect_model_obs_dir` in your config file to point to `models/MOM6/work/` from the DART root directory. 
