"""secrets.py: the .env file must be 0600, updates must not eat user lines."""

import os
import stat

from flowspeech import secrets


def test_save_creates_file_with_0600(tmp_path):
    path = secrets.save_keys(tmp_path, {"GROQ_API_KEY": "gsk_test"})
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    assert secrets.read_keys(tmp_path) == {"GROQ_API_KEY": "gsk_test"}


def test_update_preserves_comments_and_unknown_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# my precious comment\n"
        "CUSTOM_VAR=keep-me\n"
        "GROQ_API_KEY=old\n",
        encoding="utf-8",
    )
    secrets.save_keys(tmp_path, {"GROQ_API_KEY": "new"})
    text = env.read_text(encoding="utf-8")
    assert "# my precious comment" in text
    assert "CUSTOM_VAR=keep-me" in text
    assert "GROQ_API_KEY=new" in text
    assert "old" not in text


def test_none_value_removes_key(tmp_path):
    secrets.save_keys(tmp_path, {"OPENAI_API_KEY": "sk-1", "GROQ_API_KEY": "gsk"})
    secrets.save_keys(tmp_path, {"OPENAI_API_KEY": None})
    keys = secrets.read_keys(tmp_path)
    assert "OPENAI_API_KEY" not in keys
    assert keys["GROQ_API_KEY"] == "gsk"


def test_read_handles_quotes_export_and_missing_file(tmp_path):
    assert secrets.read_keys(tmp_path) == {}
    (tmp_path / ".env").write_text(
        'export ANTHROPIC_API_KEY="sk-ant"\nEMPTY=\n', encoding="utf-8"
    )
    assert secrets.read_keys(tmp_path) == {"ANTHROPIC_API_KEY": "sk-ant"}


def test_apply_to_environ_sets_and_unsets(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "stale")
    secrets.apply_to_environ({"GROQ_API_KEY": "fresh", "OPENAI_API_KEY": None})
    assert os.environ["GROQ_API_KEY"] == "fresh"
    assert "OPENAI_API_KEY" not in os.environ
