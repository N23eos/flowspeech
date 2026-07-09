"""First-run onboarding window (SPEC.md §C3).

Shown once (gated by a flag file in the data dir): live Microphone /
Accessibility status rows with deep-links into System Settings, refreshed on a
timer, and a final "you're ready" line once both are granted.

The AppKit imports are deliberately lazy — kept inside show_onboarding — so the
flag-file and permission helpers can be imported and unit-tested on a machine
without a display server. Style mirrors settings.py.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

FLAG_FILENAME = ".onboarding_done"

# Deep links straight to the relevant System Settings privacy panes.
MIC_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
AX_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

WIDTH, HEIGHT = 480, 420


def onboarding_needed(data_dir: Path) -> bool:
    """True until the onboarding window has been shown once."""
    return not (Path(data_dir) / FLAG_FILENAME).exists()


def mark_onboarding_seen(data_dir: Path) -> None:
    """Record that onboarding has run so it never shows again."""
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / FLAG_FILENAME).write_text("done\n", encoding="utf-8")


def microphone_authorized() -> bool:
    """True if this process may capture the microphone.

    Can't-tell degrades to True: a false negative would nag a user who has
    already granted access, which is worse than staying quiet.
    """
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        # AVAuthorizationStatusAuthorized == 3
        return AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio) == 3
    except Exception:
        logger.exception("Microphone authorization check failed")
        return True


def _open_settings(url: str) -> None:
    subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_controller_cls = None  # built once, cached (an ObjC class can't be re-registered)
_controllers = []       # keep controllers alive while their windows are open


def _get_controller_cls():
    global _controller_cls
    if _controller_cls is not None:
        return _controller_cls

    import objc
    from Foundation import NSMakeRect, NSObject, NSTimer

    from AppKit import (
        NSApp,
        NSBackingStoreBuffered,
        NSColor,
        NSWindow,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskTitled,
    )

    from flowspeech import uikit as ui
    from flowspeech.hotkey import is_accessibility_trusted

    green = NSColor.systemGreenColor()
    grey = NSColor.tertiaryLabelColor()
    body_width = WIDTH - 2 * ui.MARGIN

    def status_row(icon, heading, subtitle, button):
        text = ui.vstack([ui.label(heading), ui.secondary(subtitle)], spacing=1)
        return ui.hstack([icon, text, ui.spacer(), button], spacing=12)

    class _OnboardingController(NSObject):
        def initWithHotkey_(self, hotkey_label):
            self = objc.super(_OnboardingController, self).init()
            if self is None:
                return None
            self._hotkey_label = hotkey_label
            self._window = None
            self._timer = None
            self._mic_icon = None
            self._ax_icon = None
            self._done_label = None
            return self

        def present(self):
            window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, WIDTH, HEIGHT),
                NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
                NSBackingStoreBuffered,
                False,
            )
            window.setTitle_("Добро пожаловать в FlowSpeech")
            window.setReleasedWhenClosed_(False)
            window.center()
            window.setDelegate_(self)

            self._mic_icon = ui.symbol_view("circle", color=grey, point_size=18)
            self._ax_icon = ui.symbol_view("circle", color=grey, point_size=18)
            mic_row = status_row(
                self._mic_icon, "Микрофон", "Слышать вашу речь во время записи",
                ui.push_button("Открыть", lambda _s: _open_settings(MIC_URL)),
            )
            ax_row = status_row(
                self._ax_icon, "Универсальный доступ",
                "Горячая клавиша и вставка текста",
                ui.push_button("Открыть", lambda _s: _open_settings(AX_URL)),
            )

            self._done_label = ui.title("")
            privacy = ui.wrapping(ui.secondary(
                "Приватность: микрофон включается только на время записи. "
                "Распознавание и очистка идут локально, пока в меню не выбран "
                "облачный провайдер. Полностью офлайн — «🔒 Приватный режим».",
            ), body_width)

            body = ui.vstack([
                ui.title("Добро пожаловать в FlowSpeech"),
                ui.wrapping(ui.secondary(
                    "Осталось выдать два разрешения macOS. Статусы обновляются сами."),
                    body_width),
                ui.divider(),
                mic_row,
                ax_row,
                ui.divider(),
                self._done_label,
                privacy,
            ], spacing=16, fill=True)
            ui.pin(body, window.contentView())

            self._window = window
            window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
            self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                1.0, True, lambda _t: self._refresh()
            )
            self._refresh()

        def _refresh(self):
            mic = microphone_authorized()
            ax = is_accessibility_trusted()
            self._set_icon(self._mic_icon, mic)
            self._set_icon(self._ax_icon, ax)
            if mic and ax:
                self._done_label.setStringValue_(
                    f"Готово! Поставьте курсор в любое поле, зажмите "
                    f"{self._hotkey_label} и говорите."
                )
                self._done_label.setTextColor_(green)
            else:
                self._done_label.setStringValue_("Дайте оба разрешения — окно обновится само.")
                self._done_label.setTextColor_(NSColor.secondaryLabelColor())

        @staticmethod
        def _set_icon(icon_view, ok):
            from AppKit import NSImage

            name = "checkmark.circle.fill" if ok else "circle"
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
            if image is not None:
                icon_view.setImage_(image)
            icon_view.setContentTintColor_(green if ok else grey)

        def windowWillClose_(self, _notification):
            if self._timer is not None:
                self._timer.invalidate()
                self._timer = None

    _controller_cls = _OnboardingController
    return _controller_cls


def show_onboarding(data_dir: Path, hotkey_label: str = "правый ⌥") -> None:
    """Open the first-run window and mark onboarding as seen (once only)."""
    mark_onboarding_seen(data_dir)
    controller = _get_controller_cls().alloc().initWithHotkey_(hotkey_label)
    _controllers.append(controller)
    controller.present()
