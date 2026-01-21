# Write Documentation

## Overview

CrocoDash documentation is built using [Sphinx](https://www.sphinx-doc.org/) and written in [MyST (Markedly Structured Text)](https://myst-parser.readthedocs.io/) Markdown format. The documentation lives in two places: 

1. in the `docs/source` folder and is hosted on GitHub Pages.
2. In a submodule and github repo called CrocoGallery, which hosts tutorials and a gallery for CrocoDash. This is also hosted on github pages, and is officially a Jupyter Book, which also runs in MyST. This is built and published similar to CrocoDash, but the frameowrk jupyter book is a bit different.

## Building Documentation

### Basic Build

1. Activate the conda environment:
   ```bash
   mamba activate CrocoDash
   ```

2. Navigate to the docs folder:
   ```bash
   cd docs
   ```

3. Build HTML documentation:
   ```bash
   make html
   ```

   This generates HTML files in `docs/build/html/`. Open `index.html` in your browser to view the built documentation. Pushing to a PR or main will build the docs online.

### Clean Build

If documentation seems stale or you encounter build errors, perform a clean build:

```bash
cd docs
make clean
make html
```

This removes cached build files and rebuilds from scratch.

## Regenerating API Documentation

When you add new modules or submodules to CrocoDash, you need to regenerate the auto-documentation from docstrings:

```bash
cd docs
sphinx-apidoc -o source/api-docs ../CrocoDash # This reads the code of CrocoDash and loads it into source/apidocs
# You may consider deleting the regional_mom6 api docs, regional_mom6 has its own docs (which is what I've been doing.)
make html
```

**Why this is needed:** The API docs are auto-generated from your Python docstrings. When you add new modules, Sphinx needs to scan them and create `.rst` files documenting the public API.

**When to do this:**
- You create a new module or submodule under `CrocoDash/`
- You add new public classes or functions to existing modules
- You significantly restructure the package

**Note:** The `sphinx-apidoc` command creates/updates files in `source/api-docs/`. These are referenced in the main documentation structure.

## Local Server Preview

If you're on a supercomputer or want to preview documentation in a browser:

```bash
cd docs
make serve
```

This starts a local web server. The command will print a URL (typically `http://127.0.0.1:8080`) that you can access. Locally, just open the index.html file instead, don't start a server.

## MyST Markdown Format

CrocoDash documentation uses MyST, which extends standard Markdown with Sphinx capabilities. It's powerful and modern! Take full advantage, we don't use RST for a reason.

## Documentation Structure

The documentation is organized as follows:

```
docs/source/
├── index.md                 # Main landing page
├── installation.md          # Installation instructions
├── for_users/               # User-focused documentation
│   └── index.md
├── for_developers/          # Developer documentation
│   ├── index.md
│   ├── docs.md              # This file
│   └── ...
├── api-docs/                # Auto-generated API documentation
│   ├── modules.rst
│   └── ...
├── raw_data_access/         # See more about this below
└── _static/                 # Static files (CSS, images, etc.)
```

## Sphinx Configuration

Sphinx configuration is in `docs/source/conf.py`. Key settings:

- `extensions` - Sphinx extensions loaded (MyST, theme, etc.)
- `html_theme` - The theme used
- `myst_enable_extensions` - MyST-specific extensions enabled

Usually you don't need to modify this, but consult it if you're using advanced Sphinx features.

## Raw Data Access
Every night, there is a CI action (in raw_data_access_testing.yml) to check if the datasets are accessible. Those are then updated on a page in the documentation, https://crocodile-cesm.github.io/CrocoDash/reports/raw_data_status.html. The code to check the raw_data_access is in the raw_data_access subfolder of docs/source, called check_raw_data.py. There is also a script called generate_info.py that generates the two tables in the same folder which list the products and functions available. This is run when the docs are built.

## Diagrams
The diagrams are generated from the scripts in docs/source/diagrams. They run when the docs are built.

## FAQs

The FAQs link on the docs is just a Github Dicussion on CrocoDash! Feel free to add anything to that.

## Publishing Documentation (This is important! Read This!)

CrocoDash documentation is automatically published to GitHub Pages when you push to the main branch (via GitHub Actions or similar CI/CD). No manual steps are required, but ensure:

1. Your documentation builds locally without errors
2. All cross-references are valid
3. You've committed and pushed changes to GitHub

How it is built is with a github action called deploy_sphinx_docs.yml. What it does is build the docs, and based on if its a PR or a push to main, pushes the files to a folder in the gh-pages branch in the repo. Github Settings Pages is setup to deploy everytime there is a push to gh_pages. This deploys **everything** in gh-pages. This means a subfolder called workshop, will show up under the link crocodile-cesm.github.io/CrocoDash/workshop, and one called "pr-28" will show up under the sublink /pr-28/. This is useful because of how we setup the docs. 

Old versions of the docs may be set under links workshop (which I've set up manually), the latest push to main is under the subfolder /latest/. Prs are in /pr-xx/. The main index page just reroutes to /latest/

## Troubleshooting

### API docs not appearing

Check that:
1. You ran `sphinx-apidoc -o source/api-docs ../CrocoDash`
2. The generated files exist in `source/api-docs/`
3. The `api-docs/modules` is referenced in `index.md` toctree

### Documentation not updating after changes

Try a clean build:
```bash
make clean
make html
```

The HTML files are cached; cleaning removes stale caches.

### Broken cross-references

Ensure that:
1. The file path is correct (relative to the docs source)
2. You use the correct Sphinx role syntax: `{py:class}`, `{py:func}`, etc.
3. The Python object actually exists and is properly imported


## Best Practices

1. **Use Clear Headings** - Organize content with proper heading hierarchy (# for main, ## for sections, etc.)
2. **Write Docstrings** - Add docstrings to all public functions, classes, and modules; API docs pull from these
3. **Link to Code** - Use cross-references to link documentation to actual code
4. **Test Links** - After building, check that internal and external links work
5. **Keep It Updated** - Update documentation when you change the API or add features
6. **Use Admonitions** - Highlight warnings, notes, and important information
7. **Provide Examples** - Include code examples where helpful
8. **Review Locally** - Always build and review documentation locally before pushing
