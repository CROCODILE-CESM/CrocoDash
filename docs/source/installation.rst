.. _my-reference-label:installation

Installation
=============

#. Clone the repository from GitHub

   .. code-block:: bash

      git clone git@github.com:CROCODILE-CESM/CrocoDash.git --recurse-submodules

#. Create the environment (called CrocoDash by default) using the provided environment.yml file

   .. code-block:: bash

      conda env create -f environment.yml # Use Mamba if you have it installed! It's faster.

#. Activate the environment! 

   .. code-block:: bash

      conda activate CrocoDash
      pytest   # If you'd like, run this to see if everything is working as expected. These are not comprehensive tests.

#. Check out the demos!

   .. code-block:: python

      import CrocoDash as cd