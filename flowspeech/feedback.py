"""Feedback log: every dictation's raw vs. cleaned text goes to a JSONL file.

Reviewing this log shows where Whisper or the LLM makes mistakes — words that
belong in the personal dictionary, or prompt rules worth tightening.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

FEEDBACK_FILENAME = "feedback.jsonl"


@dataclass(frozen=True)
class FeedbackEntry:
    created_at: str
    raw_text: str
    clean_text: str
    provider: str
    app_name: str
    language: str


def log_entry(
    data_dir: Path,
    raw_text: str,
    clean_text: str,
    provider: str,
    app_name: str,
    language: str,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    entry = FeedbackEntry(
        created_at=datetime.now().isoformat(),
        raw_text=raw_text,
        clean_text=clean_text,
        provider=provider,
        app_name=app_name,
        language=language,
    )
    path = data_dir / FEEDBACK_FILENAME
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")


def rotate(data_dir: Path, days: int) -> None:
    """Trim feedback.jsonl to the retention window (SPEC §4.2).

    days < 0: keep everything. days == 0: drop all entries. days > 0: keep only
    entries newer than `days` days. Unparseable lines are dropped during a
    rotation pass. Mirrors the history retention applied to stats.db.
    """
    if days < 0:
        return
    path = data_dir / FEEDBACK_FILENAME
    if not path.exists():
        return
    if days == 0:
        path.write_text("", encoding="utf-8")
        return
    cutoff = datetime.now() - timedelta(days=days)
    kept: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            created_at = datetime.fromisoformat(json.loads(line)["created_at"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if created_at >= cutoff:
            kept.append(line)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def read_entries(data_dir: Path, limit: int = 50) -> tuple[FeedbackEntry, ...]:
    """Return the most recent feedback entries, newest last."""
    path = data_dir / FEEDBACK_FILENAME
    if not path.exists():
        return ()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(FeedbackEntry(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue  # a corrupt line must not break the whole log
    return tuple(entries)
