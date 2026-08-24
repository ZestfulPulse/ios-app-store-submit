"""Conservative, offline SDK/package classification.

Presence of a known package is evidence that a certain SDK category is
integrated. It is never evidence, by itself, that the SDK collects,
transmits, or retains any particular data -- that remains the app
developer's and the SDK vendor's responsibility to state accurately.
"""

from __future__ import annotations

import re

from ..readiness.inspector import ProjectInspector
from .models import Confidence, PrivacyEvidence, Purpose, TriState

# package/pod name -> (category, purpose candidate). Deliberately small and
# conservative; extend only with well-known, unambiguous SDK identities.
KNOWN_SDKS: dict[str, tuple[str, str]] = {
    "firebase_analytics": ("ANALYTICS", Purpose.ANALYTICS.value),
    "google_analytics": ("ANALYTICS", Purpose.ANALYTICS.value),
    "FirebaseAnalytics": ("ANALYTICS", Purpose.ANALYTICS.value),
    "firebase_crashlytics": ("CRASH_REPORTING", Purpose.APP_FUNCTIONALITY.value),
    "FirebaseCrashlytics": ("CRASH_REPORTING", Purpose.APP_FUNCTIONALITY.value),
    "sentry_flutter": ("CRASH_REPORTING", Purpose.APP_FUNCTIONALITY.value),
    "Sentry": ("CRASH_REPORTING", Purpose.APP_FUNCTIONALITY.value),
    "google_mobile_ads": ("ADVERTISING", Purpose.THIRD_PARTY_ADVERTISING.value),
    "GoogleMobileAds": ("ADVERTISING", Purpose.THIRD_PARTY_ADVERTISING.value),
    "facebook_audience_network": ("ADVERTISING", Purpose.THIRD_PARTY_ADVERTISING.value),
    "firebase_auth": ("AUTHENTICATION", Purpose.APP_FUNCTIONALITY.value),
    "FirebaseAuth": ("AUTHENTICATION", Purpose.APP_FUNCTIONALITY.value),
    "google_sign_in": ("AUTHENTICATION", Purpose.APP_FUNCTIONALITY.value),
    "GoogleSignIn": ("AUTHENTICATION", Purpose.APP_FUNCTIONALITY.value),
    "flutter_stripe": ("PAYMENTS", Purpose.APP_FUNCTIONALITY.value),
    "Stripe": ("PAYMENTS", Purpose.APP_FUNCTIONALITY.value),
    "google_maps_flutter": ("MAPS_LOCATION", Purpose.APP_FUNCTIONALITY.value),
    "GoogleMaps": ("MAPS_LOCATION", Purpose.APP_FUNCTIONALITY.value),
    "flutter_facebook_auth": ("SOCIAL", Purpose.APP_FUNCTIONALITY.value),
    "FBSDKCoreKit": ("SOCIAL", Purpose.APP_FUNCTIONALITY.value),
    "cloud_firestore": ("CLOUD_BACKEND", Purpose.APP_FUNCTIONALITY.value),
    "Firebase": ("CLOUD_BACKEND", Purpose.APP_FUNCTIONALITY.value),
}

GENERIC_HTTP_PACKAGES = {"http", "dio", "chopper", "cronet_http"}

_PODFILE_POD_LINE = re.compile(r"^\s*pod\s+['\"]([A-Za-z0-9_+\-/]+)['\"]", re.MULTILINE)
_PODFILE_LOCK_POD_LINE = re.compile(r"^\s{2,4}- ([A-Za-z0-9_+\-/]+)(?:\s*\(|:)", re.MULTILINE)
_PUBSPEC_DEP_NAME = re.compile(r"^ {2}([A-Za-z_][A-Za-z0-9_]*)\s*:")


def dependency_names(inspector: ProjectInspector) -> set[str]:
    """Conservative, text-based dependency-name extraction. Never a claim
    about what any dependency actually does at runtime."""
    names: set[str] = set()
    pubspec = inspector.read_text("pubspec.yaml") or ""
    in_deps = False
    for line in pubspec.splitlines():
        if re.match(r"^dependencies\s*:\s*$", line):
            in_deps = True
            continue
        if in_deps and re.match(r"^\S", line):
            in_deps = False
        if in_deps:
            match = _PUBSPEC_DEP_NAME.match(line)
            if match:
                names.add(match.group(1))
    for relative in ("ios/Podfile", "ios/Podfile.lock"):
        text = inspector.read_text(relative)
        if not text:
            continue
        names.update(_PODFILE_POD_LINE.findall(text))
        names.update(match.split("/")[0] for match in _PODFILE_LOCK_POD_LINE.findall(text))
    return names


def inspect_dependencies(inspector: ProjectInspector) -> list[PrivacyEvidence]:
    names = dependency_names(inspector)
    evidence: list[PrivacyEvidence] = []
    for name in sorted(names):
        if name not in KNOWN_SDKS:
            continue
        category, purpose = KNOWN_SDKS[name]
        evidence.append(PrivacyEvidence(
            evidence_id=f"sdk:{name}",
            kind="sdk_dependency",
            source_type="pubspec.yaml/Podfile",
            observed=name,
            data_type_candidate=None,
            access=TriState.UNKNOWN,
            transmission=TriState.UNKNOWN,
            collection=TriState.UNKNOWN,
            linked_to_user=TriState.UNKNOWN,
            tracking=TriState.UNKNOWN,
            purpose_candidates=(purpose,),
            confidence=Confidence.HIGH,
            requires_user_confirmation=True,
            notes=(
                f"{name} is a known {category.lower().replace('_', ' ')} SDK dependency. Its presence "
                "does not by itself prove what data it collects, transmits, or retains; the app "
                "developer remains responsible for the SDK vendor's actual privacy practices."
            ),
        ))
    return evidence
