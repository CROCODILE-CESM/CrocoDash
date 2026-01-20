# Write Documentation

We are using Sphinx to write and compile documentation. The documentation is written in reStructuredText (reST) format. The documentation is located in the `docs` folder. The documentation is hosted on github-pages. Please follow the below steps to compile documentation.

Steps:

1. Activate the environment

2. Navigate to the docs folder

3. Run the following command:

   ```bash
   make html
   ```

4. To rekickstart the autodocs

   > ```bash
   > sphinx-apidoc -o source/api-docs ../CrocoDash
   > ```
