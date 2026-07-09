"""Personal dictionary: user-specific words, names and terms.

Stored as a simple YAML list in <data_dir>/dictionary.yaml. The words are fed
to Whisper as an initial prompt (biases recognition) and to the LLM formatter
(protects correct spelling during cleanup).
"""

import re
from pathlib import Path

import yaml

DICTIONARY_FILENAME = "dictionary.yaml"

DEFAULT_CONTENT = """\
# Personal dictionary for FlowSpeech.
# Add words, names and terms that Whisper gets wrong, one per line.
words:
  - FlowSpeech

# Сниппеты (SPEC §A5): короткая произнесённая фраза → на что её заменить.
# Срабатывает по целым словам, без учёта регистра; финальная пунктуация не
# мешает. Раскомментируй и правь под себя:
# snippets:
#   "моя почта": you@example.com
#   "мой адрес": "г. Москва, ул. Пушкина"
"""


def dictionary_path(data_dir: Path) -> Path:
    return data_dir / DICTIONARY_FILENAME


def ensure_dictionary(data_dir: Path) -> Path:
    """Create a template dictionary file on first run."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = dictionary_path(data_dir)
    if not path.exists():
        path.write_text(DEFAULT_CONTENT, encoding="utf-8")
    return path


def load_words(data_dir: Path) -> tuple[str, ...]:
    """Return dictionary words as an immutable tuple; empty tuple if none."""
    path = dictionary_path(data_dir)
    if not path.exists():
        return ()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    words = raw.get("words") or []
    cleaned = tuple(str(w).strip() for w in words if str(w).strip())
    return cleaned


def load_snippets(data_dir: Path) -> dict[str, str]:
    """Return the snippets mapping (trigger phrase → replacement), or empty.

    Forgiving like load_words: a missing file or a malformed `snippets:` section
    just means "no snippets", never an error.
    """
    path = dictionary_path(data_dir)
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    snippets = raw.get("snippets")
    if not isinstance(snippets, dict):
        return {}
    return {
        str(trigger).strip(): str(value)
        for trigger, value in snippets.items()
        if str(trigger).strip()
    }


def apply_snippets(text: str, snippets: dict[str, str]) -> str:
    """Expand snippet triggers found in `text` (SPEC §A5).

    A trigger matches only as a whole run of words, case-insensitively, so
    "мой" never fires inside "мойка" and trailing punctuation ("моя почта.")
    doesn't block the match. The replacement is inserted verbatim — no regex
    group references — so an email or path can't be mangled by special chars.
    """
    if not text or not snippets:
        return text
    result = text
    for trigger, value in snippets.items():
        words = trigger.split()
        if not words:
            continue
        # \b…\b keeps the match on word boundaries; \s+ between words tolerates
        # whatever spacing the transcript happened to use.
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b"
        result = re.sub(
            pattern, lambda _m, v=value: v, result, flags=re.IGNORECASE | re.UNICODE
        )
    return result


def whisper_prompt(words: tuple[str, ...]) -> str | None:
    """Initial prompt that biases Whisper toward the user's vocabulary.

    Whisper's `initial_prompt` is not an instruction field — the model reads it
    as the transcript of the audio immediately preceding this clip. An English
    lead-in like "Glossary:" therefore nudges a Russian dictation toward English
    and invites the model to echo the prompt back as the transcript. Feed it the
    bare terms and nothing else.
    """
    if not words:
        return None
    return ", ".join(words)
