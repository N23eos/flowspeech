"""Command Mode (formatter.run_command): the answer-guard is off by design,
but "never touch the user's text on failure" is non-negotiable."""

from unittest.mock import MagicMock, patch

from flowspeech.config import ProviderConfig
from flowspeech.formatter import (
    COMMAND_ANSWER_PROMPT,
    COMMAND_WITH_SELECTION_PROMPT,
    run_command,
)

OLLAMA = ProviderConfig(
    name="ollama", model="llama3.1",
    base_url="http://localhost:11434/v1", api_key=None,
)
CLAUDE = ProviderConfig(
    name="claude", model="claude-haiku-4-5-20251001", base_url=None, api_key="sk-test",
)


def _openai_reply(openai_cls, text):
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=text))
    ]
    openai_cls.return_value = client
    return client


@patch("openai.OpenAI")
def test_selection_is_transformed(openai_cls):
    from flowspeech import formatter

    formatter.reset_clients()
    client = _openai_reply(openai_cls, "Short version.")
    result = run_command("сократи", "A very long paragraph of text", OLLAMA, "TextEdit")
    assert result == "Short version."

    call = client.chat.completions.create.call_args.kwargs
    system = call["messages"][0]["content"]
    user = call["messages"][1]["content"]
    assert system == COMMAND_WITH_SELECTION_PROMPT.format(app_name="TextEdit")
    assert "<command>" in user and "сократи" in user
    assert "<text>" in user and "A very long paragraph" in user


@patch("openai.OpenAI")
def test_no_selection_becomes_inline_answer(openai_cls):
    from flowspeech import formatter

    formatter.reset_clients()
    client = _openai_reply(openai_cls, "4")
    result = run_command("сколько будет два плюс два", None, OLLAMA, "Notes")
    assert result == "4"  # the answer-guard must NOT reject this
    system = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert system == COMMAND_ANSWER_PROMPT.format(app_name="Notes")


@patch("openai.OpenAI")
def test_provider_error_returns_none(openai_cls):
    from flowspeech import formatter

    formatter.reset_clients()
    openai_cls.return_value.chat.completions.create.side_effect = RuntimeError("down")
    assert run_command("сократи", "текст", OLLAMA) is None


@patch("openai.OpenAI")
def test_empty_reply_returns_none(openai_cls):
    from flowspeech import formatter

    formatter.reset_clients()
    _openai_reply(openai_cls, "   ")
    assert run_command("сократи", "текст", OLLAMA) is None


def test_blank_command_returns_none_without_network():
    assert run_command("   ", "текст", OLLAMA) is None


@patch("anthropic.Anthropic")
def test_claude_path(anthropic_cls):
    from flowspeech import formatter

    formatter.reset_clients()
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="Done.")]
    anthropic_cls.return_value = client
    assert run_command("translate to english", "привет", CLAUDE) == "Done."
