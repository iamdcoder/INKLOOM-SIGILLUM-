"""Immutable, filesystem-backed Brand Knowledge Pack version and draft store.

The transactional database remains the review/audit source of truth. This store
keeps pack binaries and JSON snapshots versioned outside application code, with
an atomic active-version pointer and optimistic concurrency checks.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import uuid4

from sigillum.modules.knowledge.brand_pack import BrandPack

SECTION_NAMES = {"brand", "facts", "policies", "terminology", "voice", "assets"}
SECTION_FILES = {
    "brand": "brand.json",
    "facts": "facts.json",
    "policies": "policies.json",
    "terminology": "terminology.json",
    "voice": "voice.json",
    "assets": "asset_manifest.json",
}
ALLOWED_SEVERITIES = {"blocking", "review_required", "suggestion", "informational"}
ALLOWED_RECORD_STATUSES = {"approved", "draft", "not_approved", "rejected", "superseded"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()


def _safe_component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value or "") or value in {".", ".."}:
        raise ValueError("Invalid storage identifier")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class KnowledgePackStore:
    """Stores per-tenant pack drafts and immutable published versions."""

    def __init__(self, seed_root: Path, root: Path):
        self.seed_root = Path(seed_root)
        self.root = Path(root)
        self._lock = threading.RLock()

    def _tenant_root(self, tenant_id: str) -> Path:
        return self.root / _safe_component(tenant_id)

    def _pack_root(self, tenant_id: str, pack_id: str) -> Path:
        return self._tenant_root(tenant_id) / _safe_component(pack_id)

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_snapshot(self, destination: Path, snapshot: dict[str, Any], copy_assets_from: Path | None = None) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for section, filename in SECTION_FILES.items():
            value = snapshot[section]
            if section == "facts":
                value = {"schema_version": "1.0.0", "facts": value}
            elif section == "policies":
                value = {"schema_version": "1.0.0", "policies": value}
            _write_json_atomic(destination / filename, value)
        asset_source = copy_assets_from / "assets" if copy_assets_from else self.seed_root / "assets"
        if asset_source.exists():
            target_assets = destination / "assets"
            if target_assets.exists():
                shutil.rmtree(target_assets)
            shutil.copytree(asset_source, target_assets)

    def _snapshot_from_root(self, root: Path) -> dict[str, Any]:
        pack = BrandPack(root=root)
        return pack.snapshot()

    def ensure_initialized(self, tenant_id: str) -> Path:
        """Create a tenant's first immutable version from the synthetic seed pack."""
        with self._lock:
            seed_pack = BrandPack(root=self.seed_root)
            pack_id = str(seed_pack.brand.get("pack_id", ""))
            if not pack_id:
                raise ValueError("Seed Brand Knowledge Pack has no pack_id")
            pack_root = self._pack_root(tenant_id, pack_id)
            active_pointer = pack_root / "active.json"
            if active_pointer.exists():
                pointer = self._read_json(active_pointer)
                active_root = pack_root / "versions" / _safe_component(pointer["version_id"])
                if active_root.exists():
                    return active_root
                raise RuntimeError("Active Brand Knowledge Pack pointer references a missing version")

            snapshot = seed_pack.snapshot()
            self._validate(snapshot, require_identity=True)
            version_id = "v0001"
            version_root = pack_root / "versions" / version_id
            self._write_snapshot(version_root, snapshot, copy_assets_from=self.seed_root)
            fingerprint = _canonical_hash(snapshot)
            _write_json_atomic(version_root / "version.json", {
                "version_id": version_id,
                "pack_id": pack_id,
                "pack_version": str(snapshot["brand"].get("pack_version", "1.0.0")),
                "fingerprint": fingerprint,
                "status": "PUBLISHED",
                "created_at": _now(),
                "created_by": "system-seed",
                "base_version_id": None,
            })
            _write_json_atomic(active_pointer, {
                "version_id": version_id,
                "fingerprint": fingerprint,
                "activated_at": _now(),
            })
            return version_root

    def active_root(self, tenant_id: str) -> Path:
        # Resolve pack_id from configured seed so tenants cannot select arbitrary packs.
        seed_pack = BrandPack(root=self.seed_root)
        pack_root = self._pack_root(tenant_id, str(seed_pack.brand["pack_id"]))
        self.ensure_initialized(tenant_id)
        pointer = self._read_json(pack_root / "active.json")
        return pack_root / "versions" / _safe_component(pointer["version_id"])

    def active_pack(self, tenant_id: str) -> BrandPack:
        return BrandPack(root=self.active_root(tenant_id))

    def active_metadata(self, tenant_id: str) -> dict[str, Any]:
        root = self.active_root(tenant_id)
        metadata = self._read_json(root / "version.json")
        pointer = self._read_json(root.parent.parent / "active.json")
        metadata["is_active"] = True
        metadata["fingerprint"] = pointer.get("fingerprint", metadata.get("fingerprint"))
        return metadata

    def list_versions(self, tenant_id: str) -> list[dict[str, Any]]:
        active = self.active_metadata(tenant_id)
        versions_root = self.active_root(tenant_id).parent
        rows: list[dict[str, Any]] = []
        for version_dir in versions_root.iterdir():
            metadata_file = version_dir / "version.json"
            if version_dir.is_dir() and metadata_file.exists():
                row = self._read_json(metadata_file)
                row["is_active"] = row.get("version_id") == active.get("version_id")
                rows.append(row)
        return sorted(rows, key=lambda item: item.get("created_at", ""), reverse=True)

    def _draft_path(self, tenant_id: str, draft_id: str) -> Path:
        return self._tenant_root(tenant_id) / "drafts" / f"{_safe_component(draft_id)}.json"

    def create_draft(self, tenant_id: str, actor_id: str) -> dict[str, Any]:
        with self._lock:
            active_root = self.active_root(tenant_id)
            active_meta = self._read_json(active_root / "version.json")
            snapshot = self._snapshot_from_root(active_root)
            draft = {
                "draft_id": str(uuid4()),
                "pack_id": active_meta["pack_id"],
                "base_version_id": active_meta["version_id"],
                "base_fingerprint": active_meta["fingerprint"],
                "status": "DRAFT",
                "created_at": _now(),
                "created_by": actor_id,
                "updated_at": _now(),
                "updated_by": actor_id,
                "snapshot": snapshot,
                "validation": None,
            }
            _write_json_atomic(self._draft_path(tenant_id, draft["draft_id"]), draft)
            return draft

    def get_draft(self, tenant_id: str, draft_id: str) -> dict[str, Any]:
        path = self._draft_path(tenant_id, draft_id)
        if not path.exists():
            raise FileNotFoundError("Draft Knowledge Pack not found")
        return self._read_json(path)

    def update_section(self, tenant_id: str, draft_id: str, section: str, content: Any, actor_id: str) -> dict[str, Any]:
        if section not in SECTION_NAMES:
            raise ValueError(f"Unsupported Knowledge Pack section: {section}")
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack versions are immutable")
            draft["snapshot"][section] = content
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id), draft)
            return draft

    def validate_draft(self, tenant_id: str, draft_id: str) -> dict[str, Any]:
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id)
            errors = self._validate(draft.get("snapshot"), require_identity=True, base_brand_id=None)
            active_root = self.active_root(tenant_id)
            active_pack = BrandPack(root=active_root)
            active_brand_id = active_pack.brand.get("brand_id")
            draft_brand_id = (draft.get("snapshot", {}).get("brand") or {}).get("brand_id")
            if draft_brand_id != active_brand_id:
                errors.append({"code": "BRAND_ID_IMMUTABLE", "path": "brand.brand_id", "message": "A draft cannot change the active brand identity."})
            active_pack_id = active_pack.brand.get("pack_id")
            draft_pack_id = (draft.get("snapshot", {}).get("brand") or {}).get("pack_id")
            if draft_pack_id != active_pack_id:
                errors.append({"code": "PACK_ID_IMMUTABLE", "path": "brand.pack_id", "message": "A draft cannot change the Brand Knowledge Pack identity."})
            assets = (draft.get("snapshot", {}).get("assets") or {}).get("approved_assets", [])
            for index, asset in enumerate(assets if isinstance(assets, list) else []):
                file_path = asset.get("file_path") if isinstance(asset, dict) else None
                if file_path:
                    candidate = active_root / Path(str(file_path))
                    if not candidate.is_file():
                        errors.append({"code": "ASSET_FILE_MISSING", "path": f"assets.approved_assets[{index}].file_path", "message": "The referenced approved asset file is not present in the active asset store. Binary asset upload is not enabled in this build."})
            result = {"valid": not errors, "errors": errors, "warnings": [], "validated_at": _now()}
            draft["validation"] = result
            draft["status"] = "VALIDATED" if not errors else "DRAFT"
            draft["updated_at"] = _now()
            _write_json_atomic(self._draft_path(tenant_id, draft_id), draft)
            return result

    def publish_draft(self, tenant_id: str, draft_id: str, actor_id: str) -> dict[str, Any]:
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id)
            if draft.get("status") != "VALIDATED" or not (draft.get("validation") or {}).get("valid"):
                raise ValueError("Validate the draft successfully before publishing")
            active_root = self.active_root(tenant_id)
            active_meta = self._read_json(active_root / "version.json")
            if active_meta["version_id"] != draft.get("base_version_id"):
                raise RuntimeError("This draft is stale because another Knowledge Pack version was published. Create a new draft from the active version.")
            snapshot = draft["snapshot"]
            errors = self._validate(snapshot, require_identity=True)
            if errors:
                raise ValueError("Draft validation is no longer valid")
            current_n = int(active_meta["version_id"].lstrip("v"))
            version_id = f"v{current_n + 1:04d}"
            pack_root = active_root.parent.parent
            version_root = pack_root / "versions" / version_id
            if version_root.exists():
                raise RuntimeError("Version identifier collision; publication aborted")
            self._write_snapshot(version_root, snapshot, copy_assets_from=active_root)
            new_pack_version = self._next_semver(str(active_meta.get("pack_version", "1.0.0")))
            snapshot["brand"]["pack_version"] = new_pack_version
            # Rewrite brand.json after setting its immutable published version.
            _write_json_atomic(version_root / "brand.json", snapshot["brand"])
            fingerprint = _canonical_hash(snapshot)
            metadata = {
                "version_id": version_id,
                "pack_id": draft["pack_id"],
                "pack_version": new_pack_version,
                "fingerprint": fingerprint,
                "status": "PUBLISHED",
                "created_at": _now(),
                "created_by": actor_id,
                "base_version_id": active_meta["version_id"],
                "draft_id": draft_id,
            }
            _write_json_atomic(version_root / "version.json", metadata)
            # Atomic pointer swap: readers see either the previous or new complete version.
            _write_json_atomic(pack_root / "active.json", {
                "version_id": version_id,
                "fingerprint": fingerprint,
                "activated_at": _now(),
            })
            draft["status"] = "PUBLISHED"
            draft["published_version_id"] = version_id
            draft["published_fingerprint"] = fingerprint
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id), draft)
            return metadata

    @staticmethod
    def _next_semver(version: str) -> str:
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
        if not match:
            return "1.0.1"
        major, minor, patch = (int(part) for part in match.groups())
        return f"{major}.{minor}.{patch + 1}"

    @staticmethod
    def _validate(snapshot: Any, require_identity: bool, base_brand_id: str | None = None) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        if not isinstance(snapshot, dict):
            return [{"code": "INVALID_SNAPSHOT", "path": "snapshot", "message": "Snapshot must be a JSON object."}]

        def add(code: str, path: str, message: str) -> None:
            errors.append({"code": code, "path": path, "message": message})

        brand = snapshot.get("brand")
        if not isinstance(brand, dict):
            add("BRAND_REQUIRED", "brand", "Brand metadata must be a JSON object.")
            brand = {}
        for field in ("pack_id", "brand_id", "brand_name", "pack_version"):
            if require_identity and not str(brand.get(field, "")).strip():
                add("BRAND_FIELD_REQUIRED", f"brand.{field}", f"{field} is required.")
        if not isinstance(brand.get("channels"), list) or not brand.get("channels"):
            add("CHANNELS_REQUIRED", "brand.channels", "At least one supported channel is required.")
        if not isinstance(brand.get("supported_locales"), list) or not brand.get("supported_locales"):
            add("LOCALES_REQUIRED", "brand.supported_locales", "At least one supported locale is required.")

        facts = snapshot.get("facts")
        if not isinstance(facts, list):
            add("FACTS_INVALID", "facts", "Facts must be an array.")
            facts = []
        seen: set[str] = set()
        for index, fact in enumerate(facts):
            path = f"facts[{index}]"
            if not isinstance(fact, dict):
                add("FACT_INVALID", path, "Each fact must be a JSON object.")
                continue
            record_id = str(fact.get("fact_id", "")).strip()
            if not record_id:
                add("FACT_ID_REQUIRED", f"{path}.fact_id", "Every fact requires a fact_id.")
            elif record_id in seen:
                add("DUPLICATE_FACT_ID", f"{path}.fact_id", f"Duplicate fact_id: {record_id}.")
            seen.add(record_id)
            if fact.get("status", "draft") not in ALLOWED_RECORD_STATUSES:
                add("FACT_STATUS_INVALID", f"{path}.status", "Unsupported fact status.")
            if fact.get("status") == "approved" and ("value" not in fact or not fact.get("predicate")):
                add("APPROVED_FACT_INCOMPLETE", path, "Approved facts require a predicate and value.")
            temporal_values: dict[str, datetime] = {}
            for temporal_field in ("valid_from", "valid_until", "recorded_at", "recorded_from", "recorded_until", "superseded_at"):
                raw_value = fact.get(temporal_field)
                if raw_value in (None, ""):
                    continue
                if not isinstance(raw_value, str):
                    add("FACT_TEMPORAL_VALUE_INVALID", f"{path}.{temporal_field}", "Temporal values must be timezone-aware ISO-8601 strings.")
                    continue
                try:
                    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                except ValueError:
                    add("FACT_TEMPORAL_VALUE_INVALID", f"{path}.{temporal_field}", "Temporal values must be valid ISO-8601 timestamps.")
                    continue
                if parsed.tzinfo is None:
                    add("FACT_TEMPORAL_TIMEZONE_REQUIRED", f"{path}.{temporal_field}", "Temporal values must include a timezone offset.")
                    continue
                temporal_values[temporal_field] = parsed
            valid_start = temporal_values.get("valid_from")
            valid_end = temporal_values.get("valid_until")
            if valid_start and valid_end and valid_end < valid_start:
                add("FACT_VALIDITY_INTERVAL_INVALID", path, "valid_until must be later than or equal to valid_from.")
            record_start = temporal_values.get("recorded_at") or temporal_values.get("recorded_from")
            record_end = temporal_values.get("recorded_until") or temporal_values.get("superseded_at")
            if record_start and record_end and record_end <= record_start:
                add("FACT_RECORD_INTERVAL_INVALID", path, "recorded_until must be later than recorded_at.")
            precedence = fact.get("source_precedence", fact.get("authority_rank"))
            if precedence is not None:
                try:
                    if int(precedence) < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    add("FACT_SOURCE_PRECEDENCE_INVALID", f"{path}.source_precedence", "Source precedence must be a positive integer; higher values are more authoritative.")

        policies = snapshot.get("policies")
        if not isinstance(policies, list):
            add("POLICIES_INVALID", "policies", "Policies must be an array.")
            policies = []
        seen = set()
        for index, policy in enumerate(policies):
            path = f"policies[{index}]"
            if not isinstance(policy, dict):
                add("POLICY_INVALID", path, "Each policy must be a JSON object.")
                continue
            record_id = str(policy.get("policy_id", "")).strip()
            if not record_id:
                add("POLICY_ID_REQUIRED", f"{path}.policy_id", "Every policy requires a policy_id.")
            elif record_id in seen:
                add("DUPLICATE_POLICY_ID", f"{path}.policy_id", f"Duplicate policy_id: {record_id}.")
            seen.add(record_id)
            if policy.get("status", "draft") not in ALLOWED_RECORD_STATUSES:
                add("POLICY_STATUS_INVALID", f"{path}.status", "Unsupported policy status.")
            if policy.get("severity") and policy["severity"] not in ALLOWED_SEVERITIES:
                add("POLICY_SEVERITY_INVALID", f"{path}.severity", "Severity must be blocking, review_required, suggestion or informational.")

        terminology = snapshot.get("terminology")
        if not isinstance(terminology, dict):
            add("TERMINOLOGY_INVALID", "terminology", "Terminology must be a JSON object.")
        else:
            for field in ("preferred_terms", "prohibited_or_review_terms"):
                if not isinstance(terminology.get(field, []), list):
                    add("TERMINOLOGY_LIST_INVALID", f"terminology.{field}", f"{field} must be an array.")

        voice = snapshot.get("voice")
        if not isinstance(voice, dict):
            add("VOICE_INVALID", "voice", "Voice guidance must be a JSON object.")
        else:
            for field in ("voice_traits", "approved_examples", "disallowed_patterns"):
                if not isinstance(voice.get(field, []), list):
                    add("VOICE_LIST_INVALID", f"voice.{field}", f"{field} must be an array.")

        assets = snapshot.get("assets")
        if not isinstance(assets, dict):
            add("ASSETS_INVALID", "assets", "Asset manifest must be a JSON object.")
        else:
            approved_assets = assets.get("approved_assets", [])
            if not isinstance(approved_assets, list):
                add("ASSET_LIST_INVALID", "assets.approved_assets", "approved_assets must be an array.")
            else:
                seen = set()
                for index, asset in enumerate(approved_assets):
                    path = f"assets.approved_assets[{index}]"
                    if not isinstance(asset, dict):
                        add("ASSET_INVALID", path, "Each asset must be a JSON object.")
                        continue
                    asset_id = str(asset.get("asset_id", "")).strip()
                    if not asset_id:
                        add("ASSET_ID_REQUIRED", f"{path}.asset_id", "Every asset requires an asset_id.")
                    elif asset_id in seen:
                        add("DUPLICATE_ASSET_ID", f"{path}.asset_id", f"Duplicate asset_id: {asset_id}.")
                    seen.add(asset_id)
                    file_path = asset.get("file_path")
                    if file_path:
                        raw_path = str(file_path)
                        candidate = Path(raw_path)
                        windows_candidate = PureWindowsPath(raw_path)
                        if candidate.is_absolute() or windows_candidate.is_absolute() or ".." in candidate.parts or ".." in windows_candidate.parts or "\\" in raw_path or ":" in raw_path:
                            add("ASSET_PATH_UNSAFE", f"{path}.file_path", "Asset paths must be relative, use forward slashes and cannot traverse directories or drive roots.")

        return errors
