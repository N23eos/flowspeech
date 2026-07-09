"""The single place that reads and writes API keys on disk.

Keys live in `~/.flowspeech/.env` (dotenv format), never in config.yaml and
never in logs. The file is chmod 0600. Editing preserves unknown lines and
comments, so a user who hand-writes extra variables never loses them.

Keychain was considered and deliberately rejected for now: a py2app bundle
re-signed on every build trips Keychain ACL prompts, and a 0600 dotenv in the
home directory is the accepted standard for developer utilities. Revisit after
the app ships signed (SPEC.md §7).
"""

import logging
import os
import re
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FILENAME = ".env"

# Every key the UI may manage. ASR_* are for the "custom endpoint" ASR engine.
KNOWN_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "ASR_API_KEY",
)

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def env_path(data_dir: Path) -> Path:
    return data_dir / ENV_FILENAME


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def read_keys(data_dir: Path) -> dict[str, str]:
    """All KEY=value pairs from the user's .env (empty values skipped)."""
    path = env_path(data_dir)
    if not path.exists():
        return {}
    keys: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LINE_RE.match(line)
        if match:
            value = _parse_value(match.group(2))
            if value:
                keys[match.group(1)] = value
    return keys


def save_keys(data_dir: Path, updates: dict[str, str | None]) -> Path:
    """Write `updates` into the .env file, creating it if needed.

    A value of None (or "") removes the key. Lines for keys not mentioned in
    `updates` — including comments and unknown variables — are preserved
    byte-for-byte. The file always ends up with permissions 0600.
    """
    path = env_path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    original = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(updates)
    lines: list[str] = []
    for line in original:
        match = _LINE_RE.match(line)
        if match and match.group(1) in remaining:
            value = remaining.pop(match.group(1))
            if value:  # replace in place; drop the line when removing
                lines.append(f"{match.group(1)}={value}")
        else:
            lines.append(line)
    for key, value in remaining.items():
        if value:
            lines.append(f"{key}={value}")

    text = "\n".join(lines).rstrip("\n") + "\n" if lines else ""
    # Create with restrictive permissions from the first byte, then enforce
    # 0600 even if the file pre-existed with a looser mode.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def apply_to_environ(keys: dict[str, str | None]) -> None:
    """Push saved keys into the current process so they apply immediately,
    without a restart. A None/"" value unsets the variable."""
    for key, value in keys.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
