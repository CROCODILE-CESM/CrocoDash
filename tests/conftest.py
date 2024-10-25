import pytest
import socket
import os

def is_glade_file_system():
    # Get the hostname
    hostname = socket.gethostname()
    # Check if "derecho" or "casper" is in the hostname and glade exists currently
    is_on_glade_bool =  ('derecho' in hostname or 'casper' in hostname) and os.path.exists("/glade")

    return is_on_glade_bool

@pytest.fixture(scope='session')
def check_glade_exists():
    if not is_glade_file_system():
        pytest.skip(reason = "Skipping test: Not running on the Glade file system.")

