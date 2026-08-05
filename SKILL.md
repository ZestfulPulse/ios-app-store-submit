---
name: ios-app-store-submit
description: Build, sign, and submit a Flutter/iOS app to the App Store Connect — covers Xcode archive/export, code signing (including headless-Mac keychain workarounds), the `asc` CLI for App Store Connect metadata automation, screenshot handoff, and final review submission. Use when asked to build and upload an iOS app, set up App Store code signing, fix a rejected/failed App Store Connect upload, automate App Store Connect metadata, or submit an app for App Store review. Triggers: "빌드해서 제출", "App Store 제출", "archive and upload", "TestFlight에 올려줘", "asc CLI로 메타데이터".
---

# iOS App Store Build & Submit

End-to-end playbook for taking a Flutter/iOS app from "code is done" to "submitted for App Store review," written for headless/agent-driven Mac environments (no interactive Xcode GUI session, no GUI keychain prompts available). Validated end-to-end on a real submission (2026-08-05) that hit — and worked around — every pitfall documented below.

**This skill is project-agnostic.** Never hardcode bundle IDs, App Store Connect App IDs, Team IDs, or certificate names from a prior run — always derive them from the current project (see Step 0).

## When NOT to use this

- Pure UI/feature work with no build/signing/submission component — just do the work directly.
- If the user has an interactive Xcode session open and wants to do signing themselves — offer to guide them through Xcode's GUI instead of fighting headless keychain limitations for no reason.

## Step 0 — Discover the project

Before anything else, gather facts from the current project (don't ask the user for things you can read yourself):

```bash
# Bundle ID, team ID, current device family
grep -n "PRODUCT_BUNDLE_IDENTIFIER\|DEVELOPMENT_TEAM\|TARGETED_DEVICE_FAMILY" ios/Runner.xcodeproj/project.pbxproj | sort -u

# App version / build number
grep "^version:" pubspec.yaml   # Flutter: X.Y.Z+N

# Is asc CLI already installed and authenticated?
which asc && asc auth status

# Is this app already registered in App Store Connect?
asc apps list --output table
```

If `asc` isn't installed or there's no cached auth, walk the user through generating an App Store Connect API key (they must do this themselves — only the account holder/Admin can):
1. https://appstoreconnect.apple.com/access/integrations/api → generate key → **App Manager** role (least privilege that still covers everything this skill needs) → download the `.p8` immediately (one-time download).
2. Get the file to you as a file (Drive link, etc.), never ask them to paste the raw key text in chat. Save it under `~/.asc/keys/` with `chmod 600`.
3. Register it:
   ```bash
   asc auth login --name "<project>" --key-id "<KEY_ID>" --issuer-id "<ISSUER_ID>" \
     --private-key "~/.asc/keys/AuthKey_<KEY_ID>.p8" --network --bypass-keychain
   ```
   **`--bypass-keychain` is required in headless sessions** — plain `asc auth login` fails with `-25308 User interaction is not allowed` because macOS Keychain wants a GUI unlock prompt that doesn't exist here.

## Step 1 — iOS Simulator does not work for ML/vision-heavy apps on Apple Silicon

If the app uses `google_mlkit_*` (or similar plugins shipping arm64-simulator-incomplete binaries), **the app cannot even install on any iOS Simulator on an Apple Silicon Mac** ("Failed to find matching arch for input file"). Don't waste time debugging this — confirm real-device testing is the only option for that Mac, and check `flutter devices` for a wirelessly-paired iPhone/iPad before assuming none is available.

For screenshots specifically: if simulators are unusable, **don't fabricate screens**. Ask the user to capture the real screens on their device, or use `xcrun devicectl` to install/launch things yourself if the device is paired (see Step 6).

## Step 2 — Code signing (the actual hard part)

### 2a. The core headless-Mac problem

The **login keychain requires interactive unlock** in most agent/headless sessions. Any operation that touches it — `asc auth login` without `--bypass-keychain`, `security import` into `login.keychain`, or even `codesign` using an *existing* identity that's already in `login.keychain` — can fail with `-25308 User interaction is not allowed` or `errSecInternalComponent`. This is true even for identities that work fine when the same Mac is used interactively (e.g., via a prior Xcode session).

**Fix: use a dedicated, non-interactive keychain for the whole session**, exactly like a CI runner would:

```bash
KC_PASS="build-$(date +%s | tail -c 6)"
security create-keychain -p "$KC_PASS" build.keychain
security unlock-keychain -p "$KC_PASS" build.keychain
security set-keychain-settings -lut 21600 build.keychain
security list-keychains -d user -s build.keychain login.keychain
```

Keep `$KC_PASS` around (write it to a gitignored file) — you'll need it again for `security set-key-partition-list`.

### 2b. Generate certificates without ever touching a keychain interactively

`asc certificates create --generate-csr` creates the private key and CSR as **plain files** — no keychain interaction at all — then submits the CSR to Apple:

```bash
asc certificates list --output table   # check what already exists first
asc certificates create --certificate-type IOS_DISTRIBUTION --generate-csr \
  --key-out ./signing/dist.key --csr-out ./signing/dist.csr \
  --common-name "<App> Distribution" --email "<contact-email>"
# For a real-device dev/profile build later, also:
# asc certificates create --certificate-type IOS_DEVELOPMENT --generate-csr ...
```

Fetch/create the matching provisioning profile:

```bash
asc signing fetch --bundle-id "<bundle.id>" --profile-type IOS_APP_STORE \
  --certificate-type IOS_DISTRIBUTION --create-missing --output ./signing
# For device installs: --profile-type IOS_APP_DEVELOPMENT --device "<ASC device ID>"
# (asc devices list to find/confirm the device is already registered)
```

### 2c. Import into build.keychain — OpenSSL 3.x needs `-legacy`

```bash
openssl x509 -inform DER -in ./signing/<serial>.cer -out ./signing/dist.pem
openssl pkcs12 -export -legacy -inkey ./signing/dist.key -in ./signing/dist.pem \
  -out ./signing/dist.p12 -passout pass:temp
```
Without `-legacy`, OpenSSL 3.x's default PKCS12 encryption makes macOS `security import` fail with `"MAC verification failed during PKCS12 import (wrong password?)"` — **the password is fine, it's an algorithm-compatibility issue.**

```bash
security import ./signing/dist.p12 -k build.keychain -P temp -T /usr/bin/codesign -T /usr/bin/security
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KC_PASS" build.keychain
security find-identity -v -p codesigning build.keychain   # confirm it shows up
```

Install the provisioning profile at the standard location:
```bash
UUID=$(security cms -D -i ./signing/<profile>.mobileprovision 2>/dev/null | plutil -extract UUID xml1 -o - - | sed -n 's/.*<string>\(.*\)<\/string>.*/\1/p')
cp ./signing/<profile>.mobileprovision ~/Library/MobileDevice/Provisioning\ Profiles/"$UUID.mobileprovision"
```

### 2d. Scope manual signing to the app target ONLY — never pass signing flags globally

If you pass `CODE_SIGN_STYLE=Manual` etc. as global `xcodebuild` command-line overrides, **every CocoaPods/SPM framework/library target in the build breaks** with errors like `"X does not support provisioning profiles, but provisioning profile Y has been manually specified."` — because those overrides apply to every target in the workspace, including libraries that must never be signed with a profile.

Instead, edit `ios/Runner.xcodeproj/project.pbxproj` and add exactly these three keys **only inside the Runner (app) target's Release/Profile `XCBuildConfiguration` blocks** (there are usually two sets of Debug/Release/Profile blocks in this file — a project-level one and a target-level one; the target-level one is the one that also has `PRODUCT_BUNDLE_IDENTIFIER` in the same block):

```
CODE_SIGN_STYLE = Manual;
CODE_SIGN_IDENTITY = "<exact string from `security find-identity -v -p codesigning build.keychain`>";
PROVISIONING_PROFILE_SPECIFIER = "<profile name>";
```

**Before editing:** `project.pbxproj` indentation is tabs, and the depth is easy to miscount by eye. Verify exact whitespace first:
```bash
python3 -c "
with open('ios/Runner.xcodeproj/project.pbxproj') as f:
    lines = f.readlines()
for i in range(START, END): print(repr(lines[i]))
"
```
then construct the Edit's `old_string` from that exact output — don't hand-type indentation.

Also, use the **exact identity string** from `security find-identity`, not a generic prefix like `"iPhone Developer"` — if both a Development and Distribution identity (or an old login-keychain identity and a new build-keychain one) are visible in the combined search list, a generic prefix can non-deterministically match the wrong one, producing `"Provisioning profile X doesn't include signing certificate Y"`.

Tell codesign which keychain to use for the archive step:
```bash
asc xcode archive --workspace ios/Runner.xcworkspace --scheme Runner --configuration Release \
  --archive-path .asc/artifacts/Runner.xcarchive \
  --xcodebuild-flag="OTHER_CODE_SIGN_FLAGS=--keychain build.keychain"
```

## Step 3 — Archive → Export → Validate → Upload

```bash
asc xcode export-options generate --archive-path .asc/artifacts/Runner.xcarchive \
  --signing-style manual --team-id "<TEAM_ID>" --output-path .asc/artifacts/ExportOptions.plist
```
If this fails with `"manual export options require provisioning profile mappings"`, don't fight it — **write the plist by hand**, it's a small, well-known format:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>teamID</key><string>TEAM_ID</string>
  <key>signingStyle</key><string>manual</string>
  <key>provisioningProfiles</key><dict><key>BUNDLE_ID</key><string>PROFILE_NAME</string></dict>
  <key>signingCertificate</key><string>iPhone Distribution</string>
  <key>uploadSymbols</key><true/>
</dict></plist>
```

```bash
asc xcode export --archive-path .asc/artifacts/Runner.xcarchive \
  --ipa-path .asc/artifacts/Runner.ipa --export-options .asc/artifacts/ExportOptions.plist
```

`asc xcode validate` wraps `altool`, which needs **its own separate credential file** (not the `asc auth` store):
```bash
mkdir -p ~/.appstoreconnect/private_keys
cp ~/.asc/keys/AuthKey_<KEY_ID>.p8 ~/.appstoreconnect/private_keys/
asc xcode validate --ipa .asc/artifacts/Runner.ipa --api-key "<KEY_ID>" --api-issuer "<ISSUER_ID>"
```

Upload and attach to a version:
```bash
asc publish appstore --app "<APP_ID>" --ipa .asc/artifacts/Runner.ipa --version "<X.Y>" --wait
```

If the upload fails, the CLI often only surfaces a bare error code. Get the real reason directly from the API:
```bash
TOKEN=$(asc auth token --confirm 2>/dev/null)
curl -s "https://api.appstoreconnect.apple.com/v1/buildUploads/<UPLOAD_ID>" \
  -H "Authorization: Bearer $TOKEN" | jq '.data.attributes.state'
```
A common real failure: **missing a legacy `Info.plist` usage-description key alongside a newer granular one** — e.g., `NSCalendarsFullAccessUsageDescription` present but plain `NSCalendarsUsageDescription` missing (error 90683). Check every usage-description key the app declares has both the classic and any newer granular variant Apple currently expects.

**Bump the build number for every re-upload.** After editing `pubspec.yaml`'s `+N`, run `flutter build ios --config-only --release` to regenerate `ios/Flutter/Generated.xcconfig` before re-archiving — a plain `flutter pub get` does not refresh it.

## Step 4 — Screenshots

Delegate to the **`app-store-screenshots`** skill for the actual editor. Two things this skill adds on top of that:

- **Don't trust a remembered screenshot size.** Whatever display-size guidance you have (6.9", 6.7", whatever) may be stale. If a real upload rejects a screenshot for wrong dimensions, that error is ground truth — fix the editor's export config to match it immediately, don't argue with it.
- **Don't fabricate screens.** If the simulator can't run the app (Step 1) and a claimed feature has no real screen backing it (e.g., a headline promises something the UI doesn't actually show yet), stop and either add the missing UI for real or renegotiate the shot list with the user — never approximate.

## Step 5 — App Store Connect metadata (what `asc` can and can't do)

**Can automate (public API):**
| Field | Command |
|---|---|
| Name/subtitle/description/keywords/URLs | `asc metadata pull` → edit JSON → `asc metadata validate` → `asc metadata push` |
| Primary category | `asc categories set --app <ID> --primary <CATEGORY>` |
| Content rights | `asc apps update --id <ID> --content-rights DOES_NOT_USE_THIRD_PARTY_CONTENT` |
| Build encryption declaration | `asc builds update --app <ID> --latest --uses-non-exempt-encryption=false` |
| Age rating | `asc age-rating edit --app <ID> --all-none` (then override specific fields if the app actually has relevant content) |
| Copyright | `asc versions update --version-id <ID> --copyright "YYYY Name"` |
| Price (free) | `asc app-setup pricing set --app <ID> --free` |
| Review contact/notes | `asc review details-create --version-id <ID> --contact-first-name ... --contact-phone ...` — **get the real name/phone from the user, never invent placeholder values here** |

**Cannot automate — needs the user in a browser:**
- **App Privacy (data-use declarations)** — not in the public API at all. `asc web privacy` needs an interactive Apple ID browser session; don't attempt it headlessly. Draft the recommended answers for the user, then have them fill it in **and explicitly click Publish** — saving without publishing still blocks submission with `"You must have published answers to your app's data usages"` at the final `review submit` step, and this failure mode isn't visible in `asc validate` beforehand (it only shows as a non-blocking "info" note there).

**Territory/pricing availability has a real API quirk:** `asc pricing availability create --territory X` can fail with an error naming a completely unrelated territory code (changes on every retry) — this isn't user error, it's because App Store Connect's `POST /v2/appAvailabilities` requires the **entire territory catalog** (~175 entries) in the initial creation call, not just the ones you care about. Work around it directly:
```bash
TOKEN=$(asc auth token --confirm 2>/dev/null)
curl -s "https://api.appstoreconnect.apple.com/v1/territories?limit=200" -H "Authorization: Bearer $TOKEN" \
  | jq -r '.data[].id' > /tmp/all_territories.txt
python3 - <<'EOF'
import json
territories = [l.strip() for l in open('/tmp/all_territories.txt') if l.strip()]
WANT_AVAILABLE = {"KOR"}  # <-- set desired territory codes here
data, included = [], []
for t in territories:
    lid = f"${{ta_{t}}}"   # literal "${...}" local-id format, required by the API
    data.append({"type": "territoryAvailabilities", "id": lid})
    included.append({"type": "territoryAvailabilities", "id": lid,
        "attributes": {"available": t in WANT_AVAILABLE},
        "relationships": {"territory": {"data": {"type": "territories", "id": t}}}})
body = {"data": {"type": "appAvailabilities",
    "attributes": {"availableInNewTerritories": False},
    "relationships": {"app": {"data": {"type": "apps", "id": "APP_ID"}},
                       "territoryAvailabilities": {"data": data}}},
    "included": included}
json.dump(body, open('/tmp/avail_body.json', 'w'))
EOF
curl -s -X POST "https://api.appstoreconnect.apple.com/v2/appAvailabilities" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d @/tmp/avail_body.json
```

## Step 6 — Submit

```bash
asc validate --app "<APP_ID>" --version "<X.Y>" --platform IOS   # iterate to 0 blocking errors
asc review submit --app "<APP_ID>" --version "<X.Y>" --build "<BUILD_ID>" --confirm
```
If that wrapper errors with `"does not contain target version"` despite the item genuinely being attached (`asc review items-list --submission <ID>` shows it `READY_FOR_REVIEW`), drop to the lower-level command — it's more reliable:
```bash
asc review submissions-submit --id "<SUBMISSION_ID>" --confirm
```
Confirm with `asc review status --app "<APP_ID>"` — look for `reviewState: WAITING_FOR_REVIEW` and `blockerCount: 0`.

## Step 7 (bonus) — Get a real, standalone-launchable build onto the user's device

Users often expect their personal iPhone to run a normal (non-Xcode-tethered) build once you've done all this work. A plain **Debug** build always needs Xcode/the Dart VM attached to launch — that's expected, not a bug, and no amount of signing fixes it. The fix is running **Profile or Release** mode instead:

```bash
flutter devices   # confirm a wirelessly-paired device
flutter build ios --profile   # or --release; needs its own dev-signing setup per Step 2 if the
                               # Release config is already pointed at an App Store profile
                               # (App Store profiles cannot sideload to an arbitrary device)
```
If `flutter build`/`flutter install` fails with the same keychain issues as Step 2, repeat the Step 2 signing setup with an `IOS_APP_DEVELOPMENT` certificate/profile instead of `IOS_DISTRIBUTION`, applied to the **Profile** (or Debug) target config block instead of Release.

To install without `flutter install` (e.g., if you already have a `.app`/`.ipa`):
```bash
xcrun devicectl device install app --device "<UDID>" "path/to/Runner.app"
xcrun devicectl device process launch --device "<UDID>" "<bundle.id>"
```

## Icon/logo swaps

When the user supplies a new app icon image:
1. **Actually look at it first** (Read tool) before resizing anything — a file that's the right pixel dimensions can still be a marketing mockup with placeholder text ("your name here") rather than an icon design. Confirm before applying.
2. Generate all required sizes from one source with Pillow (bundled: `scripts/gen_app_icons.py`).
3. Every binary change (icon included) needs a build-number bump and a fresh archive/export/upload — icons are baked into the binary, not metadata.

## Bundled scripts

- `scripts/gen_app_icons.py` — regenerates iOS/macOS/Android launcher icons from one source PNG. Edit the paths at the top for the target project, or pass them as arguments if you extend it.
- `scripts/setup_build_keychain.sh` — the Step 2a/2c keychain bootstrap as a single idempotent script (create-or-reuse keychain, unlock, add to search list). Import certificates separately per Step 2b/2c since those are certificate-specific.
