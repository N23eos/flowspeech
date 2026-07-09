"""Licensing: 7-day trial + one-time purchase key (SPEC.md §C1).

The license source is Lemon Squeezy's public License API. Activation is the
ONLY moment that requires the network; a successful activation is cached in
`~/.flowspeech/license.json` and from then on the app never needs to phone
home. A soft revalidation runs at most once per 30 days, in the background,
and silently ignores every network problem — a purchased license must keep
working on a plane, behind a firewall, and after the vendor's site dies.

The trial marker is HMAC-signed so casually editing the date doesn't work.
Deleting the file or moving the clock defeats it — accepted deliberately:
the app is unobfuscated Python and the protection is priced accordingly.

Swapping Lemon Squeezy for another vendor (Paddle, Gumroad, offline Ed25519)
means implementing one function pair: `_api_activate` / `_api_validate`.
"""

import hashlib
import hmac
import json
import logging
import os
import platform
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

TRIAL_DAYS = 7
REVALIDATE_EVERY_DAYS = 30
HTTP_TIMEOUT_SECONDS = 10

LICENSE_FILENAME = "license.json"
TRIAL_FILENAME = "trial.json"

LS_ACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"
LS_VALIDATE_URL = "https://api.lemonsqueezy.com/v1/licenses/validate"

# Obfuscation, not cryptography: stops "open trial.json, change the date".
_TRIAL_HMAC_KEY = b"flowspeech.trial.v1.5f2c1b"

KIND_LICENSED = "licensed"
KIND_TRIAL = "trial"
KIND_EXPIRED = "expired"

BUY_URL = "https://flowspeech.app/buy"  # shown in expiry messaging


@dataclass(frozen=True)
class LicenseStatus:
    kind: str  # licensed | trial | expired
    days_left: int  # trial days remaining (0 for licensed/expired)
    detail: str  # human-readable menu line

    @property
    def can_dictate(self) -> bool:
        return self.kind != KIND_EXPIRED


def _sign(payload: str) -> str:
    return hmac.new(_TRIAL_HMAC_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _mask(key: str) -> str:
    key = key.strip()
    return f"…{key[-6:]}" if len(key) > 6 else "…"


def _post_form(url: str, fields: dict[str, str]) -> dict:
    """POST form data, return parsed JSON. Lemon Squeezy answers license
    endpoints with JSON even on 4xx (e.g. invalid key), so HTTP errors with
    a JSON body are parsed rather than raised."""
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except Exception:
            raise error from None


class LicenseManager:
    def __init__(self, data_dir: Path, now=datetime.now):
        self._data_dir = data_dir
        self._now = now
        self._lock = threading.Lock()
        data_dir.mkdir(parents=True, exist_ok=True)

    # --- Public API ------------------------------------------------------

    def status(self) -> LicenseStatus:
        """Current state. Never touches the network."""
        if os.environ.get("FLOWSPEECH_DEV"):  # developer convenience
            return LicenseStatus(KIND_LICENSED, 0, "Лицензия: dev-режим")

        cached = self._read_license()
        if cached:
            return LicenseStatus(
                KIND_LICENSED, 0, f"Лицензия активна ({_mask(cached['key'])})"
            )

        days_left = self._trial_days_left()
        if days_left > 0:
            return LicenseStatus(
                KIND_TRIAL, days_left, f"Триал: осталось {days_left} дн."
            )
        return LicenseStatus(
            KIND_EXPIRED, 0, "Триал закончился — введи лицензионный ключ"
        )

    def activate(self, key: str) -> tuple[bool, str]:
        """Activate `key` against Lemon Squeezy. The one call that needs
        network; returns (ok, human-readable message)."""
        key = key.strip()
        if not key:
            return False, "Ключ пустой."
        try:
            payload = self._api_activate(key)
        except Exception as error:
            logger.warning("License activation network failure: %s", error)
            return False, (
                "Не удалось связаться с сервером лицензий. Для активации нужен "
                "интернет (один раз). Проверь сеть и попробуй ещё раз."
            )

        if not payload.get("activated"):
            reason = payload.get("error") or "ключ не принят"
            logger.info("License activation rejected: %s", reason)
            return False, f"Ключ не принят: {reason}"

        instance_id = (payload.get("instance") or {}).get("id", "")
        self._write_license({
            "key": key,
            "instance_id": instance_id,
            "activated_at": self._now().isoformat(),
            "last_validated": self._now().isoformat(),
        })
        logger.info("License activated (%s)", _mask(key))
        return True, "Лицензия активирована. Спасибо за покупку!"

    def revalidate_in_background(self) -> None:
        """Fire-and-forget soft revalidation (at most once per 30 days).

        Network errors change nothing — the license stays valid. Only an
        explicit "valid: false" from the vendor (refund/revocation) clears
        the cached activation.
        """
        threading.Thread(target=self._revalidate, daemon=True).start()

    # --- Vendor calls (the only Lemon Squeezy-specific code) --------------

    def _api_activate(self, key: str) -> dict:
        instance_name = f"{platform.node() or 'mac'}"
        return _post_form(
            LS_ACTIVATE_URL, {"license_key": key, "instance_name": instance_name}
        )

    def _api_validate(self, key: str, instance_id: str) -> dict:
        fields = {"license_key": key}
        if instance_id:
            fields["instance_id"] = instance_id
        return _post_form(LS_VALIDATE_URL, fields)

    # --- Internals ---------------------------------------------------------

    def _revalidate(self) -> None:
        try:
            cached = self._read_license()
            if not cached:
                return
            last = datetime.fromisoformat(cached.get("last_validated", "1970-01-01"))
            if self._now() - last < timedelta(days=REVALIDATE_EVERY_DAYS):
                return
            payload = self._api_validate(cached["key"], cached.get("instance_id", ""))
            if payload.get("valid") is False:
                logger.warning("License reported invalid by vendor; deactivating")
                self._license_path().unlink(missing_ok=True)
                return
            cached["last_validated"] = self._now().isoformat()
            self._write_license(cached)
        except Exception:
            # No network, vendor down, malformed cache — all fine, try again
            # some other month. The license must never break offline.
            logger.debug("License revalidation skipped", exc_info=True)

    def _license_path(self) -> Path:
        return self._data_dir / LICENSE_FILENAME

    def _trial_path(self) -> Path:
        return self._data_dir / TRIAL_FILENAME

    def _read_license(self) -> dict | None:
        path = self._license_path()
        if not path.exists():
            return None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("key"):
                return cached
        except Exception:
            logger.warning("Corrupt license cache; ignoring")
        return None

    def _write_license(self, data: dict) -> None:
        self._license_path().write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def _trial_days_left(self) -> int:
        with self._lock:
            started = self._read_trial_start()
            if started is None:
                started = self._now()
                self._write_trial_start(started)
        elapsed = self._now() - started
        return max(0, TRIAL_DAYS - elapsed.days)

    def _read_trial_start(self) -> datetime | None:
        path = self._trial_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            started = data["started"]
            if hmac.compare_digest(_sign(started), data.get("sig", "")):
                return datetime.fromisoformat(started)
            # Tampered marker: treat the trial as already over rather than
            # granting a fresh one.
            logger.warning("Trial marker signature mismatch")
            return self._now() - timedelta(days=TRIAL_DAYS + 1)
        except Exception:
            logger.warning("Corrupt trial marker; treating trial as expired")
            return self._now() - timedelta(days=TRIAL_DAYS + 1)

    def _write_trial_start(self, started: datetime) -> None:
        payload = started.isoformat()
        self._trial_path().write_text(
            json.dumps({"started": payload, "sig": _sign(payload)}),
            encoding="utf-8",
        )
