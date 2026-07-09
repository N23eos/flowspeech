"""license.py: trial arithmetic, tamper handling, activation, offline grace."""

import json
from datetime import datetime, timedelta

from flowspeech import license as license_mod
from flowspeech.license import (
    KIND_EXPIRED,
    KIND_LICENSED,
    KIND_TRIAL,
    TRIAL_DAYS,
    LicenseManager,
)


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def make_manager(tmp_path, clock=None):
    return LicenseManager(tmp_path, now=clock or datetime.now)


def test_first_run_starts_trial(tmp_path):
    status = make_manager(tmp_path).status()
    assert status.kind == KIND_TRIAL
    assert status.days_left == TRIAL_DAYS
    assert status.can_dictate


def test_trial_expires_after_seven_days(tmp_path):
    clock = Clock(datetime(2026, 7, 1, 12, 0))
    manager = make_manager(tmp_path, clock)
    assert manager.status().kind == KIND_TRIAL

    clock.now += timedelta(days=TRIAL_DAYS - 1)
    assert make_manager(tmp_path, clock).status().kind == KIND_TRIAL

    clock.now += timedelta(days=2)
    status = make_manager(tmp_path, clock).status()
    assert status.kind == KIND_EXPIRED
    assert not status.can_dictate


def test_tampered_trial_marker_means_expired_not_fresh(tmp_path):
    clock = Clock(datetime(2026, 7, 1))
    make_manager(tmp_path, clock).status()  # creates the marker
    marker = tmp_path / "trial.json"
    data = json.loads(marker.read_text())
    data["started"] = "2099-01-01T00:00:00"  # hand-edited date, stale sig
    marker.write_text(json.dumps(data))
    assert make_manager(tmp_path, clock).status().kind == KIND_EXPIRED


def test_activation_success_caches_license(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(
        manager, "_api_activate",
        lambda key: {"activated": True, "instance": {"id": "inst-1"}},
    )
    ok, message = manager.activate("KEY-123456")
    assert ok, message
    status = manager.status()
    assert status.kind == KIND_LICENSED
    assert status.can_dictate
    # The cache alone must be enough — no network on subsequent status calls.
    assert make_manager(tmp_path).status().kind == KIND_LICENSED


def test_activation_rejected_key(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(
        manager, "_api_activate",
        lambda key: {"activated": False, "error": "license key not found"},
    )
    ok, message = manager.activate("BAD-KEY")
    assert not ok
    assert "не принят" in message
    assert manager.status().kind == KIND_TRIAL


def test_activation_network_error_keeps_trial(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)

    def boom(key):
        raise OSError("no network")

    monkeypatch.setattr(manager, "_api_activate", boom)
    ok, message = manager.activate("KEY-123456")
    assert not ok
    assert "интернет" in message
    assert manager.status().kind == KIND_TRIAL  # nothing was broken


def test_revalidation_network_error_keeps_license(tmp_path, monkeypatch):
    clock = Clock(datetime(2026, 7, 1))
    manager = make_manager(tmp_path, clock)
    monkeypatch.setattr(
        manager, "_api_activate", lambda key: {"activated": True, "instance": {}}
    )
    manager.activate("KEY-123456")

    clock.now += timedelta(days=90)  # revalidation due

    def boom(key, instance_id):
        raise OSError("offline forever")

    monkeypatch.setattr(manager, "_api_validate", boom)
    manager._revalidate()  # run synchronously in the test
    assert manager.status().kind == KIND_LICENSED  # offline must never revoke


def test_vendor_revocation_clears_license(tmp_path, monkeypatch):
    clock = Clock(datetime(2026, 7, 1))
    manager = make_manager(tmp_path, clock)
    monkeypatch.setattr(
        manager, "_api_activate", lambda key: {"activated": True, "instance": {}}
    )
    manager.activate("KEY-123456")
    clock.now += timedelta(days=90)
    monkeypatch.setattr(
        manager, "_api_validate", lambda key, instance_id: {"valid": False}
    )
    manager._revalidate()
    assert manager.status().kind != KIND_LICENSED


def test_dev_env_bypass(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWSPEECH_DEV", "1")
    assert make_manager(tmp_path).status().kind == KIND_LICENSED


def test_masked_key_never_reveals_full_value(tmp_path, monkeypatch):
    assert "KEY-123456789" not in license_mod._mask("KEY-123456789")
