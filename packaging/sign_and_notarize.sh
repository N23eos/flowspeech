#!/bin/bash
# Sign, notarize and package FlowSpeech.app into a distributable DMG.
# SPEC.md §C2. Run AFTER `./build_app.sh --full`.
#
# Usage:
#   export TEAM_ID="XXXXXXXXXX"                 # Apple Developer Team ID
#   export APPLE_ID="you@example.com"           # Apple ID email
#   export APP_PASSWORD="abcd-efgh-ijkl-mnop"   # app-specific password
#                                               # (appleid.apple.com → Sign-In and
#                                               #  Security → App-Specific Passwords)
#   ./packaging/sign_and_notarize.sh
#
# Or store credentials once and skip APPLE_ID/APP_PASSWORD:
#   xcrun notarytool store-credentials flowspeech \
#       --apple-id you@example.com --team-id XXXXXXXXXX
#   export KEYCHAIN_PROFILE=flowspeech
#
# Why this script is not three lines: py2app bundles dozens of native
# .so/.dylib files (torch, ctranslate2, PortAudio, numpy). Under the hardened
# runtime EVERY Mach-O inside the bundle must carry a valid Developer ID
# signature, and signing must proceed inside-out (nested code first, the .app
# last). Expect the first notarization of a new dependency set to bounce with
# a per-binary error — re-run, the log URL names the offender.

set -euo pipefail
cd "$(dirname "$0")/.."

APP="dist/FlowSpeech.app"
DMG="dist/FlowSpeech.dmg"
ENTITLEMENTS="packaging/entitlements.plist"
IDENTITY="Developer ID Application: ${SIGN_NAME:-}${SIGN_NAME:+ }(${TEAM_ID:?Set TEAM_ID to your Apple Developer Team ID})"
VOLUME_NAME="FlowSpeech"

[ -d "$APP" ] || { echo "error: $APP not found — run ./build_app.sh --full first" >&2; exit 1; }

# Resolve the signing identity from the keychain if SIGN_NAME wasn't given.
if [ -z "${SIGN_NAME:-}" ]; then
  IDENTITY=$(security find-identity -v -p codesigning \
    | grep "Developer ID Application" | grep "$TEAM_ID" \
    | head -1 | sed 's/.*"\(.*\)"/\1/')
  [ -n "$IDENTITY" ] || { echo "error: no 'Developer ID Application' identity for team $TEAM_ID in the keychain" >&2; exit 1; }
fi
echo "==> Signing identity: $IDENTITY"

sign() {
  codesign --force --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$1"
}

echo "==> 1/6 Signing nested Mach-O binaries (inside-out)…"
# Every .so/.dylib plus extensionless executables. Sort by path depth,
# deepest first, so nested code is always signed before its container.
find "$APP" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 \
  | while IFS= read -r -d '' f; do printf '%d\t%s\0' "$(tr -dc '/' <<<"$f" | wc -c)" "$f"; done \
  | sort -z -t$'\t' -k1,1nr \
  | while IFS=$'\t' read -r -d '' _depth f; do sign "$f"; done

# Frameworks and helper executables (the embedded Python, if present).
find "$APP/Contents/Frameworks" -maxdepth 1 -name "*.framework" -print0 2>/dev/null \
  | while IFS= read -r -d '' fw; do sign "$fw"; done
find "$APP/Contents/MacOS" -type f -print0 \
  | while IFS= read -r -d '' exe; do sign "$exe"; done

echo "==> 2/6 Signing the app bundle…"
sign "$APP"

echo "==> 3/6 Verifying signature…"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> 4/6 Building DMG…"
rm -f "$DMG"
STAGING=$(mktemp -d)
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "$VOLUME_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DMG"
rm -rf "$STAGING"
sign "$DMG"

echo "==> 5/6 Notarizing (this waits for Apple; minutes, sometimes longer)…"
if [ -n "${KEYCHAIN_PROFILE:-}" ]; then
  xcrun notarytool submit "$DMG" --keychain-profile "$KEYCHAIN_PROFILE" --wait
else
  xcrun notarytool submit "$DMG" \
    --apple-id "${APPLE_ID:?Set APPLE_ID or KEYCHAIN_PROFILE}" \
    --password "${APP_PASSWORD:?Set APP_PASSWORD (app-specific password)}" \
    --team-id "$TEAM_ID" --wait
fi
# On "Invalid": xcrun notarytool log <submission-id> [creds] — it names the
# exact binary that was rejected; sign it and re-run this script.

echo "==> 6/6 Stapling the ticket…"
xcrun stapler staple "$DMG"
xcrun stapler staple "$APP" || true  # nice-to-have; the DMG ticket is what ships

echo
echo "Done: $DMG"
echo "Gatekeeper check:  spctl -a -t open --context context:primary-signature -vv $DMG"
