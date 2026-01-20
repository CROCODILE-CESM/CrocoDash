# Write Documentation

We are using Sphinx to write and compile documentation. The documentation is written in markdown (myst) format. The documentation is located in the `docs` folder. The documentation is hosted on github-pages. Please follow the below steps to compile documentation.

Steps:

1. Activate the environment

2. Navigate to the docs folder

3. Run the following command:

   ```bash
   make html
   ```

4. To reformulate the autodocs, which needs to be done when new modules & submodules are created, run this step

   > ```bash
   > sphinx-apidoc -o source/api-docs ../CrocoDash
   > ```

5. If you're on a supercomputer, you can run this command to run a local server and see it on your computer:

   ```bash
   make serve
   ```
