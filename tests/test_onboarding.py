"""Tests for onboarding.py — flag-file logic only (no AppKit UI)."""

from flowspeech.onboarding import (
    FLAG_FILENAME,
    mark_onboarding_seen,
    onboarding_needed,
)


def test_onboarding_needed_on_fresh_dir(tmp_path):
    assert onboarding_needed(tmp_path) is True


def test_mark_seen_creates_flag_and_flips_needed(tmp_path):
    mark_onboarding_seen(tmp_path)

    assert (tmp_path / FLAG_FILENAME).exists()
    assert onboarding_needed(tmp_path) is False


def test_mark_seen_creates_missing_dir(tmp_path):
    nested = tmp_path / "does-not-exist-yet"

    mark_onboarding_seen(nested)

    assert onboarding_needed(nested) is False
