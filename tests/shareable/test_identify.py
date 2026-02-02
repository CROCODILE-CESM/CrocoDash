from CrocoDash.shareable.identify import *
import pytest


@pytest.fixture(scope="module")
def two_cesm_cases(CrocoDash_case_factory, tmp_path_factory):
    case1 = CrocoDash_case_factory(tmp_path_factory.mktemp("case1"))
    case2 = CrocoDash_case_factory(tmp_path_factory.mktemp("case2"))
    return case1, case2


def test_diff_CESM_cases(skip_if_not_glade, two_cesm_cases, tmp_path):

    case1, case2 = two_cesm_cases
    output = diff_CESM_cases(
        case1.caseroot,
        case2.caseroot,
    )
    assert isinstance(output["xml_files_missing_in_new"], list)
    assert output["xml_files_missing_in_new"] == []
    assert output["user_nl_missing_params"] == {}
    assert output["source_mods_missing_files"] == []
    assert output["xmlchanges_missing"] == []
