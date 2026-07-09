"""Tests for updates.py — no real network (fetch is mocked)."""

from datetime import datetime, timedelta
from unittest.mock import patch

from flowspeech import updates
from flowspeech.updates import (
    check_for_update,
    due_for_check,
    is_newer,
    parse_version,
    record_check,
)


def test_parse_version_numeric_tuple():
    assert parse_version("1.2.10") == (1, 2, 10)
    assert parse_version("v1.0") == (1, 0)  # junk digits stripped


def test_is_newer_compares_numerically_not_lexically():
    assert is_newer("1.2.10", "1.2.9") is True  # 10 > 9, not "10" < "9"
    assert is_newer("1.10.0", "1.9.0") is True


def test_is_newer_equal_and_older():
    assert is_newer("1.0.0", "1.0.0") is False
    assert is_newer("1.0", "1.0.0") is False  # zero-padded equal
    assert is_newer("0.9.9", "1.0.0") is False


def test_check_for_update_returns_info_when_newer():
    with patch.object(updates, "fetch_appcast",
                      return_value={"version": "2.0.0", "url": "https://x/dl"}):
        info = check_for_update("1.0.0")

    assert info is not None
    assert info.version == "2.0.0"
    assert info.url == "https://x/dl"


def test_check_for_update_none_when_current_is_latest():
    with patch.object(updates, "fetch_appcast", return_value={"version": "1.0.0"}):
        assert check_for_update("1.0.0") is None


def test_check_for_update_silent_on_network_error():
    # fetch_appcast swallows errors and returns None; check must stay quiet.
    with patch.object(updates, "fetch_appcast", return_value=None):
        assert check_for_update("1.0.0") is None


def test_fetch_appcast_returns_none_on_urlopen_error():
    def boom(*_args, **_kwargs):
        raise OSError("no network")

    with patch("urllib.request.urlopen", side_effect=boom):
        assert updates.fetch_appcast("https://x/appcast.json") is None


def test_due_for_check_true_without_stamp(tmp_path):
    assert due_for_check(tmp_path) is True


def test_due_for_check_false_right_after_record(tmp_path):
    record_check(tmp_path)

    assert due_for_check(tmp_path) is False


def test_due_for_check_true_after_a_day(tmp_path):
    record_check(tmp_path, now=datetime.now() - timedelta(days=2))

    assert due_for_check(tmp_path) is True
