"""Tests for CrocoDash.logging.setup_logger."""

import logging as stdlib_logging

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
