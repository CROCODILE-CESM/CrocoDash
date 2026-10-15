"""The CrocoDash rules: advice that applies to a case's grid, compset and run.

The rules live in CrocoGallery, in crocodash/rules: Manish's rules.geojson and
rules_claude.geojson, the rules Claude added until they are reviewed. They are
read from the gallery commit that the gallery submodule points to, so a rule
change there reaches CrocoDash with a submodule bump. Case() and
configure_forcings() query them and print what applies.

`python -m CrocoDash.qe` prints every rule.
"""

import queryearth as qe
from crocogallery import rule_files


def registry() -> qe.Registry:
    """Every CrocoDash rule file, read together."""
    return qe.Registry.from_file(*rule_files())


if __name__ == "__main__":
    print(qe.report(registry().query(include_conditional=True)))
