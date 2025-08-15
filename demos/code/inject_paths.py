import json
from pathlib import Path
import os
import nbformat
import argparse


def main(reverse=False):

    with open(Path(__file__).parent / "data_paths.json", "r") as f:
        paths = json.load(f)
    notebooks_path = Path(__file__).parent.parent / "gallery" / "notebooks"

    for root, dirs, files in os.walk(notebooks_path):
        for name in files:
            notebook_path = Path(root) / name
            print(f"Processing: {notebook_path}")

            # Load the notebook
            nb = nbformat.read(notebook_path, as_version=4)

            changed = False
            for cell in nb.cells:
                if cell.cell_type in ("code", "Python"):
                    original_source = cell.source
                    for key, real_path in paths.items():
                        full_str = "<" + key + ">"
                        if not reverse:
                            if full_str in cell.source:
                                cell.source = cell.source.replace(full_str, real_path)
                                changed = True
                        else:
                            if real_path in cell.source:
                                cell.source = cell.source.replace(real_path, full_str)
                                changed = True

                    if original_source != cell.source:
                        print(f"  Modified cell in {name}")

            # Write changes back only if something was modified
            if changed:

                nbformat.write(nb, notebook_path)
                print(f"  Saved updated notebook: {notebook_path}")

    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inject or reverse-inject paths in notebooks."
    )
    parser.add_argument(
        "--reverse", action="store_true", help="Reverse the path injection."
    )
    args = parser.parse_args()
    main(reverse=True)
