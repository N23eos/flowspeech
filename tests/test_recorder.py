"""Tests for recorder.py.

The PortAudio stream is stubbed out: we drive Recorder._on_audio by hand, exactly
the way PortAudio's callback thread would, and assert on what stop() returns.
"""

import numpy as np
import pytest

from flowspeech.recorder import (
    MIN_CAPTURE_SECONDS,
    SAMPLE_RATE,
    Capture,
    Recorder,
    audio_rms,
)

BLOCK_FRAMES = 1024
BLOCK_SECONDS = BLOCK_FRAMES / SAMPLE_RATE  # ~0.064 s


def _block(amplitude: float = 0.1) -> np.ndarray:
    """One callback's worth of audio, shaped (frames, channels) like PortAudio."""
    return np.full((BLOCK_FRAMES, 1), amplitude, dtype=np.float32)


def _feed(recorder: Recorder, blocks: int, amplitude: float = 0.1) -> None:
    for _ in range(blocks):
        recorder._on_audio(_block(amplitude), BLOCK_FRAMES, None, None)


@pytest.fixture
def recorder(monkeypatch):
    """A Recorder whose stream never touches real hardware."""
    rec = Recorder(tail_seconds=0.0)
    rec.opened = 0
    rec.closed = 0

    def open_stream():
        rec.opened += 1

    def close_stream():
        rec.closed += 1

    monkeypatch.setattr(rec, "_open_stream", open_stream)
    monkeypatch.setattr(rec, "_close_stream", close_stream)
    return rec


def test_audio_rms_of_empty_is_zero():
    assert audio_rms(np.array([], dtype=np.float32)) == 0.0


def test_capture_returns_the_recorded_audio(recorder):
    recorder.start()
    _feed(recorder, 8, amplitude=0.5)

    capture = recorder.stop()

    assert capture.ok
    assert capture.duration_sec == pytest.approx(8 * BLOCK_SECONDS, rel=1e-3)
    assert float(capture.audio.max()) == pytest.approx(0.5)


def test_mic_is_open_only_while_recording(recorder):
    assert (recorder.opened, recorder.closed) == (0, 0)

    recorder.start()
    _feed(recorder, 8)
    assert (recorder.opened, recorder.closed) == (1, 0)

    recorder.stop()
    assert (recorder.opened, recorder.closed) == (1, 1)


def test_each_dictation_opens_a_fresh_stream(recorder):
    """A long-lived stream stays bound to the input device that was default
    when it opened, and records nothing after the user plugs in headphones."""
    for _ in range(3):
        recorder.start()
        _feed(recorder, 8)
        recorder.stop()

    assert recorder.opened == 3
    assert recorder.closed == 3


def test_audio_before_start_is_not_captured(recorder):
    _feed(recorder, 20, amplitude=0.9)  # stray callbacks, no capture running

    recorder.start()
    _feed(recorder, 8, amplitude=0.1)
    capture = recorder.stop()

    assert capture.duration_sec == pytest.approx(8 * BLOCK_SECONDS, rel=1e-3)
    assert float(capture.audio.max()) == pytest.approx(0.1)


def test_failure_to_open_the_mic_leaves_us_idle(monkeypatch):
    rec = Recorder(tail_seconds=0.0)
    monkeypatch.setattr(rec, "_open_stream", lambda: (_ for _ in ()).throw(OSError("no device")))

    with pytest.raises(OSError):
        rec.start()

    assert not rec.is_recording


def test_short_tap_reports_too_short_instead_of_dropping(recorder):
    recorder.start()
    _feed(recorder, 1)  # ~0.064 s

    capture = recorder.stop()

    # The old code returned a bare None here and the dictation vanished.
    assert not capture.ok
    assert capture.reason == "too_short"
    assert capture.duration_sec < MIN_CAPTURE_SECONDS


def test_silent_capture_is_reported_as_silence(recorder):
    recorder.start()
    _feed(recorder, 20, amplitude=0.0)

    capture = recorder.stop()

    assert not capture.ok
    assert capture.reason == "silence"


def test_capture_with_no_callbacks_is_reported(recorder):
    recorder.start()

    capture = recorder.stop()

    assert capture.reason == "no_audio"


def test_stop_without_start_is_harmless(recorder):
    assert recorder.stop() == Capture(None, 0.0, 0.0, reason="not_recording")


def test_double_stop_does_not_resurrect_audio(recorder):
    recorder.start()
    _feed(recorder, 20)

    first = recorder.stop()
    second = recorder.stop()

    assert first.ok
    assert second.reason == "not_recording"
    assert recorder.closed == 1


def test_start_is_idempotent(recorder):
    recorder.start()
    _feed(recorder, 10)
    recorder.start()  # must not clear the chunks collected so far
    _feed(recorder, 10)

    capture = recorder.stop()

    assert capture.duration_sec == pytest.approx(20 * BLOCK_SECONDS, rel=1e-3)
    assert recorder.opened == 1


def test_level_is_zero_when_not_capturing(recorder):
    recorder.start()
    _feed(recorder, 1, amplitude=0.5)
    assert recorder.level == pytest.approx(0.5)

    recorder.stop()
    assert recorder.level == 0.0


def test_cancel_discards_the_capture_and_closes_the_mic(recorder):
    recorder.start()
    _feed(recorder, 20)

    recorder.cancel()

    assert not recorder.is_recording
    assert recorder.closed == 1
    assert recorder.stop().reason == "not_recording"


def test_tail_seconds_keeps_capturing_after_stop_is_requested(monkeypatch):
    """stop() sleeps for tail_seconds; blocks arriving in that window count."""
    rec = Recorder(tail_seconds=0.05)
    monkeypatch.setattr(rec, "_open_stream", lambda: None)
    monkeypatch.setattr(rec, "_close_stream", lambda: None)
    rec.start()
    _feed(rec, 8)

    # Simulate PortAudio delivering one last block while stop() is sleeping.
    def sleep_and_deliver(_seconds):
        _feed(rec, 1, amplitude=0.9)

    monkeypatch.setattr("flowspeech.recorder.time.sleep", sleep_and_deliver)
    capture = rec.stop()

    assert capture.ok
    assert float(capture.audio.max()) == pytest.approx(0.9)
    assert capture.duration_sec == pytest.approx(9 * BLOCK_SECONDS, rel=1e-3)
