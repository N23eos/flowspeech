"""FlowSpeech — local voice dictation for macOS.

Hold right option, speak, release — clean text appears at your cursor.
Whisper runs locally; text cleanup goes through Claude/OpenAI/DeepSeek/Ollama.
"""

# Single source of truth for the running version; keep in sync with the
# CFBundleShortVersionString in setup.py.
__version__ = "1.0.0"
