"""Update check without Sparkle (SPEC.md §C4).

The whole feature is "compare the running version against a JSON file on the
website, and if it's older, tell the user and open the download page". No
autoupdater, no framework. Every network path is silent on failure — a missing
or unreachable appcast must never surface an error to the user.

Appcast format (https://flowspeech.app/appcast.json):
    {"version": "1.1.0", "url": "https://flowspeech.app/download"}
"""

import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

APPCAST_URL = "https://flowspeech.app/appcast.json"
REQUEST_TIMEOUT_SECONDS = 5  # outbound HTTP must never hang
STAMP_FILENAME = ".last_update_check"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str


def parse_version(text: str) -> tuple[int, ...]:
    """Turn "1.2.10" into (1, 2, 10). Non-numeric junk in a part becomes 0."""
    parts = []
    for chunk in str(text).strip().split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str) -> bool:
    """True if `remote` is a strictly higher version than `local`.

    Compared as tuples of numbers, zero-padded to equal length so "1.2" and
    "1.2.0" compare equal and "1.2.1" beats both.
    """
    remote_v = parse_version(remote)
    local_v = parse_version(local)
    width = max(len(remote_v), len(local_v))
    remote_v += (0,) * (width - len(remote_v))
    local_v += (0,) * (width - len(local_v))
    return remote_v > local_v


def fetch_appcast(url: str = APPCAST_URL) -> dict | None:
    """GET and parse the appcast; None on any error (network, JSON, shape)."""
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.info("Update check could not reach the appcast; ignoring")
        return None
    return data if isinstance(data, dict) else None


def check_for_update(current_version: str, url: str = APPCAST_URL) -> UpdateInfo | None:
    """Return UpdateInfo when a newer version is published, else None (silent)."""
    data = fetch_appcast(url)
    if not data:
        return None
    remote = data.get("version")
    if not remote or not is_newer(str(remote), current_version):
        return None
    return UpdateInfo(version=str(remote), url=str(data.get("url", "")))


def due_for_check(data_dir: Path, now: datetime | None = None) -> bool:
    """True if at least a day has passed since the last background check."""
    now = now or datetime.now()
    path = Path(data_dir) / STAMP_FILENAME
    if not path.exists():
        return True
    try:
        last = datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return True
    return (now - last) >= timedelta(days=1)


def record_check(data_dir: Path, now: datetime | None = None) -> None:
    """Stamp the time of the latest check so the next one waits a day."""
    now = now or datetime.now()
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / STAMP_FILENAME).write_text(now.isoformat(), encoding="utf-8")
