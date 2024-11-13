Write Documentation
====================

Steps:

#. Activate the environment
#. Navigate to the docs folder
#. Run the following command:

   .. code-block:: bash

      make html
#. To rekickstart the autodocs

    .. code-block:: bash
    
        sphinx-apidoc -o source/api-docs ../crocodile_dashboard # Then rename api-docs/modules.rst title to Auto Generated Docs