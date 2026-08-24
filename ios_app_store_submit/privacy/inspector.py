"""Local, read-only privacy-relevant signal inspection.

Three independent, conservative scans live here:

* permission declarations (Info.plist usage-description keys) -- ACCESS only;
* network/backend signals (generic HTTP deps, known tracking-domain
  references, identifiable data-path endpoints) -- POSSIBLE/UNKNOWN
  TRANSMISSION signals only, never proof;
* an explicit local developer attestation file, which is the one place a
  deterministic YES/NO can legitimately come from for transmission,
  collection, linkage, or tracking (analogous to Phase 3's
  ``.asc/app_privacy_published.json``).

None of these scans write anything, call out to a network, or shell out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..readiness.inspector import ProjectInspector
from .models import Confidence, PrivacyEvidence, TriState, tri_state
from .sdk_catalog import GENERIC_HTTP_PACKAGES, dependency_names

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "apple_rules" / "app_privacy_data_types.json"

_TRACKING_DOMAIN_HINT = re.compile(
    r"(google-analytics\.com|app-measurement\.com|facebook\.com/tr|doubleclick\.net|"
    r"adjust\.com|amplitude\.com|mixpanel\.com|segment\.io)",
    re.IGNORECASE,
)
_DATA_PATH_HINT = re.compile(
    r"https?://[^\s'\"]*/(location|analytics|track|telemetry|events?|collect)\b", re.IGNORECASE,
)


def _load_permission_map() -> dict[str, str]:
    data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return data["permission_key_to_data_type"]


PERMISSION_KEY_TO_DATA_TYPE = _load_permission_map()


def inspect_permissions(inspector: ProjectInspector) -> list[PrivacyEvidence]:
    info_path = "ios/Runner/Info.plist"
    values = inspector.plist_values(info_path)
    evidence: list[PrivacyEvidence] = []
    for key, data_type in sorted(PERMISSION_KEY_TO_DATA_TYPE.items()):
        value = values.get(key)
        if not (isinstance(value, str) and value.strip()):
            continue
        evidence.append(PrivacyEvidence(
            evidence_id=f"permission:{key}",
            kind="permission_declaration",
            source_type="Info.plist",
            source_path=info_path,
            observed=value.strip(),
            data_type_candidate=data_type,
            access=TriState.YES,
            transmission=TriState.UNKNOWN,
            collection=TriState.UNKNOWN,
            linked_to_user=TriState.UNKNOWN,
            tracking=TriState.UNKNOWN,
            purpose_candidates=(),
            confidence=Confidence.HIGH,
            requires_user_confirmation=True,
            notes=(
                f"{key} is present in Info.plist. This is evidence of a declared permission "
                "(ACCESS) only; it does not imply collection, tracking, linkage to a user, or "
                "purpose."
            ),
        ))
    return evidence


def inspect_network_signals(inspector: ProjectInspector) -> list[PrivacyEvidence]:
    evidence: list[PrivacyEvidence] = []
    deps = dependency_names(inspector)
    for name in sorted(deps & GENERIC_HTTP_PACKAGES):
        evidence.append(PrivacyEvidence(
            evidence_id=f"network:generic_http:{name}",
            kind="network_http_client",
            source_type="pubspec.yaml",
            observed=name,
            transmission=TriState.UNKNOWN,
            confidence=Confidence.LOW,
            requires_user_confirmation=True,
            notes=(
                f"{name} is a generic HTTP client dependency; its presence alone does not prove "
                "any user data is transmitted off-device."
            ),
        ))

    code_files = [p for p in inspector.all_text_files() if p.suffix.lower() in {".dart", ".swift", ".m", ".mm"}]

    for path, line, text in inspector.search(_TRACKING_DOMAIN_HINT.pattern, code_files)[:10]:
        relative = inspector.relative(path)
        evidence.append(PrivacyEvidence(
            evidence_id=f"network:tracking_domain:{relative}:{line}",
            kind="network_tracking_domain_reference",
            source_type="source",
            source_path=relative,
            observed=text,
            transmission=TriState.UNKNOWN,
            tracking=TriState.UNKNOWN,
            confidence=Confidence.MEDIUM,
            requires_user_confirmation=True,
            notes=(
                "A known analytics/advertising domain reference was found in source; this "
                "indicates a possible network destination, not proven tracking behavior."
            ),
        ))

    for path, line, text in inspector.search(_DATA_PATH_HINT.pattern, code_files)[:10]:
        relative = inspector.relative(path)
        match = _DATA_PATH_HINT.search(text)
        segment = match.group(1).lower() if match else "data"
        evidence.append(PrivacyEvidence(
            evidence_id=f"network:data_path:{relative}:{line}",
            kind="network_identifiable_data_path",
            source_type="source",
            source_path=relative,
            observed=text,
            transmission=TriState.UNKNOWN,
            confidence=Confidence.MEDIUM,
            requires_user_confirmation=True,
            notes=(
                f"An endpoint path referencing {segment} was found; this is an identifiable data "
                "path, not proof that user data leaves the device."
            ),
        ))
    return evidence


def inspect_local_privacy_answers(inspector: ProjectInspector) -> list[PrivacyEvidence]:
    """Read an explicit, developer-authored local attestation file if present.

    This file is never written by this package (see ``fix boundary``); it is
    the one legitimate source of a deterministic YES/NO for transmission,
    collection, linkage, or tracking, because it is an explicit statement
    attributable to the developer rather than an inference from code shape.
    """
    text = inspector.read_text(".asc/app_privacy_answers.json")
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    entries = data.get("data_types", {}) if isinstance(data, dict) else {}
    evidence: list[PrivacyEvidence] = []
    for data_type, fields in sorted(entries.items()) if isinstance(entries, dict) else []:
        if not isinstance(fields, dict):
            continue
        evidence.append(PrivacyEvidence(
            evidence_id=f"local_answer:{data_type}",
            kind="local_privacy_answer_attestation",
            source_type=".asc/app_privacy_answers.json",
            source_path=".asc/app_privacy_answers.json",
            observed=fields,
            data_type_candidate=data_type,
            transmission=tri_state(fields.get("transmission")),
            collection=tri_state(fields.get("collection")),
            linked_to_user=tri_state(fields.get("linked_to_user")),
            tracking=tri_state(fields.get("tracking")),
            purpose_candidates=tuple(fields.get("purposes", [])),
            confidence=Confidence.HIGH,
            requires_user_confirmation=False,
            notes="Explicit local developer attestation of this data type's App Privacy answer; not inferred.",
        ))
    return evidence
