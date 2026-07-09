"""Insert text at the cursor of the frontmost app.

Strategy: put the text in the clipboard, synthesize Cmd+V via a low-level
CGEvent, then restore the previous clipboard in the background after the app
has had time to actually paste. Requires the Accessibility permission.
"""

import logging
import threading
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

logger = logging.getLogger(__name__)

V_KEYCODE = 9  # ANSI 'v'
C_KEYCODE = 8  # ANSI 'c'

# How long we wait for the frontmost app to service a synthetic Cmd+C.
# Native apps answer in ~30 ms; Electron apps can take a few hundred.
SELECTION_COPY_TIMEOUT_SECONDS = 0.5
SELECTION_POLL_INTERVAL_SECONDS = 0.02

# Slow apps (Electron etc.) read the clipboard noticeably after the keystroke.
# Restoring earlier makes them paste the OLD clipboard — text "disappears".
CLIPBOARD_RESTORE_DELAY_SECONDS = 2.0

# Small pause between writing the pasteboard and the keystroke.
PASTEBOARD_SETTLE_SECONDS = 0.08


# Bumped on every deliberate clipboard write; lets a pending restore know
# that the clipboard was overwritten on purpose and must not be rolled back.
_clipboard_generation = 0


def _read_clipboard() -> str:
    pasteboard = NSPasteboard.generalPasteboard()
    return pasteboard.stringForType_(NSPasteboardTypeString) or ""


def _write_clipboard(text: str) -> None:
    global _clipboard_generation
    _clipboard_generation += 1
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)


def copy_to_clipboard(text: str) -> bool:
    """Copy `text` to the clipboard permanently (no delayed restore).

    Cancels any pending restore from a recent insert_text so the copied
    text isn't clobbered a moment later. Returns True if verified.
    """
    _write_clipboard(text)
    ok = _read_clipboard() == text
    if not ok:
        logger.error("Clipboard write verification failed")
    return ok


def _press_cmd_key(keycode: int) -> None:
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    key_down = Quartz.CGEventCreateKeyboardEvent(source, keycode, True)
    key_up = Quartz.CGEventCreateKeyboardEvent(source, keycode, False)
    Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(key_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)


def _press_cmd_v() -> None:
    _press_cmd_key(V_KEYCODE)


def capture_selection() -> str | None:
    """Return the currently selected text in the frontmost app, or None.

    Synthesizes Cmd+C and watches NSPasteboard.changeCount: when nothing is
    selected, well-behaved apps do not touch the pasteboard at all, so a
    timeout — not empty-string comparison — is the reliable "no selection"
    signal. The user's clipboard is restored immediately after reading.

    None is also returned for apps that refuse synthetic copy (secure input
    fields); callers must treat None as "no selection", never as an error.
    """
    try:
        pasteboard = NSPasteboard.generalPasteboard()
        previous = _read_clipboard()
        change_count_before = pasteboard.changeCount()
        _press_cmd_key(C_KEYCODE)

        deadline = time.time() + SELECTION_COPY_TIMEOUT_SECONDS
        while time.time() < deadline:
            if pasteboard.changeCount() != change_count_before:
                selection = _read_clipboard()
                _write_clipboard(previous)  # give the user their clipboard back
                return selection or None
            time.sleep(SELECTION_POLL_INTERVAL_SECONDS)
        return None  # nothing selected (or the app ignored the copy)
    except Exception:
        logger.exception("Selection capture failed")
        return None


def frontmost_app_name() -> str:
    """Name of the app that will receive the text (used for stats/formatting)."""
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app.localizedName() if app else "unknown"
    except Exception:
        logger.exception("Could not detect frontmost app")
        return "unknown"


def insert_text(text: str) -> None:
    """Paste `text` into the active window; restore the clipboard later."""
    if not text:
        return

    previous_clipboard = _read_clipboard()
    _write_clipboard(text)
    generation = _clipboard_generation
    time.sleep(PASTEBOARD_SETTLE_SECONDS)
    _press_cmd_v()

    def restore() -> None:
        time.sleep(CLIPBOARD_RESTORE_DELAY_SECONDS)
        # Don't clobber the clipboard if anything (the user, "copy from
        # history", a newer dictation) wrote to it meanwhile.
        if _clipboard_generation == generation and _read_clipboard() == text:
            _write_clipboard(previous_clipboard)

    threading.Thread(target=restore, daemon=True).start()
