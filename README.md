![License](https://img.shields.io/github/license/ZestfulPulse/ios-app-store-submit)
![Stars](https://img.shields.io/github/stars/ZestfulPulse/ios-app-store-submit)
![Last Commit](https://img.shields.io/github/last-commit/ZestfulPulse/ios-app-store-submit)

# ios-app-store-submit

[한국어 README](./README.ko.md)

A [Claude Code](https://claude.com/claude-code) skill that builds, signs, and submits Flutter/iOS apps to App Store Connect — end to end, from `flutter build` to `WAITING_FOR_REVIEW`.

Written for **headless/agent-driven Mac environments**: no interactive Xcode GUI session, no GUI keychain unlock prompts available. Every workaround in here was hit and solved on a real submission, not theorized.

## What it covers

- Discovering a project's bundle ID / team ID / version instead of hardcoding them
- App Store Connect API key setup (`asc auth login --bypass-keychain`)
- Code signing without an interactive keychain: certificate/profile generation via CSR files, a dedicated `build.keychain`, the OpenSSL `-legacy` PKCS12 gotcha, and why signing flags must be scoped to the app target only (never passed globally to `xcodebuild`)
- Archive → export → validate → upload, plus how to pull the *real* reason out of a cryptic `buildUploads` error code
- What App Store Connect metadata the `asc` CLI can automate (name, keywords, pricing, age rating, review contact...) vs. what needs a human in a browser (App Privacy data-use declarations — not in the public API at all)
- A real API quirk in territory/pricing availability (`POST /v2/appAvailabilities` requiring the entire 175-territory catalog on first creation) and how to work around it
- Getting a real, standalone-launchable (non-debug) build onto a physical device
- Icon regeneration and a checklist for spotting a placeholder/mockup image before it gets baked into a build

See [`SKILL.md`](./SKILL.md) for the full playbook.

## Install

Symlink (or clone) this into your Claude Code skills directory:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/cwoneday/ios-app-store-submit ~/.agents/skills/ios-app-store-submit
ln -s ../../.agents/skills/ios-app-store-submit ~/.claude/skills/ios-app-store-submit
```

Claude Code auto-discovers skills under `~/.claude/skills/`. Once linked, it's picked up automatically in any project — no per-project setup.

## Use

From any Flutter/iOS project, just ask Claude Code naturally:

> "Build this and submit it to the App Store"
> "Set up code signing for this app"
> "The App Store upload failed, find out why"
> "Fill in the App Store Connect metadata"

The skill triggers on requests like these. It is project-agnostic — it reads bundle ID, team ID, and version from whatever project it's invoked in, and never assumes a prior project's identifiers.

## Prerequisites

- An Apple Developer Program membership (paid, Admin or App Manager role)
- Xcode installed locally
- The [`asc` CLI](https://github.com/rorkai/app-store-connect-cli-skills) (the skill will guide you through installing/configuring it if missing)
- An App Store Connect API key (`.p8`) — the skill walks you through generating one; store it under `~/.asc/keys/` with `chmod 600`, never paste the raw key into chat

## Bundled scripts

| Script | Purpose |
|---|---|
| `scripts/gen_app_icons.py` | Regenerate iOS/macOS/Android launcher icons from one square source PNG (`pip install Pillow`) |
| `scripts/setup_build_keychain.sh` | Idempotently create/unlock a dedicated `build.keychain` for headless code signing — `source` it to get `$KEYCHAIN`/`$KC_PASS` |

## What this skill will not do for you

- Click "Publish" on the App Store Connect App Privacy questionnaire — Apple doesn't expose this via API
- Guess at your review-contact name/phone or copyright holder — always asks
- Fabricate demo account credentials, screenshots, or an app icon from a mockup file — flags these for your input instead

## License

MIT
