"""py2app build config: turns FlowSpeech into a real menu-bar .app.

Dev build (fast, symlinks to source — recommended while iterating):
    .venv/bin/python setup.py py2app -A

Standalone build (self-contained, redistributable):
    .venv/bin/python setup.py py2app

Or just run ./build_app.sh
"""

from setuptools import setup

# Точка входа в корне проекта: alias-сборка кладёт в sys.path папку скрипта,
# поэтому скрипт должен лежать рядом с пакетом flowspeech, а не внутри него.
APP = ["launch.py"]

RESOURCES = [
    "config.yaml",
    "assets/menubar_idle@2x.png",
    "assets/menubar_recording@2x.png",
    "assets/menubar_processing@2x.png",
]

PLIST = {
    "CFBundleName": "FlowSpeech",
    "CFBundleDisplayName": "FlowSpeech",
    "CFBundleIdentifier": "app.flowspeech",
    "CFBundleShortVersionString": "1.0.0",
    "CFBundleVersion": "1.0.0",
    # Menu-bar-only app: no Dock icon, no app switcher entry.
    "LSUIElement": True,
    "NSMicrophoneUsageDescription": (
        "FlowSpeech записывает голос, пока зажата горячая клавиша, "
        "чтобы превратить речь в текст."
    ),
    "NSAppleEventsUsageDescription": (
        "FlowSpeech вставляет распознанный текст в активное приложение."
    ),
    "LSMinimumSystemVersion": "12.0",
}

OPTIONS = {
    "iconfile": "assets/FlowSpeech.icns",
    "resources": RESOURCES,
    "plist": PLIST,
    "packages": ["flowspeech"],
}

setup(
    name="FlowSpeech",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
