(installation)=

# Installation

To use CrocoDash, we need to install both the CESM and CrocoDash! See the steps below.

## CESM Installation

The first step in running an ocean model inside the CESM is setting up the CESM! Here's how to do it:

1. Clone the CESM Repo

   CROCODILE has its own fork of the CESM available here: <https://github.com/CROCODILE-CESM/CESM>. Go ahead and clone it as shown below. I'm gonna call mine CROCESM.

   ```bash
   git clone https://github.com/CROCODILE-CESM/CESM CROCESM -b workshop_2025
   ```

2. Checkout all the components

   The original clone only clones the CESM code, we need to checkout all of the components as well, like the ocean model and the sea ice model. This will take some time.

   ```bash
   cd CROCESM
   ./bin/git-fleximod update
   ```

## CrocoDash Installation

1. Clone the repository from GitHub

   ```bash
   git clone --recurse-submodules https://github.com/CROCODILE-CESM/CrocoDash.git -b v0.1.0-beta
   ```

2. Create the environment (called CrocoDash by default) using the provided environment.yml file

   ```bash
   conda env create -f environment.yml --yes # Use Mamba if you have it installed! It's faster.
   ```

3. Activate the environment!

   ```bash
   conda activate CrocoDash
   pytest tests/test_installation.py # If you'd like, run this to see if the package is installed correctly
   ```

4. Check out the demos in the CrocoGallery!

   ```python
   import CrocoDash as cd
   ```
