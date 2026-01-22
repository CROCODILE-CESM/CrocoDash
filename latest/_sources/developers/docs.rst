Write Documentation
====================

We are using Sphinx to write and compile documentation. The documentation is written in reStructuredText (reST) format. The documentation is located in the `docs` folder. The documentation is hosted on github-pages. Please follow the below steps to compile documentation.


Steps:

#. Activate the environment
#. Navigate to the docs folder
#. Run the following command:

   .. code-block:: bash

      make html
#. To rekickstart the autodocs

    .. code-block:: bash
    
        sphinx-apidoc -o source/api-docs ../CrocoDash