(installation)=

# Installation

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

4. Check out the demos!

   ```python
   import CrocoDash as cd
   ```
