.. _installation:

Installation
=============

#. Clone the repository from GitHub

   .. code-block:: bash

      git clone --recurse-submodules git@github.com:CROCODILE-CESM/CrocoDash.git

#. Create the environment (called CrocoDash by default) using the provided environment.yml file

   .. code-block:: bash

      conda env create -f environment.yml # Use Mamba if you have it installed! It's faster.

#. Activate the environment! 

   .. code-block:: bash

      conda activate CrocoDash
      pytest tests/test_installation.py # If you'd like, run this to see if the package is installed correctly

#. Check out the demos!

   .. code-block:: python

      import CrocoDash as cd