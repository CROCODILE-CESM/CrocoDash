"""Tests for the CrocoDash rules in CrocoDash/qe.py."""

import numpy as np

from CrocoDash.qe import RULES, grid_outline


def test_the_rule_files_load_and_every_code_names_a_category():
    assert len(RULES.rules) == 26
    assert all(rule.category for rule in RULES.rules)


def test_an_itf_domain_finds_the_itf_rules():
    # a 1/12 degree latitude-longitude grid over the Indonesian seas, by its corners
    qlon, qlat = np.meshgrid(np.linspace(105, 145, 481), np.linspace(-15, 10, 301))
    found = RULES.query(
        space=grid_outline(qlon, qlat),
        resolution=(9.1, 9.3),
        cell_size_ratio=1.02,
        atmosphere="jra",
        ice="sice",
    )
    itf = [f"REGION/ITF/ITF00{n}" for n in (1, 2, 3, 4, 6)]
    assert sorted(rule.code for rule in found) == [
        "CLAUDE/CLAUDE006",
        "CLAUDE/CLAUDE007",
        *itf,
    ]
