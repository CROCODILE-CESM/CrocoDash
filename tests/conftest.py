import pathlib

# # Add these lines to run CESM tests
# import os

# os.environ["CESMROOT"] = "/home/manishrv/CROCESM"
# os.environ["CIME_MACHINE"] = "ubuntu-latest"

# Dynamically discover all fixtures in fixtures directories
fixtures_dir = pathlib.Path(__file__).parent / "fixtures"
pytest_plugins = [
    f"tests.fixtures.{f.stem}"
    for f in fixtures_dir.glob("*.py")
    if f.stem != "__init__"
]


def pytest_addoption(parser):
    # Domain-catalog selection. See tests/fixtures/domains.py for the catalog
    # itself and select_domains() for the precedence rules.
    parser.addoption(
        "--domains",
        default=None,
        help="Comma-separated domain keys, e.g. --domains=arctic_cap,tiny",
    )
    parser.addoption(
        "--domain-tags",
        default=None,
        help="Comma-separated domain tags, e.g. --domain-tags=seam,polar",
    )
    parser.addoption(
        "--all-domains",
        action="store_true",
        default=False,
        help="Run every domain in the catalog, not just the 'cheap' tier",
    )


def pytest_generate_tests(metafunc):
    """Parametrize any test taking a `domain`-family fixture over the catalog.

    Modules marked `needs_forcing` additionally get each domain's
    DomainSpec.xfail applied -- see select_domains() for why that is opt-in.
    """
    if "domain" in metafunc.fixturenames:
        from tests.fixtures.domains import select_domains

        needs_forcing = metafunc.definition.get_closest_marker("needs_forcing")
        metafunc.parametrize(
            "domain",
            select_domains(metafunc.config, apply_xfail=needs_forcing is not None),
        )
