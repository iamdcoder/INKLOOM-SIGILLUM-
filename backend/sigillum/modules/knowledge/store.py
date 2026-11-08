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

SECTION_NAMES = {"brand", "facts", "policies", "terminology", "voice", "assets", "sources"}
SECTION_FILES = {
    "brand": "brand.json",
    "facts": "facts.json",
    "policies": "policies.json",
    "terminology": "terminology.json",
    "voice": "voice.json",
    "assets": "asset_manifest.json",
    "sources": "sources.json",
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
    """Stores immutable Knowledge Packs in tenant *and brand* namespaces.

    Published versions are immutable snapshots. Drafts are scoped to one brand,
    and a new non-demo brand receives an empty starter pack rather than another
    brand's synthetic facts or assets. Filesystem storage is a single-host
    adapter; production multi-instance publication locking remains a deployment
    concern and is explicitly documented.
    """

    DEFAULT_BRAND_ID = "brand_orbita_demo"

    def __init__(self, seed_root: Path, root: Path):
        self.seed_root = Path(seed_root)
        self.root = Path(root)
        self._lock = threading.RLock()

    def _tenant_root(self, tenant_id: str) -> Path:
        return self.root / _safe_component(tenant_id)

    def _brand_root(self, tenant_id: str, brand_id: str) -> Path:
        return self._tenant_root(tenant_id) / "brands" / _safe_component(brand_id)

    def _pack_id(self, brand_id: str) -> str:
        seed_pack = BrandPack(root=self.seed_root)
        if brand_id == str(seed_pack.brand.get("brand_id", self.DEFAULT_BRAND_ID)):
            return _safe_component(str(seed_pack.brand["pack_id"]))
        return _safe_component(f"BKP-{brand_id}")

    def _pack_root(self, tenant_id: str, brand_id: str, pack_id: str | None = None) -> Path:
        return self._brand_root(tenant_id, brand_id) / _safe_component(pack_id or self._pack_id(brand_id))

    def _legacy_pack_root(self, tenant_id: str) -> Path:
        seed_pack = BrandPack(root=self.seed_root)
        return self._tenant_root(tenant_id) / _safe_component(str(seed_pack.brand["pack_id"]))

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_snapshot(self, destination: Path, snapshot: dict[str, Any], copy_assets_from: Path | None = None) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for section, filename in SECTION_FILES.items():
            if section not in snapshot:
                continue
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
        return BrandPack(root=root).snapshot()

    def _seed_source_registry(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Create explicit source records for source quotes embedded in demo facts."""
        rows: dict[str, dict[str, Any]] = {}
        for fact in snapshot.get("facts", []):
            source_ref = fact.get("source_ref") if isinstance(fact, dict) else None
            if not isinstance(source_ref, dict) or not source_ref.get("source_id"):
                continue
            source_id = str(source_ref["source_id"])
            quote = str(source_ref.get("quote", ""))
            rows.setdefault(source_id, {
                "source_id": source_id,
                "name": source_id.replace("-", " ").title(),
                "source_type": "reference_text",
                "version": int(source_ref.get("source_version", 1)),
                "reference_text": quote,
                "sha256": sha256(quote.encode("utf-8")).hexdigest(),
                "owner_id": snapshot.get("brand", {}).get("owner_id", "system-seed"),
                "status": "approved",
                "approved_by": "system-seed",
                "approved_at": _now(),
                "valid_from": fact.get("valid_from"),
                "valid_until": fact.get("valid_until"),
                "origin": "synthetic_demo_fixture",
            })
        return {"schema_version": "1.0.0", "sources": list(rows.values())}

    def _empty_brand_snapshot(self, brand_id: str, brand_name: str) -> dict[str, Any]:
        seed = BrandPack(root=self.seed_root).snapshot()
        brand = dict(seed["brand"])
        brand.update({
            "pack_id": self._pack_id(brand_id),
            "pack_version": "1.0.0",
            "brand_id": brand_id,
            "brand_name": brand_name or brand_id,
            "is_synthetic": False,
            "description": "New brand workspace. Add and approve its own facts, policies, terminology, voice examples and assets before relying on brand-specific checks.",
            "owner_id": "unassigned",
            "status": "draft",
        })
        return {
            "brand": brand,
            "facts": [],
            "policies": [],
            "terminology": {"preferred_terms": [], "prohibited_or_review_terms": []},
            "voice": {
                "locale": brand.get("default_locale", "en-IN"),
                "voice_traits": [],
                "approved_examples": [],
                "disallowed_patterns": [],
                "limitation": "Voice guidance is owner-defined and is not a factual evidence source.",
            },
            "assets": {"schema_version": "1.0.0", "approved_assets": [], "known_non_approved_test_assets": []},
            "sources": {"schema_version": "1.0.0", "sources": []},
        }

    def ensure_initialized(
        self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None
    ) -> Path:
        """Ensure a distinct pack exists for the selected tenant/brand context."""
        with self._lock:
            seed_pack = BrandPack(root=self.seed_root)
            brand_id = brand_id or str(seed_pack.brand.get("brand_id", self.DEFAULT_BRAND_ID))
            brand_id = _safe_component(brand_id)
            pack_id = self._pack_id(brand_id)
            pack_root = self._pack_root(tenant_id, brand_id, pack_id)
            active_pointer = pack_root / "active.json"
            if active_pointer.exists():
                pointer = self._read_json(active_pointer)
                active_root = pack_root / "versions" / _safe_component(pointer["version_id"])
                if active_root.exists():
                    return active_root
                raise RuntimeError("Active Brand Knowledge Pack pointer references a missing version")

            brand_root = self._brand_root(tenant_id, brand_id)
            brand_root.mkdir(parents=True, exist_ok=True)

            # One-time compatibility migration: only the original ORBITA brand
            # may inherit the tenant-only Build 007-011 pack. No sibling brand can.
            legacy_root = self._legacy_pack_root(tenant_id)
            seed_brand_id = str(seed_pack.brand.get("brand_id", self.DEFAULT_BRAND_ID))
            if brand_id == seed_brand_id and (legacy_root / "active.json").exists():
                pack_root.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(legacy_root, pack_root, dirs_exist_ok=True)
                legacy_drafts = self._tenant_root(tenant_id) / "drafts"
                target_drafts = brand_root / "drafts"
                if legacy_drafts.exists() and not target_drafts.exists():
                    shutil.copytree(legacy_drafts, target_drafts)
                pointer = self._read_json(pack_root / "active.json")
                active_root = pack_root / "versions" / _safe_component(pointer["version_id"])
                if active_root.exists():
                    return active_root
                raise RuntimeError("Migrated active Brand Knowledge Pack pointer references a missing version")

            if brand_id == seed_brand_id:
                snapshot = seed_pack.snapshot()
                # Fresh deployments get source records with explicit source
                # provenance; legacy migrated snapshots remain byte-for-byte.
                snapshot["sources"] = self._seed_source_registry(snapshot)
                for fact in snapshot.get("facts", []):
                    fact.setdefault("owner_id", snapshot["brand"].get("owner_id", "system-seed"))
                    fact.setdefault("approved_by", "system-seed")
                    fact.setdefault("approved_at", _now())
                for policy in snapshot.get("policies", []):
                    policy.setdefault("approved_by", "system-seed")
                    policy.setdefault("approved_at", _now())
            else:
                snapshot = self._empty_brand_snapshot(brand_id, brand_name or brand_id)

            self._validate(snapshot, require_identity=True)
            version_id = "v0001"
            version_root = pack_root / "versions" / version_id
            self._write_snapshot(version_root, snapshot, copy_assets_from=self.seed_root if brand_id == seed_brand_id else None)
            fingerprint = _canonical_hash(snapshot)
            metadata = {
                "version_id": version_id,
                "pack_id": pack_id,
                "brand_id": brand_id,
                "pack_version": str(snapshot["brand"].get("pack_version", "1.0.0")),
                "fingerprint": fingerprint,
                "status": "PUBLISHED",
                "created_at": _now(),
                "created_by": "system-seed" if brand_id == seed_brand_id else "system-empty-brand",
                "base_version_id": None,
            }
            _write_json_atomic(version_root / "version.json", metadata)
            _write_json_atomic(pack_root / "active.json", {
                "version_id": version_id,
                "fingerprint": fingerprint,
                "activated_at": _now(),
            })
            return version_root

    def active_root(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> Path:
        seed_pack = BrandPack(root=self.seed_root)
        brand_id = brand_id or str(seed_pack.brand.get("brand_id", self.DEFAULT_BRAND_ID))
        pack_root = self._pack_root(tenant_id, brand_id)
        self.ensure_initialized(tenant_id, brand_id, brand_name)
        pointer = self._read_json(pack_root / "active.json")
        return pack_root / "versions" / _safe_component(pointer["version_id"])

    def active_pack(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> BrandPack:
        return BrandPack(root=self.active_root(tenant_id, brand_id, brand_name))

    def active_metadata(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> dict[str, Any]:
        root = self.active_root(tenant_id, brand_id, brand_name)
        metadata = self._read_json(root / "version.json")
        pointer = self._read_json(root.parent.parent / "active.json")
        metadata["is_active"] = True
        metadata["fingerprint"] = pointer.get("fingerprint", metadata.get("fingerprint"))
        return metadata

    def list_versions(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> list[dict[str, Any]]:
        active = self.active_metadata(tenant_id, brand_id, brand_name)
        versions_root = self.active_root(tenant_id, brand_id, brand_name).parent
        rows: list[dict[str, Any]] = []
        for version_dir in versions_root.iterdir():
            metadata_file = version_dir / "version.json"
            if version_dir.is_dir() and metadata_file.exists():
                row = self._read_json(metadata_file)
                row["is_active"] = row.get("version_id") == active.get("version_id")
                rows.append(row)
        return sorted(rows, key=lambda item: item.get("created_at", ""), reverse=True)

    def _draft_path(self, tenant_id: str, draft_id: str, brand_id: str | None = None) -> Path:
        if brand_id is None:
            brand_id = self.DEFAULT_BRAND_ID
        return self._brand_root(tenant_id, brand_id) / "drafts" / f"{_safe_component(draft_id)}.json"

    def create_draft(
        self, tenant_id: str, actor_id: str, brand_id: str | None = None, brand_name: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            active_root = self.active_root(tenant_id, brand_id, brand_name)
            active_meta = self._read_json(active_root / "version.json")
            snapshot = self._snapshot_from_root(active_root)
            if "sources" not in snapshot:
                snapshot["sources"] = self._seed_source_registry(snapshot)
            for record in snapshot.get("facts", []):
                if isinstance(record, dict) and record.get("status") == "approved":
                    record.setdefault("owner_id", snapshot.get("brand", {}).get("owner_id", "legacy-seed"))
                    record.setdefault("approved_by", "legacy-seed")
                    record.setdefault("approved_at", _now())
            for record in snapshot.get("policies", []):
                if isinstance(record, dict) and record.get("status") == "approved":
                    record.setdefault("approved_by", record.get("owner_id") or "legacy-seed")
                    record.setdefault("approved_at", _now())
            for record in (snapshot.get("assets", {}) or {}).get("approved_assets", []):
                if isinstance(record, dict) and record.get("status") == "approved":
                    record.setdefault("owner_id", snapshot.get("brand", {}).get("owner_id", "legacy-seed"))
                    record.setdefault("approved_by", "legacy-seed")
                    record.setdefault("approved_at", _now())
            for key in ("preferred_terms", "prohibited_or_review_terms"):
                for record in (snapshot.get("terminology", {}) or {}).get(key, []):
                    if isinstance(record, dict):
                        # Build 007-011 terminology fixtures predate explicit record
                        # approval fields. Treat those historical entries as approved
                        # once, then preserve explicit draft/rejected decisions.
                        record.setdefault("status", "approved")
                        if record.get("status") == "approved":
                            record.setdefault("owner_id", snapshot.get("brand", {}).get("owner_id", "legacy-seed"))
                            record.setdefault("approved_by", "legacy-seed")
                            record.setdefault("approved_at", _now())
            draft = {
                "draft_id": str(uuid4()),
                "brand_id": brand_id or self.DEFAULT_BRAND_ID,
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
            _write_json_atomic(self._draft_path(tenant_id, draft["draft_id"], brand_id), draft)
            return draft

    def get_draft(self, tenant_id: str, draft_id: str, brand_id: str | None = None) -> dict[str, Any]:
        path = self._draft_path(tenant_id, draft_id, brand_id)
        if not path.exists() and (brand_id is None or brand_id == self.DEFAULT_BRAND_ID):
            legacy_path = self._tenant_root(tenant_id) / "drafts" / f"{_safe_component(draft_id)}.json"
            if legacy_path.exists():
                path = legacy_path
        if not path.exists():
            raise FileNotFoundError("Draft Knowledge Pack not found")
        draft = self._read_json(path)
        if brand_id and draft.get("brand_id", self.DEFAULT_BRAND_ID) != brand_id:
            raise FileNotFoundError("Draft Knowledge Pack not found")
        return draft

    def update_section(
        self, tenant_id: str, draft_id: str, section: str, content: Any, actor_id: str,
        brand_id: str | None = None,
    ) -> dict[str, Any]:
        if section not in SECTION_NAMES:
            raise ValueError(f"Unsupported Knowledge Pack section: {section}")
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack versions are immutable")
            draft["snapshot"][section] = content
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return draft

    def append_asset(
        self, tenant_id: str, brand_id: str, draft_id: str, asset: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack versions are immutable")
            assets = draft["snapshot"].setdefault("assets", {"approved_assets": []})
            records = assets.setdefault("approved_assets", [])
            if any(item.get("asset_id") == asset.get("asset_id") for item in records if isinstance(item, dict)):
                raise ValueError("Asset identifier already exists in this draft")
            records.append(dict(asset))
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return draft

    def decide_record(
        self, tenant_id: str, brand_id: str, draft_id: str, record_type: str, record_id: str,
        status: str, actor_id: str, reason: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"approved", "draft", "not_approved", "rejected"}:
            raise ValueError("Unsupported record decision status")
        if record_type not in {"fact", "policy", "source", "asset", "term"}:
            raise ValueError("Unsupported record type")
        section_map = {"fact": "facts", "policy": "policies", "source": "sources", "asset": "assets"}
        id_field = {"fact": "fact_id", "policy": "policy_id", "source": "source_id", "asset": "asset_id", "term": "term_id"}
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            snapshot = draft.get("snapshot", {})
            candidates: list[dict[str, Any]] = []
            if record_type == "term":
                terminology = snapshot.get("terminology", {})
                candidates = list(terminology.get("preferred_terms", [])) + list(terminology.get("prohibited_or_review_terms", []))
            elif record_type == "asset":
                candidates = (snapshot.get("assets", {}) or {}).get("approved_assets", [])
            elif record_type == "source":
                candidates = (snapshot.get("sources", {}) or {}).get("sources", [])
            else:
                candidates = snapshot.get(section_map[record_type], [])
            record = next((item for item in candidates if isinstance(item, dict) and str(item.get(id_field[record_type])) == record_id), None)
            if record is None:
                raise FileNotFoundError("Knowledge record not found")
            record["status"] = status
            record["owner_id"] = record.get("owner_id") or actor_id
            record["decision_by"] = actor_id
            record["decision_at"] = _now()
            record["decision_reason"] = (reason or "").strip() or None
            if status == "approved":
                record["approved_by"] = actor_id
                record["approved_at"] = _now()
            else:
                record.pop("approved_by", None)
                record.pop("approved_at", None)
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return draft

    def validate_draft(
        self, tenant_id: str, draft_id: str, brand_id: str | None = None,
        asset_exists=None, asset_hash=None,
    ) -> dict[str, Any]:
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            snapshot = draft.get("snapshot")
            errors = self._validate(snapshot, require_identity=True, base_brand_id=None)
            active_root = self.active_root(tenant_id, brand_id)
            active_pack = BrandPack(root=active_root)
            active_brand_id = active_pack.brand.get("brand_id")
            draft_brand_id = (snapshot.get("brand") or {}).get("brand_id")
            if draft_brand_id != active_brand_id:
                errors.append({"code": "BRAND_ID_IMMUTABLE", "path": "brand.brand_id", "message": "A draft cannot change the active brand identity."})
            active_pack_id = active_pack.brand.get("pack_id")
            draft_pack_id = (snapshot.get("brand") or {}).get("pack_id")
            if draft_pack_id != active_pack_id:
                errors.append({"code": "PACK_ID_IMMUTABLE", "path": "brand.pack_id", "message": "A draft cannot change the Brand Knowledge Pack identity."})
            assets = (snapshot.get("assets") or {}).get("approved_assets", [])
            for index, asset in enumerate(assets if isinstance(assets, list) else []):
                if not isinstance(asset, dict):
                    continue
                file_path = asset.get("file_path")
                if file_path:
                    candidate = active_root / Path(str(file_path))
                    if not candidate.is_file():
                        errors.append({"code": "ASSET_FILE_MISSING", "path": f"assets.approved_assets[{index}].file_path", "message": "The referenced approved asset file is not present in the active asset store."})
                storage_key = asset.get("storage_key")
                if storage_key:
                    expected_prefix = f"brand-assets/{tenant_id}/{brand_id or self.DEFAULT_BRAND_ID}/"
                    if not str(storage_key).startswith(expected_prefix):
                        errors.append({"code": "ASSET_SCOPE_INVALID", "path": f"assets.approved_assets[{index}].storage_key", "message": "Uploaded asset storage keys must remain inside the current tenant and brand namespace."})
                        storage_key = None
                if asset.get("status") == "approved" and storage_key:
                    if asset_exists is not None:
                        try:
                            if not asset_exists(storage_key):
                                errors.append({"code": "ASSET_OBJECT_MISSING", "path": f"assets.approved_assets[{index}].storage_key", "message": "The approved asset object is missing from private object storage."})
                        except FileNotFoundError:
                            errors.append({"code": "ASSET_OBJECT_MISSING", "path": f"assets.approved_assets[{index}].storage_key", "message": "The approved asset object is missing from private object storage."})
                        except Exception:
                            errors.append({"code": "ASSET_OBJECT_UNAVAILABLE", "path": f"assets.approved_assets[{index}].storage_key", "message": "The approved asset could not be verified in object storage."})
                    if asset_hash is not None:
                        try:
                            actual_hash = asset_hash(storage_key)
                            expected_hash = str(asset.get("sha256", "")).lower()
                            if not expected_hash:
                                errors.append({"code": "ASSET_HASH_REQUIRED", "path": f"assets.approved_assets[{index}].sha256", "message": "Approved uploaded assets require a recorded SHA-256 hash."})
                            elif actual_hash.lower() != expected_hash:
                                errors.append({"code": "ASSET_HASH_MISMATCH", "path": f"assets.approved_assets[{index}].sha256", "message": "The stored asset bytes no longer match the uploaded SHA-256 hash."})
                        except FileNotFoundError:
                            errors.append({"code": "ASSET_OBJECT_MISSING", "path": f"assets.approved_assets[{index}].storage_key", "message": "The approved asset object is missing from private object storage."})
                        except Exception:
                            errors.append({"code": "ASSET_OBJECT_UNAVAILABLE", "path": f"assets.approved_assets[{index}].storage_key", "message": "The approved asset could not be hash-verified in object storage."})
                if asset.get("status") == "approved" and asset.get("storage_key") and (not asset.get("approved_by") or not asset.get("approved_at")):
                    errors.append({"code": "ASSET_APPROVAL_PROVENANCE_REQUIRED", "path": f"assets.approved_assets[{index}]", "message": "Approved uploaded assets require an approving owner and timestamp."})

            result = {"valid": not errors, "errors": errors, "warnings": [], "validated_at": _now()}
            draft["validation"] = result
            draft["status"] = "VALIDATED" if not errors else "DRAFT"
            draft["updated_at"] = _now()
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return result

    def publish_draft(
        self, tenant_id: str, draft_id: str, actor_id: str, brand_id: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") != "VALIDATED" or not (draft.get("validation") or {}).get("valid"):
                raise ValueError("Validate the draft successfully before publishing")
            active_root = self.active_root(tenant_id, brand_id)
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
            _write_json_atomic(version_root / "brand.json", snapshot["brand"])
            fingerprint = _canonical_hash(snapshot)
            metadata = {
                "version_id": version_id,
                "pack_id": draft["pack_id"],
                "brand_id": brand_id or self.DEFAULT_BRAND_ID,
                "pack_version": new_pack_version,
                "fingerprint": fingerprint,
                "status": "PUBLISHED",
                "created_at": _now(),
                "created_by": actor_id,
                "base_version_id": active_meta["version_id"],
                "draft_id": draft_id,
            }
            _write_json_atomic(version_root / "version.json", metadata)
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
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
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
            seen_terms: set[str] = set()
            for field in ("preferred_terms", "prohibited_or_review_terms"):
                rows = terminology.get(field, [])
                if not isinstance(rows, list):
                    add("TERMINOLOGY_LIST_INVALID", f"terminology.{field}", f"{field} must be an array.")
                    continue
                for index, term in enumerate(rows):
                    path = f"terminology.{field}[{index}]"
                    if not isinstance(term, dict):
                        add("TERMINOLOGY_RECORD_INVALID", path, "Each terminology entry must be an object.")
                        continue
                    term_id = str(term.get("term_id", "")).strip()
                    if not term_id:
                        add("TERMINOLOGY_ID_REQUIRED", f"{path}.term_id", "Every terminology entry requires a term_id.")
                    elif term_id in seen_terms:
                        add("DUPLICATE_TERMINOLOGY_ID", f"{path}.term_id", f"Duplicate term_id: {term_id}.")
                    seen_terms.add(term_id)
                    content_field = "preferred" if field == "preferred_terms" else "variant"
                    if not str(term.get(content_field, "")).strip():
                        add("TERMINOLOGY_TEXT_REQUIRED", f"{path}.{content_field}", f"Every entry requires {content_field} text.")
                    status = term.get("status", "approved")
                    if status not in ALLOWED_RECORD_STATUSES:
                        add("TERMINOLOGY_STATUS_INVALID", f"{path}.status", "Unsupported terminology status.")
                    if status == "approved" and (not term.get("approved_by") or not term.get("approved_at")):
                        add("TERMINOLOGY_APPROVAL_PROVENANCE_REQUIRED", path, "Approved terminology requires an approving owner and timestamp.")

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

        sources = snapshot.get("sources", {"sources": []})
        if not isinstance(sources, dict) or not isinstance(sources.get("sources", []), list):
            add("SOURCES_INVALID", "sources", "Source registry must contain a sources array.")
        else:
            seen_sources: set[str] = set()
            for index, source in enumerate(sources.get("sources", [])):
                path = f"sources.sources[{index}]"
                if not isinstance(source, dict):
                    add("SOURCE_INVALID", path, "Each source registry entry must be an object.")
                    continue
                source_id = str(source.get("source_id", "")).strip()
                if not source_id:
                    add("SOURCE_ID_REQUIRED", f"{path}.source_id", "Every source requires a source_id.")
                elif source_id in seen_sources:
                    add("DUPLICATE_SOURCE_ID", f"{path}.source_id", f"Duplicate source_id: {source_id}.")
                seen_sources.add(source_id)
                if not str(source.get("name", "")).strip():
                    add("SOURCE_NAME_REQUIRED", f"{path}.name", "Every source requires a display name.")
                if source.get("status", "draft") not in ALLOWED_RECORD_STATUSES:
                    add("SOURCE_STATUS_INVALID", f"{path}.status", "Unsupported source status.")
                if source.get("source_type", "reference_text") not in {"reference_text", "policy_document", "product_specification", "campaign_terms", "guideline", "other"}:
                    add("SOURCE_TYPE_INVALID", f"{path}.source_type", "Unsupported source type.")
                try:
                    if int(source.get("version", 1)) < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    add("SOURCE_VERSION_INVALID", f"{path}.version", "Source version must be a positive integer.")
                if source.get("source_uri"):
                    from urllib.parse import urlsplit
                    parsed_uri = urlsplit(str(source["source_uri"]))
                    if parsed_uri.scheme.lower() not in {"http", "https"} or not parsed_uri.netloc:
                        add("SOURCE_URI_INVALID", f"{path}.source_uri", "Source URI must be an absolute HTTP or HTTPS URL. Sigillum does not fetch source URIs automatically.")
                if source.get("sha256") and not re.fullmatch(r"[0-9a-fA-F]{64}", str(source["sha256"])):
                    add("SOURCE_HASH_INVALID", f"{path}.sha256", "Source SHA-256 must contain exactly 64 hexadecimal characters.")
                elif source.get("reference_text") and source.get("sha256"):
                    reference_hash = sha256(str(source["reference_text"]).encode("utf-8")).hexdigest()
                    if reference_hash.lower() != str(source["sha256"]).lower():
                        add("SOURCE_HASH_MISMATCH", f"{path}.sha256", "The source excerpt does not match its recorded SHA-256 hash.")
                if source.get("status") == "approved":
                    if not source.get("approved_by") or not source.get("approved_at"):
                        add("SOURCE_APPROVAL_PROVENANCE_REQUIRED", path, "Approved sources require approved_by and approved_at.")
                    if not (source.get("sha256") or source.get("reference_text") or source.get("source_uri")):
                        add("APPROVED_SOURCE_EVIDENCE_REQUIRED", path, "An approved source requires a content hash, reference text or source URI.")
                for temporal_field in ("valid_from", "valid_until"):
                    raw_value = source.get(temporal_field)
                    if raw_value in (None, ""):
                        continue
                    try:
                        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
                        if parsed.tzinfo is None:
                            raise ValueError
                    except ValueError:
                        add("SOURCE_TEMPORAL_VALUE_INVALID", f"{path}.{temporal_field}", "Source validity must be a timezone-aware ISO-8601 timestamp.")
                raw_start = source.get("valid_from")
                raw_end = source.get("valid_until")
                if raw_start and raw_end:
                    try:
                        start_at = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
                        end_at = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
                        if start_at.tzinfo is not None and end_at.tzinfo is not None and end_at < start_at:
                            add("SOURCE_VALIDITY_INTERVAL_INVALID", path, "valid_until must be later than or equal to valid_from.")
                    except ValueError:
                        pass

            approved_sources = {
                str(item.get("source_id")): item
                for item in sources.get("sources", [])
                if isinstance(item, dict) and item.get("status") == "approved"
            }
            for index, fact in enumerate(facts):
                if not isinstance(fact, dict) or fact.get("status") != "approved":
                    continue
                if not fact.get("approved_by") or not fact.get("approved_at"):
                    add("FACT_APPROVAL_PROVENANCE_REQUIRED", f"facts[{index}]", "Approved facts require approved_by and approved_at.")
                source_ref = fact.get("source_ref")
                source_id = source_ref.get("source_id") if isinstance(source_ref, dict) else None
                approved_source = approved_sources.get(str(source_id)) if source_id else None
                if not approved_source:
                    add("FACT_APPROVED_SOURCE_NOT_AUTHORISED", f"facts[{index}].source_ref", "An approved fact must link to an approved source registry record.")
                else:
                    if source_ref.get("source_version") is not None:
                        try:
                            if int(source_ref["source_version"]) != int(approved_source.get("version", 1)):
                                add("FACT_SOURCE_VERSION_MISMATCH", f"facts[{index}].source_ref.source_version", "The fact must reference the exact approved source version used as evidence.")
                        except (TypeError, ValueError):
                            add("FACT_SOURCE_VERSION_INVALID", f"facts[{index}].source_ref.source_version", "Source version must be a positive integer.")
                    quote = str(source_ref.get("quote", "")).strip()
                    if not quote:
                        add("FACT_SOURCE_QUOTE_REQUIRED", f"facts[{index}].source_ref.quote", "Approved facts require the exact supporting source excerpt.")
                    elif approved_source.get("reference_text") and quote not in str(approved_source["reference_text"]):
                        add("FACT_SOURCE_QUOTE_NOT_FOUND", f"facts[{index}].source_ref.quote", "The fact's source quote is not present in the approved source record's reference text.")

        for index, policy in enumerate(policies):
            if isinstance(policy, dict) and policy.get("status") == "approved":
                if not policy.get("approved_by") or not policy.get("approved_at"):
                    add("POLICY_APPROVAL_PROVENANCE_REQUIRED", f"policies[{index}]", "Approved policies require approved_by and approved_at.")

        return errors
