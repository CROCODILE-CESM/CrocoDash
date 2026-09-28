"""Tests for CrocoDash.logging.setup_logger."""

import logging as stdlib_logging

import pytest

from CrocoDash import logging as cd_logging


def test_setup_logger_returns_logger_with_handler():
    """A fresh logger should get a StreamHandler attached with a formatter."""
    name = "crocdash_test_logger_fresh"

    # Clear any handlers from a prior run and disable propagation so that
    # Logger.hasHandlers() does NOT return True based on ancestors (e.g. the
    # root logger that pytest/other imports may have configured).
    existing = stdlib_logging.getLogger(name)
    for h in list(existing.handlers):
        existing.removeHandler(h)
    existing.propagate = False

    logger = cd_logging.setup_logger(name)
    try:
        assert logger.name == name
        assert logger.level == stdlib_logging.INFO
        # This logger should now own its own handler (not rely on ancestors).
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert handler.formatter is not None
        assert "%(asctime)s" in handler.formatter._fmt
    finally:
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.propagate = True


def test_setup_logger_is_idempotent():
    """Calling setup_logger twice should not stack duplicate handlers."""
    name = "crocdash_test_logger_idempotent"
    existing = stdlib_logging.getLogger(name)
    for h in list(existing.handlers):
        existing.removeHandler(h)
    existing.propagate = False

    logger_a = cd_logging.setup_logger(name)
    handler_count_after_first = len(logger_a.handlers)
    logger_b = cd_logging.setup_logger(name)
    try:
        assert logger_a is logger_b
        assert len(logger_b.handlers) == handler_count_after_first
        assert handler_count_after_first == 1
    finally:
        for h in list(logger_b.handlers):
            logger_b.removeHandler(h)
        logger_b.propagate = True


@pytest.fixture
def restore_levels():
    """Put back every logger level a test changes, for the rest of the run."""
    saved = {
        name: logger.level
        for name, logger in list(stdlib_logging.Logger.manager.loggerDict.items())
        if isinstance(logger, stdlib_logging.Logger)
    }
    yield
    for name, logger in list(stdlib_logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, stdlib_logging.Logger):
            logger.setLevel(saved.get(name, stdlib_logging.NOTSET))


def test_quiet_visualcasegen_info_hides_only_visualcasegen_info(caplog, restore_levels):
    """visualCaseGen's loggers are the whitespace-padded ones: their INFO goes,
    their warnings stay, and other loggers are left alone."""
    vcg = stdlib_logging.getLogger("\tfake_vcg_stage")
    other = stdlib_logging.getLogger("CrocoDash.fake_module")
    other.setLevel(stdlib_logging.INFO)
    cd_logging.quiet_visualcasegen_info()
    with caplog.at_level(stdlib_logging.INFO):
        vcg.info("Enabling stage 1. Component Set.")
        vcg.warning("a real visualCaseGen warning")
        other.info("[REQUIRED] Activating StreamYears")
    messages = [r.getMessage() for r in caplog.records]
    assert "Enabling stage 1. Component Set." not in messages
    assert "a real visualCaseGen warning" in messages
    assert "[REQUIRED] Activating StreamYears" in messages


def test_quiet_visualcasegen_info_keeps_a_level_already_set(restore_levels):
    vcg = stdlib_logging.getLogger("\tfake_vcg_verbose")
    vcg.setLevel(stdlib_logging.DEBUG)
    cd_logging.quiet_visualcasegen_info()
    assert vcg.level == stdlib_logging.DEBUG


def test_importing_case_quiets_the_real_visualcasegen_loggers():
    """Guards the whitespace naming this relies on: if visualCaseGen renames
    its loggers, this fails instead of the INFO lines silently coming back."""
    import CrocoDash.case  # noqa: F401 -- the import does the quieting

    stage = stdlib_logging.Logger.manager.loggerDict.get("\tstage")
    assert isinstance(stage, stdlib_logging.Logger)
    assert stage.getEffectiveLevel() == stdlib_logging.WARNING
