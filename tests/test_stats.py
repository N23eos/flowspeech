"""Tests for stats.py."""

from datetime import datetime, timedelta

from flowspeech.stats import SessionRecord, StatsStore, calculate_wpm, count_words


def make_session(clean_text="привет мир как дела", duration=6.0, app="Telegram",
                 created_at=None):
    return SessionRecord(
        created_at=created_at or datetime.now(),
        duration_sec=duration,
        raw_text="эээ " + clean_text,
        clean_text=clean_text,
        app_name=app,
        provider="claude",
        language="ru",
    )


def test_count_words_handles_russian_and_english():
    assert count_words("привет world, как dela-2?") == 4


def test_wpm_calculation():
    # 20 words in 30 seconds = 40 wpm
    assert calculate_wpm(20, 30.0) == 40.0


def test_wpm_zero_duration_is_safe():
    assert calculate_wpm(10, 0.0) == 0.0


def test_record_and_summarize_sessions(tmp_path):
    # Arrange
    store = StatsStore(tmp_path)
    store.record_session(make_session("привет мир", duration=3.0, app="Telegram"))
    store.record_session(make_session("привет код", duration=3.0, app="VS Code"))

    # Act
    summary = store.summary(days=1)

    # Assert
    assert summary.total_sessions == 2
    assert summary.total_words == 4
    top = dict(summary.top_words)
    assert top["привет"] == 2
    assert dict(summary.words_by_app) == {"Telegram": 2, "VS Code": 2}


def test_summary_empty_store(tmp_path):
    store = StatsStore(tmp_path)

    summary = store.summary()

    assert summary.total_sessions == 0
    assert summary.average_wpm == 0.0


# --- History: search / delete / purge (SPEC.md §4.2) -------------------------


def test_search_returns_rows_newest_first(tmp_path):
    store = StatsStore(tmp_path)
    store.record_session(make_session("первая диктовка"))
    store.record_session(make_session("вторая диктовка"))

    rows = store.search()

    assert len(rows) == 2
    assert rows[0][3] == "вторая диктовка"  # newest first
    assert isinstance(rows[0][0], int)  # id present for delete


def test_search_filters_by_substring(tmp_path):
    store = StatsStore(tmp_path)
    store.record_session(make_session("купить молоко"))
    store.record_session(make_session("позвонить маме"))

    rows = store.search("молоко")

    assert len(rows) == 1
    assert rows[0][3] == "купить молоко"


def test_delete_session_removes_row(tmp_path):
    store = StatsStore(tmp_path)
    store.record_session(make_session("удали меня"))
    session_id = store.search()[0][0]

    store.delete_session(session_id)

    assert store.search() == ()


def test_purge_older_than_deletes_old_sessions(tmp_path):
    store = StatsStore(tmp_path)
    old = datetime.now() - timedelta(days=40)
    store.record_session(make_session("старое", created_at=old))
    store.record_session(make_session("новое"))

    removed = store.purge_older_than(30)

    assert removed == 1
    rows = store.search()
    assert len(rows) == 1 and rows[0][3] == "новое"


def test_purge_texts_blanks_text_but_keeps_stats(tmp_path):
    store = StatsStore(tmp_path)
    store.record_session(make_session("один два три", duration=6.0))

    affected = store.purge_texts()

    assert affected == 1
    assert store.search() == ()  # text gone, row hidden from history
    # Aggregate stats survive: the word counts were stored at record time.
    assert store.summary(days=1).total_words == 3
