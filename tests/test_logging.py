"""Tests for file logging setup (SPEC.md §7).

flowspeech.main pulls in rumps/AppKit, so these skip where that can't import
(headless CI) and run on the Mac where the .app actually lives.
"""

import logging

import pytest


def test_file_logging_skipped_without_resourcepath(tmp_path, monkeypatch):
    main = pytest.importorskip("flowspeech.main")
    monkeypatch.delenv("RESOURCEPATH", raising=False)

    assert main.setup_file_logging(tmp_path) is None


def test_file_logging_writes_in_app_mode(tmp_path, monkeypatch):
    main = pytest.importorskip("flowspeech.main")
    monkeypatch.setenv("RESOURCEPATH", str(tmp_path))

    handler = main.setup_file_logging(tmp_path)
    try:
        assert handler is not None
        # pytest lowers the root logger to WARNING; make sure the INFO record
        # actually reaches the handler under test.
        emitter = logging.getLogger("flowspeech.test")
        emitter.setLevel(logging.INFO)
        emitter.info("timing 1.0s 12 chars")
        handler.flush()
        log_file = tmp_path / "logs" / "flowspeech.log"
        assert log_file.exists()
        assert "12 chars" in log_file.read_text(encoding="utf-8")
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
