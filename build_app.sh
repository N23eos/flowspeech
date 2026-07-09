#!/bin/bash
# Build FlowSpeech.app.
#
#   ./build_app.sh          — dev build (alias mode: быстро, ссылки на исходники)
#   ./build_app.sh --full   — standalone build (можно раздавать, дольше)
#
# После сборки: open dist/FlowSpeech.app
# macOS спросит разрешения Микрофон и Accessibility уже у FlowSpeech,
# а не у Терминала.

set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python

$PY -c "import py2app" 2>/dev/null || {
  echo "Устанавливаю py2app…"
  uv pip install py2app --python $PY 2>/dev/null || $PY -m pip install py2app
}

[ -f assets/FlowSpeech.icns ] || $PY assets/make_icons.py

rm -rf build dist

if [ "${1:-}" = "--full" ]; then
  $PY setup.py py2app
else
  $PY setup.py py2app -A
fi

echo
echo "Готово: dist/FlowSpeech.app"
echo "Запуск:  open dist/FlowSpeech.app"
echo "В /Applications:  cp -r dist/FlowSpeech.app /Applications/"
