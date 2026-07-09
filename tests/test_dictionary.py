"""Tests for dictionary.py and feedback.py."""

from flowspeech import feedback
from flowspeech.dictionary import (
    apply_snippets,
    ensure_dictionary,
    load_snippets,
    load_words,
    whisper_prompt,
)


def test_ensure_creates_template(tmp_path):
    path = ensure_dictionary(tmp_path)

    assert path.exists()
    assert "FlowSpeech" in load_words(tmp_path)


def test_load_words_missing_file_returns_empty(tmp_path):
    assert load_words(tmp_path) == ()


def test_load_words_skips_blank_entries(tmp_path):
    (tmp_path / "dictionary.yaml").write_text(
        "words:\n  - Kubernetes\n  - '  '\n  - FlowSpeech\n", encoding="utf-8"
    )

    assert load_words(tmp_path) == ("Kubernetes", "FlowSpeech")


def test_whisper_prompt_contains_words():
    prompt = whisper_prompt(("Kubernetes", "FlowSpeech"))

    assert "Kubernetes" in prompt and "FlowSpeech" in prompt


def test_whisper_prompt_empty_is_none():
    assert whisper_prompt(()) is None


# --- Snippets (SPEC.md §A5) --------------------------------------------------

SNIPPETS = {"моя почта": "user@example.com", "мой": "МОЙ-ЗАМЕНА"}


def test_apply_snippets_replaces_whole_phrase():
    assert apply_snippets("моя почта", SNIPPETS) == "user@example.com"


def test_apply_snippets_is_case_insensitive():
    assert apply_snippets("Моя Почта", SNIPPETS) == "user@example.com"


def test_apply_snippets_tolerates_trailing_punctuation():
    assert apply_snippets("напиши моя почта.", SNIPPETS) == "напиши user@example.com."


def test_apply_snippets_ignores_substrings_of_words():
    # "мой" must not fire inside "мойка".
    assert apply_snippets("мойка работает", SNIPPETS) == "мойка работает"


def test_apply_snippets_no_snippets_returns_text():
    assert apply_snippets("любой текст", {}) == "любой текст"


def test_apply_snippets_replacement_is_verbatim():
    # A value with regex-special chars must land unchanged.
    assert apply_snippets("ссылка", {"ссылка": r"a\1b$0"}) == r"a\1b$0"


def test_load_snippets_missing_file_returns_empty(tmp_path):
    assert load_snippets(tmp_path) == {}


def test_load_snippets_reads_section(tmp_path):
    (tmp_path / "dictionary.yaml").write_text(
        'words:\n  - X\nsnippets:\n  "моя почта": me@example.com\n', encoding="utf-8"
    )

    assert load_snippets(tmp_path) == {"моя почта": "me@example.com"}


def test_load_snippets_malformed_section_ignored(tmp_path):
    (tmp_path / "dictionary.yaml").write_text(
        "snippets: not-a-mapping\n", encoding="utf-8"
    )

    assert load_snippets(tmp_path) == {}


def test_feedback_roundtrip(tmp_path):
    # Arrange / Act
    feedback.log_entry(tmp_path, "эээ привет", "Привет.", "claude", "Telegram", "ru")
    feedback.log_entry(tmp_path, "um hello", "Hello.", "ollama", "Slack", "en")

    entries = feedback.read_entries(tmp_path)

    # Assert
    assert len(entries) == 2
    assert entries[0].clean_text == "Привет."
    assert entries[1].provider == "ollama"


def test_feedback_survives_corrupt_line(tmp_path):
    feedback.log_entry(tmp_path, "a", "b", "claude", "App", "en")
    with open(tmp_path / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write("{broken json\n")

    entries = feedback.read_entries(tmp_path)

    assert len(entries) == 1


# --- Feedback rotation (SPEC.md §4.2) ----------------------------------------


def _write_feedback_line(tmp_path, created_at, text="hi"):
    import json
    line = json.dumps({
        "created_at": created_at.isoformat(), "raw_text": text, "clean_text": text,
        "provider": "claude", "app_name": "App", "language": "en",
    })
    with open(tmp_path / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def test_feedback_rotate_keeps_forever_when_negative(tmp_path):
    from datetime import datetime, timedelta
    _write_feedback_line(tmp_path, datetime.now() - timedelta(days=999))

    feedback.rotate(tmp_path, -1)

    assert len(feedback.read_entries(tmp_path)) == 1


def test_feedback_rotate_zero_drops_all(tmp_path):
    feedback.log_entry(tmp_path, "a", "b", "claude", "App", "en")

    feedback.rotate(tmp_path, 0)

    assert feedback.read_entries(tmp_path) == ()


def test_feedback_rotate_days_drops_old_keeps_recent(tmp_path):
    from datetime import datetime, timedelta
    _write_feedback_line(tmp_path, datetime.now() - timedelta(days=40), "старое")
    _write_feedback_line(tmp_path, datetime.now(), "новое")

    feedback.rotate(tmp_path, 30)

    entries = feedback.read_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0].raw_text == "новое"
