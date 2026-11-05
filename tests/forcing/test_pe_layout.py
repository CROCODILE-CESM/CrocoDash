import pytest

from CrocoDash.forcing.pe_layout import pe_layout


@pytest.mark.parametrize(
    "ocean_points, marbl, ntasks_ocn, expected",
    [
        # (NTASKS, ROOTPE, NTASKS_OCN, ROOTPE_OCN) on a 128-task node
        (100, False, None, (1, 0, 1, 0)),  # 1 task: MOM_interface's XS
        (5_000, False, None, (1, 0, 32, 0)),  # 30 tasks: the 32 tier, one node
        (15_000, False, None, (128, 0, 128, 128)),  # 89: S
        (30_000, False, None, (128, 0, 384, 128)),  # 177, two nodes: M
        (200_000, False, None, (128, 0, 896, 128)),  # 1177, ten nodes: L
        (5_000, True, None, (128, 0, 384, 128)),  # 84 with MARBL: MARBL's S
        (30_000, False, 8, (1, 0, 8, 0)),  # ntasks_ocn replaces the count
    ],
)
def test_pe_layout_picks_the_smallest_tier_that_fits(
    ocean_points, marbl, ntasks_ocn, expected
):
    layout = pe_layout(ocean_points, 128, marbl=marbl, ntasks_ocn=ntasks_ocn)
    assert layout == dict(
        zip(("NTASKS", "ROOTPE", "NTASKS_OCN", "ROOTPE_OCN"), expected)
    )
