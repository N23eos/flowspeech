"""Dictation statistics in SQLite: sessions, word counts, WPM, per-app usage."""

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

DB_FILENAME = "stats.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    duration_sec REAL NOT NULL,
    raw_text TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    wpm REAL NOT NULL,
    app_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    language TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions (created_at);
"""

WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)


@dataclass(frozen=True)
class SessionRecord:
    created_at: datetime
    duration_sec: float
    raw_text: str
    clean_text: str
    app_name: str
    provider: str
    language: str


@dataclass(frozen=True)
class StatsSummary:
    total_sessions: int
    total_words: int
    total_speaking_sec: float
    average_wpm: float
    top_words: tuple[tuple[str, int], ...]
    words_by_app: tuple[tuple[str, int], ...]


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def calculate_wpm(word_count: int, duration_sec: float) -> float:
    if duration_sec <= 0:
        return 0.0
    return round(word_count / (duration_sec / 60), 1)


class StatsStore:
    """Thin wrapper over SQLite. One connection per operation — the app is
    single-user and low-frequency, simplicity wins over pooling."""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = data_dir / DB_FILENAME
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def record_session(self, session: SessionRecord) -> None:
        words = count_words(session.clean_text)
        wpm = calculate_wpm(words, session.duration_sec)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (created_at, duration_sec, raw_text, clean_text,"
                " word_count, wpm, app_name, provider, language)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session.created_at.isoformat(),
                    session.duration_sec,
                    session.raw_text,
                    session.clean_text,
                    words,
                    wpm,
                    session.app_name,
                    session.provider,
                    session.language,
                ),
            )

    def recent_sessions(self, limit: int = 10) -> tuple[tuple[str, str, str], ...]:
        """Last dictations, newest first: (created_at, app_name, clean_text).

        Purged sessions (blanked text, see purge_texts) are skipped so the
        menu never shows empty rows.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT created_at, app_name, clean_text FROM sessions"
                " WHERE clean_text != '' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(rows)

    def search(
        self, query: str = "", limit: int = 200
    ) -> tuple[tuple[int, str, str, str], ...]:
        """History rows for the settings table, newest first.

        Returns (id, created_at, app_name, clean_text). Blanked (purged) rows
        are excluded. A non-empty query is a case-preserving substring filter
        over both the raw and cleaned text. (SQLite LIKE only folds ASCII case,
        which is good enough for a personal search box.)
        """
        sql = ["SELECT id, created_at, app_name, clean_text FROM sessions",
               "WHERE clean_text != ''"]
        params: list = []
        if query.strip():
            sql.append("AND (clean_text LIKE ? OR raw_text LIKE ?)")
            like = f"%{query.strip()}%"
            params += [like, like]
        sql.append("ORDER BY id DESC LIMIT ?")
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(" ".join(sql), params).fetchall()
        return tuple(rows)

    def delete_session(self, session_id: int) -> None:
        """Remove a single history row entirely."""
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def purge_older_than(self, days: int) -> int:
        """Delete sessions older than `days` days; returns rows removed."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
            return cur.rowcount

    def purge_texts(self) -> int:
        """Blank the stored raw/clean text of every session, keeping the
        aggregate columns (word_count, wpm, app, provider) so statistics
        survive. Returns rows affected. This is the privacy-preserving
        "forget what was said, keep how much" clear."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE sessions SET raw_text = '', clean_text = ''"
                " WHERE clean_text != '' OR raw_text != ''"
            )
            return cur.rowcount

    def summary(self, days: int = 7) -> StatsSummary:
        """Aggregate stats for the last `days` days."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT clean_text, word_count, duration_sec, wpm, app_name"
                " FROM sessions WHERE created_at >= ?",
                (since,),
            ).fetchall()

        word_counter: Counter[str] = Counter()
        app_counter: Counter[str] = Counter()
        total_words = 0
        total_sec = 0.0
        wpm_values = []
        for clean_text, word_count, duration_sec, wpm, app_name in rows:
            word_counter.update(w.lower() for w in WORD_RE.findall(clean_text))
            app_counter[app_name] += word_count
            total_words += word_count
            total_sec += duration_sec
            if wpm > 0:
                wpm_values.append(wpm)

        average_wpm = round(sum(wpm_values) / len(wpm_values), 1) if wpm_values else 0.0
        return StatsSummary(
            total_sessions=len(rows),
            total_words=total_words,
            total_speaking_sec=round(total_sec, 1),
            average_wpm=average_wpm,
            top_words=tuple(word_counter.most_common(20)),
            words_by_app=tuple(app_counter.most_common(10)),
        )
