# ios-app-store-submit

[🇺🇸 English](README.md) | [🇰🇷 한국어](README.ko.md)

![Release](https://img.shields.io/github/v/release/ZestfulPulse/ios-app-store-submit)
![License](https://img.shields.io/github/license/ZestfulPulse/ios-app-store-submit)
![Stars](https://img.shields.io/github/stars/ZestfulPulse/ios-app-store-submit)
![Last Commit](https://img.shields.io/github/last-commit/ZestfulPulse/ios-app-store-submit)

Claude Code skill for automating iOS App Store submission.


[English README](./README.md)

Flutter/iOS 앱을 `flutter build`부터 `WAITING_FOR_REVIEW`(심사 대기)까지 — 빌드, 코드사이닝, App Store Connect 제출을 전 과정 자동화하는 [Claude Code](https://claude.com/claude-code) 스킬입니다.

**헤드리스/에이전트 기반 Mac 환경**을 위해 작성되었습니다: Xcode GUI 세션도, 키체인 GUI 잠금해제 프롬프트도 없는 환경입니다. 여기 담긴 모든 우회법은 이론이 아니라 실제 심사 제출 과정에서 직접 부딪히고 해결한 것들입니다.

## 다루는 내용

- 프로젝트 번들 ID / 팀 ID / 버전을 하드코딩하지 않고 프로젝트에서 직접 탐지하기
- App Store Connect API 키 설정 (`asc auth login --bypass-keychain`)
- 대화형 키체인 없이 코드사이닝하기: CSR 파일을 통한 인증서/프로파일 생성, 전용 `build.keychain`, OpenSSL `-legacy` PKCS12 함정, 그리고 서명 관련 플래그가 왜 앱 타겟에만 스코핑되어야 하는지(절대 `xcodebuild`에 전역으로 넘기면 안 되는 이유)
- Archive → Export → Validate → Upload, 그리고 알아보기 힘든 `buildUploads` 에러 코드에서 *진짜* 원인을 뽑아내는 방법
- App Store Connect 메타데이터 중 `asc` CLI로 자동화 가능한 것(이름, 키워드, 가격, 연령 등급, 심사 담당자 등)과 사람이 브라우저에서 직접 해야 하는 것(App Privacy 데이터 수집 설문 — 공개 API에 아예 없음)의 구분
- Territory/pricing availability의 실제 API 버그(`POST /v2/appAvailabilities`가 최초 생성 시 175개국 전체 목록을 요구하는 현상)와 그 우회법
- 실물 기기에 Xcode 없이도 바로 실행되는(디버그 아닌) 빌드를 올리는 방법
- 아이콘 일괄 생성, 그리고 목업/placeholder 이미지가 실제 아이콘으로 잘못 반영되기 전에 걸러내는 체크리스트

전체 플레이북은 [`SKILL.md`](./SKILL.md)를 참고하세요.

## 설치

Claude Code 스킬 디렉토리에 클론 후 심볼릭 링크로 연결합니다:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/cwoneday/ios-app-store-submit ~/.agents/skills/ios-app-store-submit
ln -s ../../.agents/skills/ios-app-store-submit ~/.claude/skills/ios-app-store-submit
```

Claude Code는 `~/.claude/skills/` 아래의 스킬을 자동으로 인식합니다. 한 번 연결해두면 어떤 프로젝트에서든 프로젝트별 추가 설정 없이 자동으로 적용됩니다.

## 사용법

어떤 Flutter/iOS 프로젝트에서든 자연스럽게 요청하면 됩니다:

> "이거 빌드해서 App Store에 제출해줘"
> "이 앱 코드사이닝 설정해줘"
> "App Store 업로드가 실패했어, 원인 찾아줘"
> "App Store Connect 메타데이터 채워줘"

이런 요청에 스킬이 자동으로 매칭됩니다. 프로젝트에 특정되지 않은 범용 스킬이라 — 어떤 프로젝트에서 호출되든 번들 ID, 팀 ID, 버전을 그 프로젝트에서 직접 읽어오며, 이전 프로젝트의 값을 가정하지 않습니다.

## 사전 준비물

- Apple Developer Program 유료 멤버십 (Admin 또는 App Manager 권한)
- 로컬에 설치된 Xcode
- [`asc` CLI](https://github.com/rorkai/app-store-connect-cli-skills) (없으면 스킬이 설치/설정을 안내합니다)
- App Store Connect API 키(`.p8`) — 스킬이 발급 과정을 안내합니다. `~/.asc/keys/`에 `chmod 600`으로 저장하고, 원본 키를 채팅에 붙여넣지 마세요

## 번들 스크립트

| 스크립트 | 용도 |
|---|---|
| `scripts/gen_app_icons.py` | 정사각형 소스 PNG 한 장으로 iOS/macOS/Android 런처 아이콘 전체 사이즈를 재생성 (`pip install Pillow` 필요) |
| `scripts/setup_build_keychain.sh` | 헤드리스 코드사이닝용 전용 `build.keychain`을 멱등하게 생성/잠금해제 — `source`로 실행하면 `$KEYCHAIN`/`$KC_PASS` 변수를 이어서 사용 가능 |

## 이 스킬이 대신 해주지 않는 것

- App Store Connect App Privacy 설문의 "게시" 버튼 클릭 — Apple이 API로 노출하지 않음
- 심사 담당자 이름/연락처나 저작권자를 임의로 추정하는 것 — 항상 직접 확인함
- 데모 계정 자격증명, 스크린샷, 목업 파일을 앱 아이콘으로 그대로 가져다 쓰는 것 — 대신 사용자에게 확인을 요청함

## 라이선스

MIT
