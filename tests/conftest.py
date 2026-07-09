"""Test-suite bootstrap.

`sounddevice` needs the PortAudio shared library at import time. It is present
on any Mac running FlowSpeech, but not necessarily on a headless CI box, and
none of the tests touch real audio hardware anyway. When the real module cannot
load, register a stub so `import flowspeech.recorder` still works.
"""

import sys
import types


def _install_sounddevice_stub() -> None:
    stub = types.ModuleType("sounddevice")

    class InputStream:  # pragma: no cover - never exercised by the tests
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            raise RuntimeError("No audio hardware in the test environment")

        def stop(self):
            pass

        def close(self):
            pass

    stub.InputStream = InputStream
    sys.modules["sounddevice"] = stub


try:
    import sounddevice  # noqa: F401
except (OSError, ImportError):
    _install_sounddevice_stub()
