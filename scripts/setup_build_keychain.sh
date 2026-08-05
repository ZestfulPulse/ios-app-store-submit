#!/usr/bin/env bash
# Idempotent headless-Mac build-keychain bootstrap for iOS code signing.
# Creates (or reuses) a dedicated keychain outside login.keychain, since login.keychain
# refuses interactive-requiring writes/reads in non-GUI agent sessions.
#
# Usage: source setup_build_keychain.sh [keychain-name] [password-file]
#   keychain-name  default: build.keychain
#   password-file  default: ./.asc/signing/.keychain_pass (created if missing, chmod 600)
#
# After sourcing, $KEYCHAIN and $KC_PASS are set for use by `security import` /
# `security set-key-partition-list` / `codesign --keychain "$KEYCHAIN"` calls.
set -euo pipefail

KEYCHAIN="${1:-build.keychain}"
PASS_FILE="${2:-./.asc/signing/.keychain_pass}"

mkdir -p "$(dirname "$PASS_FILE")"

if [ -f "$PASS_FILE" ]; then
    KC_PASS="$(cat "$PASS_FILE")"
else
    KC_PASS="build-$(head -c 12 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 16)"
    echo "$KC_PASS" > "$PASS_FILE"
    chmod 600 "$PASS_FILE"
fi

if security list-keychains -d user | grep -q "$KEYCHAIN"; then
    echo "Keychain $KEYCHAIN already in search list, unlocking..."
    security unlock-keychain -p "$KC_PASS" "$KEYCHAIN" 2>/dev/null || {
        echo "Existing $KEYCHAIN password doesn't match stored one — recreating." >&2
        security delete-keychain "$KEYCHAIN" 2>/dev/null || true
        security create-keychain -p "$KC_PASS" "$KEYCHAIN"
    }
else
    security create-keychain -p "$KC_PASS" "$KEYCHAIN"
fi

security unlock-keychain -p "$KC_PASS" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"

EXISTING_KEYCHAINS=$(security list-keychains -d user | sed 's/"//g' | tr -d '\n')
if ! echo "$EXISTING_KEYCHAINS" | grep -q "$KEYCHAIN"; then
    security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | sed 's/"//g')
fi

echo "Ready: KEYCHAIN=$KEYCHAIN"
echo "Next: security import <cert.p12> -k \"$KEYCHAIN\" -P <p12-password> -T /usr/bin/codesign -T /usr/bin/security"
echo "Then: security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k \"\$KC_PASS\" \"$KEYCHAIN\""
