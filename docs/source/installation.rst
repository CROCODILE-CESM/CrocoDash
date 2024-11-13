Installation
=============

#. Clone the repository from GitHub

   .. code-block:: bash

      git clone git@github.com:CROCODILE-CESM/crocodile-regional-ruckus.git

#. Create the environment (called crocodash) using the provided environment.yml file

   .. code-block:: bash

      conda env create -f environment.yml # Use Mamba if you have it installed! It's faster.

#. Activate the environment! 

   .. code-block:: bash

      conda activate crocodash
      pytest   # If you'd like, run this to see if everything is working as expected. These are not comprehensive tests.

#. Check out the demos! Change the path of the sys.path.insert(0,) to the path of the repository on your machine.

   .. code-block:: python

      import sys
      sys.path.insert(0, '/path/to/crocodile_dashboard')
      import crocodile_dashboard as cd