import pytest
import os
import socket


@pytest.fixture(scope="session")
def is_glade_file_system():
    # Get the hostname
    hostname = socket.getfqdn()
    # Check if "derecho" or "casper" is in the hostname and glade exists currently
    is_on_glade_bool = ("ucar" in hostname) and os.path.exists("/glade")

    return is_on_glade_bool


@pytest.fixture(scope="session")
def skip_if_not_glade(is_glade_file_system):
    if not is_glade_file_system:
        pytest.skip(reason="Skipping test: Not running on the Glade file system.")


@pytest.fixture(scope="session")
def is_github_actions():
    return os.getenv("GITHUB_ACTIONS") == "true"


@pytest.fixture(scope="session")
def get_cesm_root_path(is_glade_file_system):
    """Path to a CESM checkout, or skip every test that needs one.

    $CESMROOT wins, so the suite can be pointed at any checkout without editing this
    file; otherwise fall back to a known location per platform.

    A checkout is required rather than optional, and CESM_NOT_PORTED does not change
    that: CIME_interface asserts that <cesmroot>/cime exists and reads compsets, grids
    and the machine list out of the tree *before* it can decide the host is un-ported.
    "Un-ported" means CESM is present but this host has no machine definition -- not
    that CESM is absent. So when there is no checkout to read, skip instead of failing;
    the ~200 tests that never build a Case are unaffected and still run.
    """
    cesmroot = os.getenv("CESMROOT")
    if cesmroot is None:
        if is_glade_file_system:
            cesmroot = "/glade/u/home/manishrv/work/installs/full_regional_cesm"
        else:
            cesmroot = "/Users/manishrv/Documents/cesm"
            os.environ["CIME_MACHINE"] = "ubuntu-latest"  # macos has problems with VCG
    if not os.path.isdir(os.path.join(cesmroot, "cime")):
        pytest.skip(
            f"No CESM checkout at {cesmroot} (no cime/ subdirectory). Set $CESMROOT to "
            "a CESM checkout to run the tests that build a Case."
        )
    return cesmroot
