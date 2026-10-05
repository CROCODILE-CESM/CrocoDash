"""Render CrocoGallery notebooks into starter files for `crocodash template`.

The gallery is not vendored. Its files -- the notebooks, known_paths.json,
and the loose pbs/yaml assets -- are fetched over HTTP from a pinned ref of
the CrocoGallery repo on every run (no on-disk cache). The gallery publishes
gallery_manifest.json so the files can be located without listing a remote
tree.

GALLERY_REF pins the gallery to a version known to match this CrocoDash.
The gallery is written ahead of CrocoDash (in-flight features included), so
tracking `main` could hand users notebooks their install cannot run. Bump
the ref when releasing, the same way a submodule pointer would be bumped.

Set CROCODASH_GALLERY_PATH (or pass --gallery-path) to read a local
CrocoGallery checkout instead -- for offline use, CI, and gallery dev.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

GALLERY_REPO = "CROCODILE-CESM/CrocoGallery"
GALLERY_REF = "main"
GALLERY_PATH_ENV = "CROCODASH_GALLERY_PATH"
MANIFEST_NAME = "gallery_manifest.json"

DEFAULT_TEMPLATE_NOTEBOOK_ID = "crocodash.tutorial-ocn"

# Machine key used when the caller does not name one. Must match a top-level
# key in known_paths.json.
DEFAULT_MACHINE = "glade"

# known_paths.json *values* that are stand-ins rather than real paths -- a
# machine that has not filled in its checkout/case/input locations. Injecting
# one would swap an obvious <KEY> for something equally uninformative, so those
# entries are left for hand editing. Filtering on the value rather than the key
# matters: a machine that does give CESM/inputdir/casedir real values (or CI,
# which seds these sentinels into real directories) gets them injected.
SENTINEL_VALUES = {"Checkout", "fill_in_id", "fill_in_cd"}

# Loose template files that live in the gallery next to the notebooks.
TEMPLATE_ASSETS = {"pbs": "submit_forcings.pbs", "yaml": "starter_case.yaml"}

_TIMEOUT_S = 30


class GalleryUnavailableError(FileNotFoundError):
    """The gallery could not be read (no network, bad ref, bad local path)."""


class GallerySource:
    """Read-only access to CrocoGallery files, from a local checkout or HTTP."""

    def __init__(self, path=None, ref=GALLERY_REF):
        path = path or os.environ.get(GALLERY_PATH_ENV)
        self.local = Path(path).expanduser() if path else None
        self.ref = ref
        if self.local is not None and not (self.local / MANIFEST_NAME).is_file():
            raise GalleryUnavailableError(
                f"No {MANIFEST_NAME} in gallery checkout {self.local}. "
                "Point --gallery-path at the root of a CrocoGallery checkout."
            )
        self._manifest = None

    def __repr__(self):
        where = self.local if self.local else f"{GALLERY_REPO}@{self.ref}"
        return f"GallerySource({where})"

    def _url(self, relpath):
        return f"https://raw.githubusercontent.com/{GALLERY_REPO}/{self.ref}/{relpath}"

    def _fetch(self, relpath):
        url = self._url(relpath)
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as resp:
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as e:
            raise GalleryUnavailableError(
                f"Could not download {url} ({e}).\n"
                "If you are offline or behind a firewall, point at a local "
                f"CrocoGallery checkout with --gallery-path or ${GALLERY_PATH_ENV}."
            ) from e

    def read_text(self, relpath):
        if self.local is not None:
            return (self.local / relpath).read_text()
        return self._fetch(relpath)

    def manifest(self):
        if self._manifest is None:
            self._manifest = json.loads(self.read_text(MANIFEST_NAME))
        return self._manifest

    def list_notebooks(self):
        """Return {notebook_id: relative_path} for every gallery notebook.

        ID format: dot-separated path relative to the gallery root, no extension.
        Example: "crocodash.tutorial-ocn"
        """
        return dict(self.manifest()["notebooks"])

    def read_notebook(self, notebook_id):
        import nbformat

        notebooks = self.list_notebooks()
        if notebook_id not in notebooks:
            available = "\n  ".join(sorted(notebooks))
            raise KeyError(
                f"Unknown notebook {notebook_id!r}. Available:\n  {available}"
            )
        return nbformat.reads(self.read_text(notebooks[notebook_id]), as_version=4)

    def read_asset(self, name):
        assets = self.manifest()["assets"]
        if name not in assets:
            raise GalleryUnavailableError(
                f"No template asset named {name!r} in the gallery manifest."
            )
        return self.read_text(assets[name])

    def known_paths(self):
        return json.loads(self.read_text(self.manifest()["known_paths"]))


def load_paths(machine, source):
    """Return the {KEY: path} dict for `machine` from the gallery's
    known_paths.json."""
    db = source.known_paths()
    if machine not in db:
        available = ", ".join(db.keys())
        raise KeyError(f"Unknown machine '{machine}'. Available: {available}")
    return db[machine]


def template_paths(machine, source):
    """Path table for template rendering, minus the hand-edit placeholders.

    A machine of None means "leave every <KEY> alone".
    """
    if machine is None:
        return {}
    paths = load_paths(machine, source)
    return {k: v for k, v in paths.items() if v not in SENTINEL_VALUES}


def inject_into_text(text, paths):
    """Replace <KEY> placeholders in a plain string."""
    for key, val in paths.items():
        text = text.replace(f"<{key}>", val)
    return text


def comment_out_magics(source):
    """Comment out IPython magic/shell lines (jupytext convention) so
    extracted code cells are valid, runnable Python."""
    return "\n".join(
        "# " + line if re.match(r"^\s*[%!]", line) else line
        for line in source.split("\n")
    )


def render_notebook(source, notebook_id, paths):
    """Return an nbformat notebook with paths injected into code and markdown
    cells (markdown carries shell commands, e.g. `qcmd -A <PROJECT>`)."""
    nb = source.read_notebook(notebook_id)
    for cell in nb.cells:
        if cell.cell_type in ("code", "markdown"):
            cell.source = inject_into_text(cell.source, paths)
    return nb


def render_script(source, notebook_id, paths):
    """Return the notebook as a jupytext-style `# %%` Python script."""
    nb = source.read_notebook(notebook_id)
    blocks = []
    for cell in nb.cells:
        if cell.cell_type == "code":
            code = comment_out_magics(inject_into_text(cell.source, paths))
            blocks.append("# %%\n" + code)
        elif cell.cell_type == "markdown":
            text = inject_into_text(cell.source, paths)
            commented = "\n".join(
                f"# {line}" if line else "#" for line in text.split("\n")
            )
            blocks.append("# %% [markdown]\n" + commented)
    return "\n\n".join(blocks)


def render_asset(source, asset_kind, paths):
    """Return a loose template asset ('pbs' or 'yaml') with paths injected."""
    return inject_into_text(source.read_asset(TEMPLATE_ASSETS[asset_kind]), paths)


def write_template(
    output,
    notebook_id=DEFAULT_TEMPLATE_NOTEBOOK_ID,
    machine=None,
    kind="case",
    source=None,
):
    """Write a starter template to `output`.

    The output suffix picks the format: .yaml/.yml a config, .pbs a batch
    script, .ipynb a notebook, anything else a `# %%` Python script.
    kind="pbs" forces the batch script regardless of suffix.
    """
    import nbformat

    source = source or GallerySource()
    output = Path(output)
    paths = template_paths(machine, source)

    # Render before touching the filesystem so a fetch failure leaves no
    # empty output (or stray parent directories) behind.
    is_pbs = kind == "pbs" or output.suffix == ".pbs"
    if is_pbs:
        text = render_asset(source, "pbs", paths)
    elif output.suffix in (".yaml", ".yml"):
        text = render_asset(source, "yaml", paths)
    elif output.suffix == ".ipynb":
        # nbformat.write() ends the file with a newline; writes() does not.
        text = nbformat.writes(render_notebook(source, notebook_id, paths)) + "\n"
    else:
        text = render_script(source, notebook_id, paths)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    if is_pbs:
        output.chmod(output.stat().st_mode | 0o111)
    return output


def uses_notebook(output, kind="case"):
    """Whether this output would be rendered from --notebook.

    The pbs and yaml templates are standalone assets, so --notebook is
    meaningless for them; callers use this to warn instead of silently
    ignoring the flag.
    """
    output = Path(output)
    return not (kind == "pbs" or output.suffix in (".pbs", ".yaml", ".yml"))
