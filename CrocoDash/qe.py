"""The CrocoDash rules: advice that applies to a case's grid, compset and run.

Case() and configure_forcings() query RULES and print what applies. Most rules come
from expert interviews and cite the passage they rest on; all are drafts until an
expert has reviewed them.

The rules are two queryearth packs next to this file: folders with a folder per
category, which nest, and a GeoJSON file per rule, named by its code.

- rules/ holds Manish's rules, such as rules/REGION/ITF/ITF001.geojson.
- rules_claude/ holds the rules Claude added from the interviews on its own, in the
  CLAUDE category, until they are reviewed. A reviewed one moves to rules/ under its
  category's next code, RULES.next_code("ITF"), with its old code in "aliases"; a
  number is never reused.

To add or change a rule, edit its file, or draw it in vizqueryearth and save the
GeoJSON it shows as the rule's file. Then `python -m CrocoDash.qe` writes both packs
to qe_rules.geojson, the one file a vizqueryearth link shows; `--report` prints
every rule instead.
"""

import sys
from pathlib import Path

import queryearth as qe

HERE = Path(__file__).resolve().parent
PACKS = (HERE / "rules", HERE / "rules_claude")
RULES = qe.Registry.from_file(*PACKS)

if __name__ == "__main__":
    if sys.argv[1:] == ["--report"]:
        print(qe.report(RULES.query(include_conditional=True)))
    else:
        RULES.to_file(HERE / "qe_rules.geojson")
