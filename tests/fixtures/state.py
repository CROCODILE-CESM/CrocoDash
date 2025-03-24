import pytest
import os
import socket


@pytest.fixture(scope="session")
def is_glade_file_system():
    # Get the hostname
    hostname = socket.getfqdn()
    # Check if "derecho" or "casper" is in the hostname and glade exists currently
    is_on_glade_bool = (
        "ucar" in hostname
    ) and os.path.exists("/glade")

    return is_on_glade_bool


@pytest.fixture(scope="session")
def skip_if_not_glade(is_glade_file_system):
    if not is_glade_file_system:
        pytest.skip(reason="Skipping test: Not running on the Glade file system.")


@pytest.fixture()
def is_github_actions():
    return os.getenv("GITHUB_ACTIONS") == "true"


@pytest.fixture(scope="session")
def get_cesm_root_path(is_glade_file_system):
    cesmroot = os.getenv("CESMROOT")

    if is_glade_file_system:
        cesmroot = "/glade/u/home/manishrv/work/installs/CROCESM_beta04"
    return cesmroot
