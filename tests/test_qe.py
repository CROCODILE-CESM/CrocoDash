"""Tests for the CrocoDash rules in CrocoDash/qe.py."""

import json

from CrocoDash import qe as rules


def test_qe_rules_geojson_holds_the_packs():
    """qe_rules.geojson, the file a vizqueryearth link shows, is written from the
    packs; after changing a rule, rerun `python -m CrocoDash.qe`."""
    written = json.loads((rules.HERE / "qe_rules.geojson").read_text())
    assert written == rules.RULES.to_collection()
