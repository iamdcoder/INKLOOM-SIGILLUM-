"""Transactional Brand Knowledge Pack catalogue with private file storage.

The database owns pack metadata, immutable JSON snapshots, drafts, decisions and
the active-version pointer. The configured storage adapter retains private
binary assets; filesystem JSON files are compatibility/export mirrors only.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from sigillum.modules.knowledge.brand_pack import BrandPack
from sigillum.modules.knowledge.asset_policy import palette_match_ratio, validate_usage_policies
from sigillum.infrastructure.database import models
from sigillum.infrastructure.database.session import set_database_scope

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

    Published versions are immutable database snapshots. Drafts are scoped to
    one brand, and a new non-demo brand receives an empty starter pack rather
    than another brand's synthetic facts or assets. Filesystem JSON is a
    compatibility mirror; private binaries remain in the configured storage
    adapter.
    """

    DEFAULT_BRAND_ID = "brand_orbita_demo"

    def __init__(self, seed_root: Path, root: Path, session_factory=None):
        self.seed_root = Path(seed_root)
        self.root = Path(root)
        self.session_factory = session_factory
        self._lock = threading.RLock()

    @contextmanager
    def _database(self, tenant_id: str, brand_id: str):
        """Open a tenant+brand-scoped transaction when database persistence is enabled."""
        if self.session_factory is None:
            yield None
            return
        session = self.session_factory()
        try:
            set_database_scope(session, tenant_id=tenant_id, brand_id=brand_id)
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _datetime_value(value: str | None) -> datetime:
        if value:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except (TypeError, ValueError):
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    def _draft_dict(self, row: models.BrandKnowledgePackDraft) -> dict[str, Any]:
        return {
            "draft_id": row.draft_id,
            "brand_id": row.brand_id,
            "pack_id": row.pack_id,
            "base_version_id": row.base_version_id,
            "base_fingerprint": row.base_fingerprint,
            "status": row.status,
            "created_at": self._as_iso(row.created_at),
            "created_by": row.created_by,
            "updated_at": self._as_iso(row.updated_at),
            "updated_by": row.updated_by,
            "snapshot": deepcopy(row.snapshot),
            "validation": deepcopy(row.validation),
            "published_version_id": row.published_version_id,
            "published_fingerprint": row.published_fingerprint,
            "revision": row.revision,
        }

    def _version_dict(self, row: models.BrandKnowledgePackVersion, is_active: bool = False) -> dict[str, Any]:
        return {
            "version_id": row.version_id,
            "pack_id": row.pack_id,
            "brand_id": row.brand_id,
            "pack_version": row.pack_version,
            "fingerprint": row.fingerprint,
            "status": row.status,
            "created_at": self._as_iso(row.created_at),
            "created_by": row.created_by,
            "base_version_id": row.base_version_id,
            "is_active": is_active,
        }

    def _catalog_active(self, tenant_id: str, brand_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if self.session_factory is None:
            return None
        with self._database(tenant_id, brand_id) as db:
            head = db.scalar(select(models.BrandKnowledgePackHead).where(
                models.BrandKnowledgePackHead.tenant_id == tenant_id,
                models.BrandKnowledgePackHead.brand_id == brand_id,
            ))
            if head is None:
                return None
            version = db.scalar(select(models.BrandKnowledgePackVersion).where(
                models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                models.BrandKnowledgePackVersion.brand_id == brand_id,
                models.BrandKnowledgePackVersion.version_id == head.active_version_id,
            ))
            if version is None:
                raise RuntimeError("The database Knowledge Pack head references a missing immutable version")
            return (
                {
                    "id": head.id,
                    "tenant_id": head.tenant_id,
                    "brand_id": head.brand_id,
                    "pack_id": head.pack_id,
                    "active_version_id": head.active_version_id,
                    "active_fingerprint": head.active_fingerprint,
                    "revision": head.revision,
                },
                {
                    **self._version_dict(version, is_active=True),
                    "snapshot": deepcopy(version.snapshot),
                },
            )

    def _catalog_register_from_filesystem(
        self, tenant_id: str, brand_id: str, version_root: Path
    ) -> None:
        """Import the complete existing filesystem version history into the DB."""
        if self.session_factory is None:
            return
        pack_root = version_root.parent.parent
        pointer_path = pack_root / "active.json"
        active_pointer = self._read_json(pointer_path) if pointer_path.exists() else {}
        active_version_id = str(active_pointer.get("version_id") or version_root.name)
        imported_versions: list[dict[str, Any]] = []
        active_metadata: dict[str, Any] | None = None

        versions_root = pack_root / "versions"
        for candidate_root in sorted(versions_root.iterdir(), key=lambda item: item.name):
            if not candidate_root.is_dir() or not (candidate_root / "version.json").is_file():
                continue
            metadata = self._read_json(candidate_root / "version.json")
            version_id = str(metadata.get("version_id") or candidate_root.name)
            if version_id != candidate_root.name:
                raise RuntimeError("Legacy Knowledge Pack version folder and metadata ID do not match")
            if str(metadata.get("brand_id") or brand_id) != brand_id:
                raise RuntimeError("Legacy Knowledge Pack version belongs to a different brand scope")
            snapshot = BrandPack(root=candidate_root).snapshot()
            expected_fingerprint = str(metadata.get("fingerprint", ""))
            if expected_fingerprint and _canonical_hash(snapshot) != expected_fingerprint:
                raise RuntimeError(
                    f"Legacy filesystem Knowledge Pack {version_id} fingerprint does not match its snapshot; refusing to import it"
                )
            pack_id = str(metadata.get("pack_id") or self._pack_id(brand_id))
            if imported_versions and pack_id != imported_versions[0]["pack_id"]:
                raise RuntimeError("Legacy Knowledge Pack history contains inconsistent pack IDs")
            row = {
                "version_id": version_id,
                "pack_id": pack_id,
                "pack_version": str(metadata.get("pack_version", "1.0.0")),
                "fingerprint": expected_fingerprint or _canonical_hash(snapshot),
                "base_version_id": metadata.get("base_version_id"),
                "snapshot": snapshot,
                "created_by": str(metadata.get("created_by", "system-migration")),
                "created_at": self._datetime_value(metadata.get("created_at")),
            }
            imported_versions.append(row)
            if version_id == active_version_id:
                active_metadata = row

        if not imported_versions or active_metadata is None:
            raise RuntimeError("Legacy active Knowledge Pack version is missing from its version history")
        pointer_fingerprint = str(active_pointer.get("fingerprint") or active_metadata["fingerprint"])
        if pointer_fingerprint != active_metadata["fingerprint"]:
            raise RuntimeError("Legacy active Knowledge Pack pointer fingerprint does not match its version")

        try:
            with self._database(tenant_id, brand_id) as db:
                existing = db.scalar(select(models.BrandKnowledgePackHead).where(
                    models.BrandKnowledgePackHead.tenant_id == tenant_id,
                    models.BrandKnowledgePackHead.brand_id == brand_id,
                ))
                if existing is not None:
                    return
                for item in imported_versions:
                    db.add(models.BrandKnowledgePackVersion(
                        tenant_id=tenant_id,
                        brand_id=brand_id,
                        pack_id=item["pack_id"],
                        version_id=item["version_id"],
                        pack_version=item["pack_version"],
                        fingerprint=item["fingerprint"],
                        status="PUBLISHED",
                        base_version_id=item["base_version_id"],
                        snapshot=item["snapshot"],
                        created_by=item["created_by"],
                        created_at=item["created_at"],
                    ))
                head = models.BrandKnowledgePackHead(
                    tenant_id=tenant_id,
                    brand_id=brand_id,
                    pack_id=active_metadata["pack_id"],
                    active_version_id=active_version_id,
                    active_fingerprint=active_metadata["fingerprint"],
                    revision=1,
                )
                db.add(head)
        except IntegrityError:
            # Another process initialised this exact scope first. Its database
            # pointer is authoritative; the caller will re-read it below.
            return

    def _catalog_import_filesystem_drafts(self, tenant_id: str, brand_id: str) -> None:
        """Import Build 012 filesystem drafts once, preserving un-published work."""
        if self.session_factory is None:
            return
        drafts_root = self._brand_root(tenant_id, brand_id) / "drafts"
        if not drafts_root.exists():
            return
        for path in sorted(drafts_root.glob("*.json")):
            try:
                payload = self._read_json(path)
                draft_id = str(payload.get("draft_id", ""))
                snapshot = payload.get("snapshot")
                if (
                    not draft_id
                    or path.stem != draft_id
                    or not isinstance(snapshot, dict)
                    or payload.get("brand_id", self.DEFAULT_BRAND_ID) != brand_id
                    or not payload.get("base_version_id")
                    or not payload.get("base_fingerprint")
                ):
                    continue
                with self._database(tenant_id, brand_id) as db:
                    exists = db.scalar(select(models.BrandKnowledgePackDraft.draft_id).where(
                        models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                        models.BrandKnowledgePackDraft.brand_id == brand_id,
                        models.BrandKnowledgePackDraft.draft_id == draft_id,
                    ))
                    if exists is not None:
                        continue
                    created_at = self._datetime_value(payload.get("created_at"))
                    updated_at = self._datetime_value(payload.get("updated_at"))
                    db.add(models.BrandKnowledgePackDraft(
                        draft_id=draft_id,
                        tenant_id=tenant_id,
                        brand_id=brand_id,
                        pack_id=str(payload.get("pack_id") or self._pack_id(brand_id)),
                        base_version_id=str(payload["base_version_id"]),
                        base_fingerprint=str(payload["base_fingerprint"]),
                        status=str(payload.get("status", "DRAFT")),
                        snapshot=deepcopy(snapshot),
                        validation=deepcopy(payload.get("validation")),
                        revision=max(1, int(payload.get("revision", 1))),
                        published_version_id=payload.get("published_version_id"),
                        published_fingerprint=payload.get("published_fingerprint"),
                        created_at=created_at,
                        created_by=str(payload.get("created_by") or "legacy-build-012"),
                        updated_at=updated_at,
                        updated_by=str(payload.get("updated_by") or payload.get("created_by") or "legacy-build-012"),
                    ))
            except IntegrityError:
                # A concurrent API instance may have imported the same draft.
                continue
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                # A malformed legacy file is not imported as authoritative state.
                # Keep the original file untouched for manual recovery.
                continue

    def _persist_draft(
        self,
        tenant_id: str,
        brand_id: str,
        draft: dict[str, Any],
        decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.session_factory is None:
            _write_json_atomic(self._draft_path(tenant_id, draft["draft_id"], brand_id), draft)
            return draft
        with self._database(tenant_id, brand_id) as db:
            row = db.scalar(select(models.BrandKnowledgePackDraft).where(
                models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                models.BrandKnowledgePackDraft.brand_id == brand_id,
                models.BrandKnowledgePackDraft.draft_id == draft["draft_id"],
            ).with_for_update())
            if row is None:
                raise FileNotFoundError("Draft Knowledge Pack not found")
            expected_revision = int(draft.get("revision", row.revision))
            updated_at = self._datetime_value(draft.get("updated_at"))
            updated_by = str(draft.get("updated_by") or row.updated_by)

            # Revision is part of the UPDATE predicate as well as the row lock.
            # The compare-and-swap protects SQLite/local multi-process writes too,
            # where SELECT FOR UPDATE is not available.
            changed = db.execute(update(models.BrandKnowledgePackDraft).where(
                models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                models.BrandKnowledgePackDraft.brand_id == brand_id,
                models.BrandKnowledgePackDraft.draft_id == draft["draft_id"],
                models.BrandKnowledgePackDraft.revision == expected_revision,
            ).values(
                snapshot=deepcopy(draft["snapshot"]),
                status=str(draft["status"]),
                validation=deepcopy(draft.get("validation")),
                updated_at=updated_at,
                updated_by=updated_by,
                published_version_id=draft.get("published_version_id"),
                published_fingerprint=draft.get("published_fingerprint"),
                revision=expected_revision + 1,
            ), execution_options={"synchronize_session": False})
            if changed.rowcount != 1:
                raise ValueError("This draft changed in another session. Reload it before making another edit.")

            if decision:
                db.add(models.BrandKnowledgePackDecision(
                    tenant_id=tenant_id,
                    brand_id=brand_id,
                    draft_id=draft["draft_id"],
                    record_type=decision["record_type"],
                    record_id=decision["record_id"],
                    decision_status=decision["status"],
                    reason=decision["reason"],
                    actor_id=decision["actor_id"],
                    created_at=self._datetime_value(decision.get("created_at")),
                ))

            db.flush()
            db.refresh(row)
            result = self._draft_dict(row)
        try:
            _write_json_atomic(self._draft_path(tenant_id, draft["draft_id"], brand_id), result)
        except OSError:
            # The committed database state is authoritative; a failed local
            # compatibility mirror must not turn a successful write into a
            # misleading API failure. The next access can repair the mirror.
            pass
        return result

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

    def _write_snapshot(self, destination: Path, snapshot: dict[str, Any], copy_assets_from: Path | None = None, copy_seed_assets: bool = True) -> None:
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
        asset_source = copy_assets_from / "assets" if copy_assets_from else (self.seed_root / "assets" if copy_seed_assets else None)
        if asset_source is not None and asset_source.exists():
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
        """Ensure a distinct pack exists and its active pointer is database-backed when configured."""
        seed_pack = BrandPack(root=self.seed_root)
        brand_id = brand_id or str(seed_pack.brand.get("brand_id", self.DEFAULT_BRAND_ID))
        brand_id = _safe_component(brand_id)
        pack_id = self._pack_id(brand_id)

        # Database catalogue is authoritative. The local JSON pointer is retained
        # as a compatibility/export mirror, not as a concurrency authority.
        catalog = self._catalog_active(tenant_id, brand_id)
        if catalog is not None:
            head, version = catalog
            pack_root = self._pack_root(tenant_id, brand_id, head["pack_id"])
            version_root = pack_root / "versions" / _safe_component(version["version_id"])
            if not (version_root / "version.json").exists() or not (version_root / "brand.json").exists():
                try:
                    self._write_snapshot(
                        version_root,
                        version["snapshot"],
                        copy_assets_from=None,
                        copy_seed_assets=(brand_id == self.DEFAULT_BRAND_ID),
                    )
                    metadata = {key: value for key, value in version.items() if key != "snapshot"}
                    metadata["pack_id"] = head["pack_id"]
                    _write_json_atomic(version_root / "version.json", metadata)
                except OSError:
                    # Reading the authoritative DB snapshot remains possible
                    # even when local mirror repair is temporarily unavailable.
                    pass
            try:
                _write_json_atomic(pack_root / "active.json", {
                    "version_id": head["active_version_id"],
                    "fingerprint": head["active_fingerprint"],
                    "activated_at": _now(),
                })
            except OSError:
                # The DB pointer remains authoritative if its local mirror is
                # unavailable; active_root() reads the DB directly.
                pass
            self._catalog_import_filesystem_drafts(tenant_id, brand_id)
            return version_root

        with self._lock:
            pack_root = self._pack_root(tenant_id, brand_id, pack_id)
            active_pointer = pack_root / "active.json"
            if active_pointer.exists():
                pointer = self._read_json(active_pointer)
                active_root = pack_root / "versions" / _safe_component(pointer["version_id"])
                if active_root.exists():
                    self._catalog_register_from_filesystem(tenant_id, brand_id, active_root)
                    catalog = self._catalog_active(tenant_id, brand_id)
                    if catalog is not None:
                        self._catalog_import_filesystem_drafts(tenant_id, brand_id)
                        return pack_root / "versions" / catalog[1]["version_id"]
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
                    self._catalog_register_from_filesystem(tenant_id, brand_id, active_root)
                    catalog = self._catalog_active(tenant_id, brand_id)
                    if catalog is not None:
                        self._catalog_import_filesystem_drafts(tenant_id, brand_id)
                        return pack_root / "versions" / catalog[1]["version_id"]
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
            self._catalog_register_from_filesystem(tenant_id, brand_id, version_root)
            catalog = self._catalog_active(tenant_id, brand_id)
            if catalog is not None:
                self._catalog_import_filesystem_drafts(tenant_id, brand_id)
                return pack_root / "versions" / catalog[1]["version_id"]
            return version_root

    def active_root(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> Path:
        seed_pack = BrandPack(root=self.seed_root)
        brand_id = brand_id or str(seed_pack.brand.get("brand_id", self.DEFAULT_BRAND_ID))
        self.ensure_initialized(tenant_id, brand_id, brand_name)
        if self.session_factory is not None:
            catalog = self._catalog_active(tenant_id, brand_id)
            if catalog is None:
                raise RuntimeError("Database Knowledge Pack catalogue was not initialised")
            head, version = catalog
            return self._pack_root(tenant_id, brand_id, head["pack_id"]) / "versions" / _safe_component(version["version_id"])
        pack_root = self._pack_root(tenant_id, brand_id)
        pointer = self._read_json(pack_root / "active.json")
        return pack_root / "versions" / _safe_component(pointer["version_id"])

    def active_pack(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> BrandPack:
        root = self.active_root(tenant_id, brand_id, brand_name)
        if self.session_factory is not None:
            resolved_brand_id = brand_id or self.DEFAULT_BRAND_ID
            catalog = self._catalog_active(tenant_id, resolved_brand_id)
            if catalog is None:
                raise RuntimeError("Database Knowledge Pack catalogue was not initialised")
            return BrandPack.from_snapshot(catalog[1]["snapshot"])
        return BrandPack(root=root)

    def active_metadata(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> dict[str, Any]:
        root = self.active_root(tenant_id, brand_id, brand_name)
        if self.session_factory is not None:
            catalog = self._catalog_active(tenant_id, brand_id or self.DEFAULT_BRAND_ID)
            if catalog is None:
                raise RuntimeError("Database Knowledge Pack catalogue was not initialised")
            return {key: value for key, value in catalog[1].items() if key != "snapshot"}
        metadata = self._read_json(root / "version.json")
        pointer = self._read_json(root.parent.parent / "active.json")
        metadata["is_active"] = True
        metadata["fingerprint"] = pointer.get("fingerprint", metadata.get("fingerprint"))
        return metadata

    def list_versions(self, tenant_id: str, brand_id: str | None = None, brand_name: str | None = None) -> list[dict[str, Any]]:
        active = self.active_metadata(tenant_id, brand_id, brand_name)
        if self.session_factory is not None:
            with self._database(tenant_id, brand_id or self.DEFAULT_BRAND_ID) as db:
                rows = db.scalars(select(models.BrandKnowledgePackVersion).where(
                    models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                    models.BrandKnowledgePackVersion.brand_id == (brand_id or self.DEFAULT_BRAND_ID),
                ).order_by(models.BrandKnowledgePackVersion.created_at.desc())).all()
                return [self._version_dict(row, row.version_id == active.get("version_id")) for row in rows]
        versions_root = self.active_root(tenant_id, brand_id, brand_name).parent
        rows: list[dict[str, Any]] = []
        for version_dir in versions_root.iterdir():
            metadata_file = version_dir / "version.json"
            if version_dir.is_dir() and metadata_file.exists():
                row = self._read_json(metadata_file)
                row["is_active"] = row.get("version_id") == active.get("version_id")
                rows.append(row)
        return sorted(rows, key=lambda item: item.get("created_at", ""), reverse=True)

    def _version_snapshot(
        self, tenant_id: str, brand_id: str, version_id: str, brand_name: str | None = None
    ) -> dict[str, Any]:
        version_id = _safe_component(version_id)
        if self.session_factory is not None:
            with self._database(tenant_id, brand_id) as db:
                row = db.scalar(select(models.BrandKnowledgePackVersion).where(
                    models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                    models.BrandKnowledgePackVersion.brand_id == brand_id,
                    models.BrandKnowledgePackVersion.version_id == version_id,
                ))
                if row is None:
                    raise FileNotFoundError("Knowledge Pack version not found")
                return deepcopy(row.snapshot)
        versions_root = self.active_root(tenant_id, brand_id, brand_name).parent
        version_root = versions_root / version_id
        if not version_root.is_dir():
            raise FileNotFoundError("Knowledge Pack version not found")
        return BrandPack(root=version_root).snapshot()

    @staticmethod
    def _diff_value(value: Any, field_name: str | None = None) -> str:
        """Bound values and redact private object-store identifiers in version diffs."""
        sensitive_names = {"storage_key", "extraction_key", "object_key", "s3_key", "bucket_key"}
        if field_name and field_name.lower() in sensitive_names:
            return "[redacted private storage reference]"

        def redact_nested(item: Any) -> Any:
            if isinstance(item, dict):
                return {
                    key: ("[redacted private storage reference]" if str(key).lower() in sensitive_names else redact_nested(val))
                    for key, val in item.items()
                }
            if isinstance(item, list):
                return [redact_nested(value) for value in item]
            return item

        safe_value = redact_nested(value)
        rendered = safe_value if isinstance(safe_value, str) else json.dumps(safe_value, ensure_ascii=False, sort_keys=True)
        return rendered if len(rendered) <= 500 else rendered[:497] + "..."

    @staticmethod
    def _diff_record(record: dict[str, Any]) -> dict[str, Any]:
        sensitive_names = {"storage_key", "extraction_key", "object_key", "s3_key", "bucket_key"}
        def redact(item: Any, parent_key: str | None = None) -> Any:
            if parent_key and parent_key.lower() in sensitive_names:
                return "[redacted private storage reference]"
            if isinstance(item, dict):
                return {
                    key: redact(value, str(key))
                    for key, value in item.items()
                }
            if isinstance(item, list):
                return [redact(value) for value in item]
            if parent_key == "reference_text" and isinstance(item, str) and len(item) > 500:
                return item[:497] + "..."
            return item
        return redact(record)

    def compare_versions(
        self, tenant_id: str, brand_id: str, from_version_id: str, to_version_id: str,
        brand_name: str | None = None, max_changes: int = 250,
    ) -> dict[str, Any]:
        """Return a bounded record-level diff between two immutable versions in one brand."""
        if from_version_id == to_version_id:
            raise ValueError("Choose two different Knowledge Pack versions to compare")
        left = self._version_snapshot(tenant_id, brand_id, from_version_id, brand_name)
        right = self._version_snapshot(tenant_id, brand_id, to_version_id, brand_name)
        descriptors = {
            "brand": (None, None),
            "facts": ("facts", "fact_id"),
            "policies": ("policies", "policy_id"),
            "terminology": ("terminology", "term_id"),
            "voice": ("voice", None),
            "assets": ("assets", "asset_id"),
            "sources": ("sources", "source_id"),
        }

        def records(section: str, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
            value = snapshot.get(section)
            if section == "brand":
                return {"brand": value} if isinstance(value, dict) else {}
            if section in {"facts", "policies"}:
                items = value if isinstance(value, list) else []
            elif section == "sources":
                items = value.get("sources", []) if isinstance(value, dict) else []
            elif section == "assets":
                items = value.get("approved_assets", []) if isinstance(value, dict) else []
            elif section == "terminology":
                items = []
                if isinstance(value, dict):
                    items = list(value.get("preferred_terms", [])) + list(value.get("prohibited_or_review_terms", []))
            elif section == "voice":
                return {"voice": value} if isinstance(value, dict) else {}
            else:
                items = []
            identifier = descriptors[section][1]
            result: dict[str, dict[str, Any]] = {}
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                key = str(item.get(identifier) or f"index-{index}") if identifier else f"index-{index}"
                result[key] = item
            return result

        changes: list[dict[str, Any]] = []
        for section in descriptors:
            before_records = records(section, left)
            after_records = records(section, right)
            for record_id in sorted(set(before_records) | set(after_records)):
                before = before_records.get(record_id)
                after = after_records.get(record_id)
                if before is None:
                    changes.append({"section": section, "record_id": record_id, "change": "ADDED", "fields": [], "after": self._diff_record(after)})
                elif after is None:
                    changes.append({"section": section, "record_id": record_id, "change": "REMOVED", "fields": [], "before": self._diff_record(before)})
                else:
                    fields = []
                    for field in sorted(set(before) | set(after)):
                        if before.get(field) != after.get(field):
                            fields.append({
                                "field": field,
                                "before": self._diff_value(before.get(field), field),
                                "after": self._diff_value(after.get(field), field),
                            })
                    if fields:
                        changes.append({"section": section, "record_id": record_id, "change": "CHANGED", "fields": fields})
                if len(changes) > max_changes:
                    break
            if len(changes) > max_changes:
                break
        return {
            "from_version_id": from_version_id,
            "to_version_id": to_version_id,
            "change_count": len(changes),
            "changes": changes[:max_changes],
            "truncated": len(changes) > max_changes,
        }

    def _draft_path(self, tenant_id: str, draft_id: str, brand_id: str | None = None) -> Path:
        if brand_id is None:
            brand_id = self.DEFAULT_BRAND_ID
        return self._brand_root(tenant_id, brand_id) / "drafts" / f"{_safe_component(draft_id)}.json"

    def _create_draft_database(
        self, tenant_id: str, actor_id: str, brand_id: str, brand_name: str | None
    ) -> dict[str, Any]:
        self.ensure_initialized(tenant_id, brand_id, brand_name)
        with self._database(tenant_id, brand_id) as db:
            head = db.scalar(select(models.BrandKnowledgePackHead).where(
                models.BrandKnowledgePackHead.tenant_id == tenant_id,
                models.BrandKnowledgePackHead.brand_id == brand_id,
            ).with_for_update())
            if head is None:
                raise RuntimeError("Knowledge Pack catalogue has not been initialised")
            active_version = db.scalar(select(models.BrandKnowledgePackVersion).where(
                models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                models.BrandKnowledgePackVersion.brand_id == brand_id,
                models.BrandKnowledgePackVersion.version_id == head.active_version_id,
            ))
            if active_version is None:
                raise RuntimeError("Active Knowledge Pack version is missing")
            snapshot = deepcopy(active_version.snapshot)
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
                        record.setdefault("status", "approved")
                        if record.get("status") == "approved":
                            record.setdefault("owner_id", snapshot.get("brand", {}).get("owner_id", "legacy-seed"))
                            record.setdefault("approved_by", "legacy-seed")
                            record.setdefault("approved_at", _now())
            now = datetime.now(timezone.utc)
            draft_id = str(uuid4())
            draft_row = models.BrandKnowledgePackDraft(
                draft_id=draft_id,
                tenant_id=tenant_id,
                brand_id=brand_id,
                pack_id=head.pack_id,
                base_version_id=head.active_version_id,
                base_fingerprint=head.active_fingerprint,
                status="DRAFT",
                snapshot=snapshot,
                validation=None,
                revision=1,
                created_at=now,
                created_by=actor_id,
                updated_at=now,
                updated_by=actor_id,
            )
            db.add(draft_row)
            db.flush()
            draft = self._draft_dict(draft_row)
        try:
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
        except OSError:
            # Database commit succeeded; filesystem JSON is only a mirror.
            pass
        return draft

    def create_draft(
        self, tenant_id: str, actor_id: str, brand_id: str | None = None, brand_name: str | None = None
    ) -> dict[str, Any]:
        resolved_brand_id = brand_id or self.DEFAULT_BRAND_ID
        if self.session_factory is not None:
            return self._create_draft_database(tenant_id, actor_id, resolved_brand_id, brand_name)
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
        resolved_brand_id = brand_id or self.DEFAULT_BRAND_ID
        if self.session_factory is not None:
            with self._database(tenant_id, resolved_brand_id) as db:
                row = db.scalar(select(models.BrandKnowledgePackDraft).where(
                    models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                    models.BrandKnowledgePackDraft.brand_id == resolved_brand_id,
                    models.BrandKnowledgePackDraft.draft_id == draft_id,
                ))
                if row is None:
                    raise FileNotFoundError("Draft Knowledge Pack not found")
                return self._draft_dict(row)
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

    def list_decisions(
        self, tenant_id: str, draft_id: str, brand_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return append-only record decisions for a scoped Knowledge Pack draft."""
        resolved_brand_id = brand_id or self.DEFAULT_BRAND_ID
        if self.session_factory is None:
            return []
        with self._database(tenant_id, resolved_brand_id) as db:
            draft_exists = db.scalar(select(models.BrandKnowledgePackDraft.draft_id).where(
                models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                models.BrandKnowledgePackDraft.brand_id == resolved_brand_id,
                models.BrandKnowledgePackDraft.draft_id == draft_id,
            ))
            if draft_exists is None:
                raise FileNotFoundError("Draft Knowledge Pack not found")
            rows = db.scalars(select(models.BrandKnowledgePackDecision).where(
                models.BrandKnowledgePackDecision.tenant_id == tenant_id,
                models.BrandKnowledgePackDecision.brand_id == resolved_brand_id,
                models.BrandKnowledgePackDecision.draft_id == draft_id,
            ).order_by(models.BrandKnowledgePackDecision.created_at.asc(), models.BrandKnowledgePackDecision.id.asc())).all()
            return [{
                "id": row.id,
                "draft_id": row.draft_id,
                "record_type": row.record_type,
                "record_id": row.record_id,
                "status": row.decision_status,
                "reason": row.reason,
                "actor_id": row.actor_id,
                "created_at": self._as_iso(row.created_at),
            } for row in rows]

    @staticmethod
    def _enforce_section_governance(section: str, current: Any, proposed: Any) -> None:
        """Protect owner decisions and upload provenance from the generic JSON editor.

        Editing an already-approved record automatically downgrades it to DRAFT;
        the owner must explicitly approve it again through the decision endpoint.
        New approvals and upload metadata can only be created by dedicated routes.
        """
        identity_fields = {
            "facts": "fact_id", "policies": "policy_id", "sources": "source_id",
            "assets": "asset_id", "terminology": "term_id",
        }
        protected = {"status", "approved_by", "approved_at", "decision_by", "decision_at", "decision_reason"}
        if section == "policies":
            # New policy records are required to carry an approved source clause.
            # This server-owned marker cannot be disabled through the JSON editor.
            protected.add("source_provenance_required")
        upload_provenance = {
            "sources": {"storage_key", "file_sha256", "mime_type", "size_bytes", "uploaded_by", "uploaded_at", "source_format",
                        "original_filename", "extraction_key", "extraction_status", "extraction_warnings",
                        "region_count", "reference_text", "sha256", "scan_status", "scan_engine",
                        "scan_scanned_at", "scan_signature"},
            "assets": {"storage_key", "sha256", "mime_type", "size_bytes", "width", "height", "uploaded_by",
                       "uploaded_at", "original_filename", "scan_status", "scan_engine", "scan_scanned_at",
                       "scan_signature"},
        }.get(section, set())

        def rows(value: Any) -> list[dict[str, Any]]:
            if section in {"facts", "policies"}:
                return value if isinstance(value, list) else []
            if section == "sources":
                return value.get("sources", []) if isinstance(value, dict) and isinstance(value.get("sources", []), list) else []
            if section == "assets":
                return value.get("approved_assets", []) if isinstance(value, dict) and isinstance(value.get("approved_assets", []), list) else []
            if section == "terminology":
                if not isinstance(value, dict):
                    return []
                return list(value.get("preferred_terms", [])) + list(value.get("prohibited_or_review_terms", []))
            return []

        id_field = identity_fields.get(section)
        if not id_field:
            return
        previous = {
            str(item.get(id_field)): item
            for item in rows(current)
            if isinstance(item, dict) and item.get(id_field) is not None
        }
        for index, item in enumerate(rows(proposed)):
            if not isinstance(item, dict):
                continue
            record_id = str(item.get(id_field, f"new-{index}"))
            old = previous.get(record_id)
            if old is None:
                if item.get("status") not in (None, "draft"):
                    raise ValueError(f"{section} record {record_id}: new records must start as draft; use the owner decision workflow to approve")
                new_record_protected = protected - {"status"}
                if section == "policies":
                    # Echoing this server-set marker back is harmless; setting it
                    # false or to any non-boolean value is not permitted.
                    if item.get("source_provenance_required") not in (None, True):
                        raise ValueError(f"policy record {record_id}: source provenance requirements are controlled by the server")
                    new_record_protected = new_record_protected - {"source_provenance_required"}
                if any(item.get(field) not in (None, "") for field in new_record_protected):
                    raise ValueError(f"{section} record {record_id}: approval provenance is created only by the owner decision workflow")
                if any(item.get(field) not in (None, "") for field in upload_provenance):
                    raise ValueError(f"{section} record {record_id}: upload provenance is created only by dedicated upload routes")
                if section == "policies":
                    item["source_provenance_required"] = True
                continue

            for field in protected:
                if item.get(field) != old.get(field):
                    raise ValueError(f"{section} record {record_id}: {field} is controlled by the explicit owner decision workflow")
            for field in upload_provenance:
                if item.get(field) != old.get(field):
                    raise ValueError(f"{section} record {record_id}: {field} is immutable upload provenance")

            if old.get("status") == "approved" and item != old:
                item["status"] = "draft"
                for field in ("approved_by", "approved_at", "decision_by", "decision_at", "decision_reason"):
                    item.pop(field, None)

    def update_section(
        self, tenant_id: str, draft_id: str, section: str, content: Any, actor_id: str,
        brand_id: str | None = None,
    ) -> dict[str, Any]:
        if section not in SECTION_NAMES:
            raise ValueError(f"Unsupported Knowledge Pack section: {section}")
        if self.session_factory is not None:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack versions are immutable")
            self._enforce_section_governance(section, draft["snapshot"].get(section), content)
            draft["snapshot"][section] = deepcopy(content)
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            return self._persist_draft(tenant_id, brand_id or self.DEFAULT_BRAND_ID, draft)
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack versions are immutable")
            self._enforce_section_governance(section, draft["snapshot"].get(section), content)
            draft["snapshot"][section] = content
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return draft

    def append_source(
        self, tenant_id: str, brand_id: str, draft_id: str, source: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        """Append a source created by a dedicated provenance-preserving intake route."""
        if self.session_factory is not None:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack drafts are immutable")
            registry = draft["snapshot"].setdefault("sources", {"schema_version": "1.0.0", "sources": []})
            records = registry.setdefault("sources", [])
            if any(item.get("source_id") == source.get("source_id") for item in records if isinstance(item, dict)):
                raise ValueError("Source identifier already exists in this draft")
            records.append(dict(source))
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            return self._persist_draft(tenant_id, brand_id, draft)
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack drafts are immutable")
            registry = draft["snapshot"].setdefault("sources", {"schema_version": "1.0.0", "sources": []})
            records = registry.setdefault("sources", [])
            if any(item.get("source_id") == source.get("source_id") for item in records if isinstance(item, dict)):
                raise ValueError("Source identifier already exists in this draft")
            records.append(dict(source))
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return draft

    def append_source_version(
        self, tenant_id: str, brand_id: str, draft_id: str, previous_source_id: str,
        source: dict[str, Any], actor_id: str,
    ) -> dict[str, Any]:
        """Append a replacement source version while preserving the old record in draft history."""
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack drafts are immutable")
            registry = draft["snapshot"].setdefault("sources", {"schema_version": "1.0.0", "sources": []})
            records = registry.setdefault("sources", [])
            previous = next((item for item in records if isinstance(item, dict) and item.get("source_id") == previous_source_id), None)
            if previous is None:
                raise FileNotFoundError("Source version to replace was not found")
            if previous.get("status") == "superseded":
                raise ValueError("A superseded source cannot be replaced again")
            if str(source.get("name", "")).strip().casefold() != str(previous.get("name", "")).strip().casefold():
                raise ValueError("A replacement must retain the source's logical name")
            try:
                expected_version = int(previous.get("version", 1)) + 1
                actual_version = int(source.get("version", 0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Source versions must be positive integers") from exc
            if actual_version != expected_version:
                raise ValueError(f"Replacement must use source version {expected_version}")
            if any(isinstance(item, dict) and item.get("source_id") == source.get("source_id") for item in records):
                raise ValueError("Source identifier already exists in this draft")
            previous["superseded_from_status"] = previous.get("status", "draft")
            previous["status"] = "superseded"
            previous["superseded_by"] = source.get("source_id")
            previous["superseded_at"] = _now()
            source["supersedes_source_id"] = previous_source_id
            records.append(dict(source))
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            return self._persist_draft(tenant_id, brand_id, draft)

    @staticmethod
    def _snapshot_references_key(value: Any, storage_key: str) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key) in {"storage_key", "extraction_key"} and nested == storage_key:
                    return True
                if KnowledgePackStore._snapshot_references_key(nested, storage_key):
                    return True
        elif isinstance(value, list):
            return any(KnowledgePackStore._snapshot_references_key(item, storage_key) for item in value)
        return False

    def remove_unpublished_source(
        self, tenant_id: str, brand_id: str, draft_id: str, source_id: str, actor_id: str,
    ) -> dict[str, Any]:
        """Remove an unapproved source only when no fact or immutable version uses it."""
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") == "PUBLISHED":
                raise ValueError("Published Knowledge Pack drafts are immutable")
            registry = draft.get("snapshot", {}).get("sources", {}) or {}
            records = registry.get("sources", []) if isinstance(registry, dict) else []
            source = next((item for item in records if isinstance(item, dict) and item.get("source_id") == source_id), None)
            if source is None:
                raise FileNotFoundError("Source record not found")
            if source.get("status") == "approved":
                raise ValueError("An approved source cannot be deleted; supersede it with a new version instead")
            if source.get("superseded_by"):
                raise ValueError("A source with a successor version cannot be deleted; delete the latest version first")
            for index, fact in enumerate(draft.get("snapshot", {}).get("facts", [])):
                ref = fact.get("source_ref") if isinstance(fact, dict) else None
                if isinstance(ref, dict) and str(ref.get("source_id")) == source_id:
                    raise ValueError(f"Source is referenced by fact at facts[{index}]; update the fact provenance before deletion")

            keys = [str(source.get(key)) for key in ("storage_key", "extraction_key") if source.get(key)]
            if keys:
                if self.session_factory is not None:
                    with self._database(tenant_id, brand_id) as db:
                        versions = db.scalars(select(models.BrandKnowledgePackVersion).where(
                            models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                            models.BrandKnowledgePackVersion.brand_id == brand_id,
                        )).all()
                        if any(self._snapshot_references_key(row.snapshot, key) for row in versions for key in keys):
                            raise ValueError("Source objects are referenced by immutable published history and cannot be deleted")
                        other_drafts = db.scalars(select(models.BrandKnowledgePackDraft).where(
                            models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                            models.BrandKnowledgePackDraft.brand_id == brand_id,
                            models.BrandKnowledgePackDraft.draft_id != draft_id,
                        )).all()
                        if any(self._snapshot_references_key(row.snapshot, key) for row in other_drafts for key in keys):
                            raise ValueError("Source objects are referenced by another draft and cannot be deleted")
                else:
                    versions_root = self.active_root(tenant_id, brand_id).parent
                    for version_root in versions_root.iterdir() if versions_root.exists() else []:
                        if version_root.is_dir() and (version_root / "version.json").exists():
                            snap = BrandPack(root=version_root).snapshot()
                            if any(self._snapshot_references_key(snap, key) for key in keys):
                                raise ValueError("Source objects are referenced by immutable published history and cannot be deleted")
                    drafts_root = self._brand_root(tenant_id, brand_id) / "drafts"
                    for draft_file in drafts_root.glob("*.json") if drafts_root.exists() else []:
                        if draft_file.stem == draft_id:
                            continue
                        try:
                            other = self._read_json(draft_file)
                        except (OSError, ValueError, json.JSONDecodeError):
                            continue
                        if any(self._snapshot_references_key(other.get("snapshot", {}), key) for key in keys):
                            raise ValueError("Source objects are referenced by another draft and cannot be deleted")

            predecessor_id = source.get("supersedes_source_id")
            if predecessor_id:
                predecessor = next(
                    (item for item in records if isinstance(item, dict) and item.get("source_id") == predecessor_id),
                    None,
                )
                if predecessor is None or predecessor.get("superseded_by") != source_id:
                    raise ValueError("Source version lineage is inconsistent; deletion is blocked for manual reconciliation")
                predecessor["status"] = predecessor.pop("superseded_from_status", "draft")
                predecessor.pop("superseded_by", None)
                predecessor.pop("superseded_at", None)
            registry["sources"] = [item for item in records if not (isinstance(item, dict) and item.get("source_id") == source_id)]
            draft["snapshot"]["sources"] = registry
            draft["status"] = "DRAFT"
            draft["validation"] = None
            draft["updated_at"] = _now()
            draft["updated_by"] = actor_id
            self._persist_draft(tenant_id, brand_id, draft)
            return deepcopy(source)

    def append_asset(
        self, tenant_id: str, brand_id: str, draft_id: str, asset: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        if self.session_factory is not None:
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
            return self._persist_draft(tenant_id, brand_id, draft)
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

    def update_scan_record(
        self, tenant_id: str, brand_id: str, draft_id: str, record_type: str, record_id: str,
        updates: dict[str, Any], actor_id: str,
    ) -> dict[str, Any]:
        """Update only machine-owned scan/extraction metadata after a rescan.

        This is intentionally narrower than ``update_section``: callers cannot
        change approval state, actor provenance, storage location or original hash.
        """
        allowed = {
            "source": {"scan_status", "scan_engine", "scan_scanned_at", "scan_signature",
                       "extraction_key", "extraction_status", "extraction_warnings",
                       "region_count", "reference_text", "sha256"},
            "asset": {"scan_status", "scan_engine", "scan_scanned_at", "scan_signature"},
        }
        if record_type not in allowed or set(updates) - allowed[record_type]:
            raise ValueError("Unsupported security scan metadata update")
        draft = self.get_draft(tenant_id, draft_id, brand_id)
        if draft.get("status") == "PUBLISHED":
            raise ValueError("Published Knowledge Pack drafts are immutable")
        snapshot = draft.get("snapshot", {})
        if record_type == "source":
            records = (snapshot.get("sources", {}) or {}).get("sources", [])
            id_field = "source_id"
        else:
            records = (snapshot.get("assets", {}) or {}).get("approved_assets", [])
            id_field = "asset_id"
        record = next((item for item in records if isinstance(item, dict) and str(item.get(id_field)) == record_id), None)
        if record is None:
            raise FileNotFoundError("Knowledge record not found")
        record.update(deepcopy(updates))
        if record.get("scan_status") != "CLEAN" and record.get("status") == "approved":
            record["status"] = "draft"
            record.pop("approved_by", None)
            record.pop("approved_at", None)
            record["decision_by"] = actor_id
            record["decision_at"] = _now()
            record["decision_reason"] = "Approval suspended because a new malware scan did not return CLEAN."
        draft["status"] = "DRAFT"
        draft["validation"] = None
        draft["updated_at"] = _now()
        draft["updated_by"] = actor_id
        return self._persist_draft(tenant_id, brand_id, draft)

    @staticmethod
    def _validate_policy_source_reference(snapshot: dict[str, Any], policy: dict[str, Any]) -> None:
        """Require new policy clauses to cite an approved source version and exact excerpt."""
        if not policy.get("source_provenance_required"):
            return
        source_ref = policy.get("source_ref")
        if not isinstance(source_ref, dict) or not source_ref.get("source_id"):
            raise ValueError("POLICY_SOURCE_PROVENANCE_REQUIRED: a new policy clause must reference an approved source record")
        source_rows = (snapshot.get("sources", {}) or {}).get("sources", [])
        source = next((
            item for item in source_rows
            if isinstance(item, dict)
            and str(item.get("source_id")) == str(source_ref.get("source_id"))
        ), None)
        if source is None or source.get("status") != "approved":
            raise ValueError("POLICY_SOURCE_NOT_APPROVED: the policy clause must reference an owner-approved source")
        try:
            if int(source_ref.get("source_version", 0)) != int(source.get("version", 1)):
                raise ValueError("POLICY_SOURCE_VERSION_MISMATCH: the policy must cite the exact approved source version")
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("POLICY_SOURCE_VERSION_MISMATCH"):
                raise
            raise ValueError("POLICY_SOURCE_VERSION_INVALID: source version must be a positive integer") from exc
        quote = str(source_ref.get("quote", "")).strip()
        reference_text = str(source.get("reference_text") or "")
        if not quote or not reference_text.strip():
            raise ValueError("POLICY_SOURCE_QUOTE_REQUIRED: retain the exact policy clause excerpt in the approved source")
        if quote not in reference_text:
            raise ValueError("POLICY_SOURCE_QUOTE_NOT_FOUND: the policy excerpt is not present in the approved source text")
        if source.get("storage_key") and (source.get("scan_status") != "CLEAN" or source.get("extraction_status") != "COMPLETED"):
            raise ValueError("POLICY_SOURCE_NOT_READY: uploaded source must pass scanning and complete extraction")

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
        if self.session_factory is not None:
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
            if status == "approved" and record_type == "policy":
                self._validate_policy_source_reference(snapshot, record)
            if status == "approved" and record_type == "source" and record.get("storage_key"):
                if record.get("scan_status") != "CLEAN":
                    raise ValueError("SOURCE_MALWARE_SCAN_REQUIRED: the uploaded source must pass malware scanning before approval")
                if record.get("extraction_status") != "COMPLETED" or not str(record.get("reference_text") or "").strip():
                    raise ValueError("SOURCE_EXTRACTION_INCOMPLETE: the uploaded source needs complete, readable extracted text before approval")
            if status == "approved" and record_type == "asset" and record.get("storage_key"):
                if record.get("scan_status") != "CLEAN":
                    raise ValueError("ASSET_MALWARE_SCAN_REQUIRED: the uploaded asset must pass malware scanning before approval")
            record["status"] = status
            record["owner_id"] = record.get("owner_id") or actor_id
            record["decision_by"] = actor_id
            record["decision_at"] = _now()
            clean_reason = (reason or "").strip()
            record["decision_reason"] = clean_reason or None
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
            return self._persist_draft(
                tenant_id,
                brand_id,
                draft,
                decision={
                    "record_type": record_type,
                    "record_id": record_id,
                    "status": status,
                    "reason": clean_reason or "No reason supplied",
                    "actor_id": actor_id,
                    "created_at": _now(),
                },
            )
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
            if status == "approved" and record_type == "policy":
                self._validate_policy_source_reference(snapshot, record)
            if status == "approved" and record_type == "source" and record.get("storage_key"):
                if record.get("scan_status") != "CLEAN":
                    raise ValueError("SOURCE_MALWARE_SCAN_REQUIRED: the uploaded source must pass malware scanning before approval")
                if record.get("extraction_status") != "COMPLETED" or not str(record.get("reference_text") or "").strip():
                    raise ValueError("SOURCE_EXTRACTION_INCOMPLETE: the uploaded source needs complete, readable extracted text before approval")
            if status == "approved" and record_type == "asset" and record.get("storage_key"):
                if record.get("scan_status") != "CLEAN":
                    raise ValueError("ASSET_MALWARE_SCAN_REQUIRED: the uploaded asset must pass malware scanning before approval")
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
            validation_items = self._validate(snapshot, require_identity=True, base_brand_id=None)
            conflict_codes = {"APPROVED_FACT_CONFLICT", "APPROVED_POLICY_CONFLICT", "APPROVED_TERMINOLOGY_CONFLICT"}
            errors = [item for item in validation_items if item.get("code") not in conflict_codes]
            warnings: list[dict[str, str]] = [
                {**item, "message": item["message"] + " This conflict remains visible to retrieval and must be resolved or explicitly governed; it is not silently ranked away."}
                for item in validation_items if item.get("code") in conflict_codes
            ]
            asset_manifest = snapshot.get("assets", {}) if isinstance(snapshot, dict) else {}
            if isinstance(asset_manifest, dict):
                for kind, policy in (asset_manifest.get("usage_policies", {}) or {}).items():
                    if isinstance(policy, dict) and float(policy.get("clear_space_ratio", 0) or 0) > 0:
                        warnings.append({
                            "code": "ASSET_CLEAR_SPACE_MANUAL_REVIEW",
                            "path": f"assets.usage_policies.{kind}.clear_space_ratio",
                            "message": f"The {kind} policy requires {float(policy['clear_space_ratio']):.0%} clear space. Sigillum records this requirement but does not automatically certify geometric clear space; inspect the original asset before approval.",
                        })
            active_root = self.active_root(tenant_id, brand_id)
            active_pack = self.active_pack(tenant_id, brand_id)
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
                if asset.get("status") == "approved" and asset.get("storage_key") and asset.get("scan_status") != "CLEAN":
                    errors.append({"code": "ASSET_MALWARE_SCAN_REQUIRED", "path": f"assets.approved_assets[{index}].scan_status", "message": "Approved uploaded assets must have a successful malware scan."})
                elif asset.get("storage_key") and asset.get("scan_status") != "CLEAN":
                    warnings.append({"code": "ASSET_QUARANTINED_PENDING_SCAN", "path": f"assets.approved_assets[{index}].scan_status", "message": "The uploaded asset remains private and cannot be used until malware scanning succeeds."})
                if asset.get("status") == "approved" and asset.get("storage_key") and (not asset.get("approved_by") or not asset.get("approved_at")):
                    errors.append({"code": "ASSET_APPROVAL_PROVENANCE_REQUIRED", "path": f"assets.approved_assets[{index}]", "message": "Approved uploaded assets require an approving owner and timestamp."})

            sources = (snapshot.get("sources") or {}).get("sources", [])
            for index, source in enumerate(sources if isinstance(sources, list) else []):
                if not isinstance(source, dict) or not source.get("storage_key"):
                    continue
                storage_key = str(source["storage_key"])
                expected_prefix = f"brand-source-documents/{tenant_id}/{brand_id or self.DEFAULT_BRAND_ID}/"
                if not storage_key.startswith(expected_prefix):
                    errors.append({"code": "SOURCE_STORAGE_SCOPE_INVALID", "path": f"sources.sources[{index}].storage_key", "message": "Uploaded source storage keys must remain inside the current tenant and brand namespace."})
                    continue
                if source.get("status") == "approved":
                    if source.get("scan_status") != "CLEAN":
                        errors.append({"code": "SOURCE_MALWARE_SCAN_REQUIRED", "path": f"sources.sources[{index}].scan_status", "message": "Approved uploaded sources must have a successful malware scan."})
                    if source.get("extraction_status") != "COMPLETED" or not str(source.get("reference_text") or "").strip():
                        errors.append({"code": "SOURCE_EXTRACTION_INCOMPLETE", "path": f"sources.sources[{index}].extraction_status", "message": "Approved uploaded sources require complete extracted text."})
                    expected_file_hash = str(source.get("file_sha256", "")).lower()
                    if not re.fullmatch(r"[0-9a-f]{64}", expected_file_hash):
                        errors.append({"code": "SOURCE_FILE_HASH_REQUIRED", "path": f"sources.sources[{index}].file_sha256", "message": "Approved uploaded sources require the original file SHA-256."})
                    if asset_exists is not None:
                        try:
                            if not asset_exists(storage_key):
                                errors.append({"code": "SOURCE_OBJECT_MISSING", "path": f"sources.sources[{index}].storage_key", "message": "The uploaded source object is missing from private storage."})
                        except Exception:
                            errors.append({"code": "SOURCE_OBJECT_UNAVAILABLE", "path": f"sources.sources[{index}].storage_key", "message": "The uploaded source object could not be verified in private storage."})
                    if asset_hash is not None and expected_file_hash:
                        try:
                            if str(asset_hash(storage_key)).lower() != expected_file_hash:
                                errors.append({"code": "SOURCE_FILE_HASH_MISMATCH", "path": f"sources.sources[{index}].file_sha256", "message": "The original source bytes no longer match the recorded SHA-256."})
                        except Exception:
                            errors.append({"code": "SOURCE_OBJECT_UNAVAILABLE", "path": f"sources.sources[{index}].storage_key", "message": "The uploaded source object could not be hash-verified."})
                elif source.get("scan_status") != "CLEAN":
                    warnings.append({"code": "SOURCE_QUARANTINED_PENDING_SCAN", "path": f"sources.sources[{index}].scan_status", "message": "The uploaded source remains private and cannot be used as authoritative evidence until malware scanning succeeds."})

            result = {"valid": not errors, "errors": errors, "warnings": warnings, "validated_at": _now()}
            draft["validation"] = result
            draft["status"] = "VALIDATED" if not errors else "DRAFT"
            draft["updated_at"] = _now()
            if self.session_factory is not None:
                self._persist_draft(tenant_id, brand_id or self.DEFAULT_BRAND_ID, draft)
            else:
                _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft)
            return result

    def _publish_draft_database(
        self, tenant_id: str, draft_id: str, actor_id: str, brand_id: str
    ) -> dict[str, Any]:
        version_root: Path | None = None
        metadata: dict[str, Any] | None = None
        draft_export: dict[str, Any] | None = None
        pack_root = self._pack_root(tenant_id, brand_id)
        with self._database(tenant_id, brand_id) as db:
            head = db.scalar(select(models.BrandKnowledgePackHead).where(
                models.BrandKnowledgePackHead.tenant_id == tenant_id,
                models.BrandKnowledgePackHead.brand_id == brand_id,
            ).with_for_update())
            draft_row = db.scalar(select(models.BrandKnowledgePackDraft).where(
                models.BrandKnowledgePackDraft.tenant_id == tenant_id,
                models.BrandKnowledgePackDraft.brand_id == brand_id,
                models.BrandKnowledgePackDraft.draft_id == draft_id,
            ).with_for_update())
            if head is None or draft_row is None:
                raise FileNotFoundError("Draft Knowledge Pack not found")
            if draft_row.status != "VALIDATED" or not (draft_row.validation or {}).get("valid"):
                raise ValueError("Validate the draft successfully before publishing")
            if head.active_version_id != draft_row.base_version_id or head.active_fingerprint != draft_row.base_fingerprint:
                raise RuntimeError("This draft is stale because another Knowledge Pack version was published. Create a new draft from the active version.")

            snapshot = deepcopy(draft_row.snapshot)
            conflict_codes = {"APPROVED_FACT_CONFLICT", "APPROVED_POLICY_CONFLICT", "APPROVED_TERMINOLOGY_CONFLICT"}
            errors = [item for item in self._validate(snapshot, require_identity=True) if item.get("code") not in conflict_codes]
            if errors:
                raise ValueError("Draft validation is no longer valid")
            active_version = db.scalar(select(models.BrandKnowledgePackVersion).where(
                models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                models.BrandKnowledgePackVersion.brand_id == brand_id,
                models.BrandKnowledgePackVersion.version_id == head.active_version_id,
            ))
            if active_version is None:
                raise RuntimeError("Active Knowledge Pack version is missing")
            active_meta = self._version_dict(active_version, is_active=True)
            versions = db.scalars(select(models.BrandKnowledgePackVersion).where(
                models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                models.BrandKnowledgePackVersion.brand_id == brand_id,
            )).all()
            version_numbers = [
                int(match.group(1))
                for row in versions
                if (match := re.match(r"^v(\d+)$", row.version_id))
            ]
            next_number = max(version_numbers or [0]) + 1
            version_id = f"v{next_number:04d}"
            version_root = pack_root / "versions" / version_id
            if version_root.exists():
                # A previous process may have left an orphan after a failed DB
                # commit. It is safe to clear only because no catalogue row exists.
                existing = db.scalar(select(models.BrandKnowledgePackVersion.id).where(
                    models.BrandKnowledgePackVersion.tenant_id == tenant_id,
                    models.BrandKnowledgePackVersion.brand_id == brand_id,
                    models.BrandKnowledgePackVersion.version_id == version_id,
                ))
                if existing is not None:
                    raise RuntimeError("Version identifier collision; publication aborted")
                shutil.rmtree(version_root)
            new_pack_version = self._next_semver(str(active_meta.get("pack_version", "1.0.0")))
            snapshot.setdefault("brand", {})["pack_version"] = new_pack_version
            fingerprint = _canonical_hash(snapshot)

            # Materialise the immutable file view before the database transaction
            # commits. If any write fails, the authoritative pointer is unchanged.
            active_root = pack_root / "versions" / head.active_version_id
            self._write_snapshot(version_root, snapshot, copy_assets_from=active_root, copy_seed_assets=False)
            now = datetime.now(timezone.utc)
            metadata = {
                "version_id": version_id,
                "pack_id": head.pack_id,
                "brand_id": brand_id,
                "pack_version": new_pack_version,
                "fingerprint": fingerprint,
                "status": "PUBLISHED",
                "created_at": now.isoformat(),
                "created_by": actor_id,
                "base_version_id": head.active_version_id,
                "draft_id": draft_id,
            }
            _write_json_atomic(version_root / "version.json", metadata)
            db.add(models.BrandKnowledgePackVersion(
                tenant_id=tenant_id,
                brand_id=brand_id,
                pack_id=head.pack_id,
                version_id=version_id,
                pack_version=new_pack_version,
                fingerprint=fingerprint,
                status="PUBLISHED",
                base_version_id=head.active_version_id,
                snapshot=snapshot,
                created_by=actor_id,
                created_at=now,
            ))
            expected_active_version = head.active_version_id
            expected_revision = head.revision
            result = db.execute(update(models.BrandKnowledgePackHead).where(
                models.BrandKnowledgePackHead.id == head.id,
                models.BrandKnowledgePackHead.active_version_id == expected_active_version,
                models.BrandKnowledgePackHead.revision == expected_revision,
            ).values(
                active_version_id=version_id,
                active_fingerprint=fingerprint,
                revision=expected_revision + 1,
                updated_at=now,
            ))
            if result.rowcount != 1:
                raise RuntimeError("The active Knowledge Pack changed concurrently. Reload and publish from a new draft.")
            draft_row.status = "PUBLISHED"
            draft_row.published_version_id = version_id
            draft_row.published_fingerprint = fingerprint
            draft_row.updated_at = now
            draft_row.updated_by = actor_id
            draft_row.revision += 1
            draft_export = self._draft_dict(draft_row)

        # Database head is authoritative. The file pointer is only a compatibility
        # mirror used by older local tooling and is repaired on the next read.
        try:
            _write_json_atomic(pack_root / "active.json", {
                "version_id": metadata["version_id"],
                "fingerprint": metadata["fingerprint"],
                "activated_at": metadata["created_at"],
            })
            _write_json_atomic(self._draft_path(tenant_id, draft_id, brand_id), draft_export)
        except OSError:
            # The immutable snapshot and active pointer are safely committed in
            # the database; a failed mirror write must not report a false rollback.
            pass
        return metadata

    def publish_draft(
        self, tenant_id: str, draft_id: str, actor_id: str, brand_id: str | None = None
    ) -> dict[str, Any]:
        if self.session_factory is not None:
            return self._publish_draft_database(tenant_id, draft_id, actor_id, brand_id or self.DEFAULT_BRAND_ID)
        with self._lock:
            draft = self.get_draft(tenant_id, draft_id, brand_id)
            if draft.get("status") != "VALIDATED" or not (draft.get("validation") or {}).get("valid"):
                raise ValueError("Validate the draft successfully before publishing")
            active_root = self.active_root(tenant_id, brand_id)
            active_meta = self._read_json(active_root / "version.json")
            if active_meta["version_id"] != draft.get("base_version_id"):
                raise RuntimeError("This draft is stale because another Knowledge Pack version was published. Create a new draft from the active version.")
            snapshot = draft["snapshot"]
            conflict_codes = {"APPROVED_FACT_CONFLICT", "APPROVED_POLICY_CONFLICT", "APPROVED_TERMINOLOGY_CONFLICT"}
            errors = [item for item in self._validate(snapshot, require_identity=True) if item.get("code") not in conflict_codes]
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
            if not str(policy.get("name", "")).strip():
                add("POLICY_NAME_REQUIRED", f"{path}.name", "Every policy requires a human-readable name.")
            if not str(policy.get("rule", "")).strip():
                add("POLICY_RULE_REQUIRED", f"{path}.rule", "Every policy requires an explicit rule or requirement.")
            if policy.get("severity") and policy["severity"] not in ALLOWED_SEVERITIES:
                add("POLICY_SEVERITY_INVALID", f"{path}.severity", "Severity must be blocking, review_required, suggestion or informational.")
            allowed_actions = {"review", "correct", "remove", "disclose", "manual_check", "block", "warn", "escalate"}
            action = policy.get("required_action", policy.get("action"))
            if action is not None and action not in allowed_actions:
                add("POLICY_ACTION_INVALID", f"{path}.required_action", "Policy action is not one of the supported deterministic routes.")
            policy_scope = policy.get("scope", {})
            if policy_scope is not None and not isinstance(policy_scope, dict):
                add("POLICY_SCOPE_INVALID", f"{path}.scope", "Policy scope must be an object with explicit dimensions.")
            elif isinstance(policy_scope, dict):
                for scope_field, scope_value in policy_scope.items():
                    if scope_value is None:
                        continue
                    if not isinstance(scope_value, (str, list, tuple)):
                        add("POLICY_SCOPE_VALUE_INVALID", f"{path}.scope.{scope_field}", "Scope values must be text or a list of text values.")
                    elif isinstance(scope_value, (list, tuple)) and any(not isinstance(item, str) or not item.strip() for item in scope_value):
                        add("POLICY_SCOPE_VALUE_INVALID", f"{path}.scope.{scope_field}", "Scope lists must contain non-empty text values only.")
            policy_dates: dict[str, datetime] = {}
            for temporal_field in ("valid_from", "valid_until"):
                raw_value = policy.get(temporal_field)
                if raw_value in (None, ""):
                    continue
                if not isinstance(raw_value, str):
                    add("POLICY_TEMPORAL_VALUE_INVALID", f"{path}.{temporal_field}", "Policy validity timestamps must be timezone-aware ISO-8601 strings.")
                    continue
                try:
                    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        raise ValueError
                    policy_dates[temporal_field] = parsed
                except ValueError:
                    add("POLICY_TEMPORAL_VALUE_INVALID", f"{path}.{temporal_field}", "Policy validity timestamps must be timezone-aware ISO-8601 strings.")
            if policy_dates.get("valid_from") and policy_dates.get("valid_until") and policy_dates["valid_until"] < policy_dates["valid_from"]:
                add("POLICY_VALIDITY_INTERVAL_INVALID", path, "Policy valid_until must be later than or equal to valid_from.")
            if policy.get("status") == "approved" and (not policy.get("approved_by") or not policy.get("approved_at")):
                add("POLICY_APPROVAL_PROVENANCE_REQUIRED", path, "Approved policies require an approving owner and timestamp.")

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
            traits = voice.get("voice_traits", [])
            if isinstance(traits, list):
                seen_traits: set[str] = set()
                for index, trait in enumerate(traits):
                    if not isinstance(trait, str) or not trait.strip():
                        add("VOICE_TRAIT_INVALID", f"voice.voice_traits[{index}]", "Voice traits must be non-empty text values.")
                        continue
                    trait_key = trait.strip().casefold()
                    if trait_key in seen_traits:
                        add("DUPLICATE_VOICE_TRAIT", f"voice.voice_traits[{index}]", "Duplicate voice traits should be consolidated.")
                    seen_traits.add(trait_key)
            examples = voice.get("approved_examples", [])
            if isinstance(examples, list):
                seen_examples: set[str] = set()
                for index, example in enumerate(examples):
                    path = f"voice.approved_examples[{index}]"
                    if not isinstance(example, dict):
                        add("VOICE_EXAMPLE_INVALID", path, "Each approved voice example must be an object.")
                        continue
                    example_id = str(example.get("example_id", "")).strip()
                    if not example_id:
                        add("VOICE_EXAMPLE_ID_REQUIRED", f"{path}.example_id", "Every voice example requires an example_id.")
                    elif example_id in seen_examples:
                        add("DUPLICATE_VOICE_EXAMPLE_ID", f"{path}.example_id", f"Duplicate voice example ID: {example_id}.")
                    seen_examples.add(example_id)
                    if not str(example.get("text", "")).strip():
                        add("VOICE_EXAMPLE_TEXT_REQUIRED", f"{path}.text", "Voice examples require non-empty text.")
                    if not isinstance(example.get("labels", []), list):
                        add("VOICE_EXAMPLE_LABELS_INVALID", f"{path}.labels", "Voice example labels must be an array.")
            patterns = voice.get("disallowed_patterns", [])
            if isinstance(patterns, list):
                seen_patterns: set[str] = set()
                for index, pattern in enumerate(patterns):
                    path = f"voice.disallowed_patterns[{index}]"
                    if not isinstance(pattern, dict):
                        add("VOICE_PATTERN_INVALID", path, "Each disallowed voice pattern must be an object.")
                        continue
                    phrase = str(pattern.get("pattern", "")).strip()
                    if not phrase:
                        add("VOICE_PATTERN_TEXT_REQUIRED", f"{path}.pattern", "Disallowed voice patterns require non-empty text.")
                    phrase_key = phrase.casefold()
                    locale_key = str(pattern.get("locale", "")).strip().casefold()
                    duplicate_key = f"{locale_key}::{phrase_key}"
                    if phrase and duplicate_key in seen_patterns:
                        add("DUPLICATE_VOICE_PATTERN", f"{path}.pattern", "Duplicate disallowed voice patterns should be consolidated.")
                    seen_patterns.add(duplicate_key)
                    if pattern.get("severity") and pattern.get("severity") not in ALLOWED_SEVERITIES:
                        add("VOICE_PATTERN_SEVERITY_INVALID", f"{path}.severity", "Voice pattern severity must be blocking, review_required, suggestion or informational.")

        assets = snapshot.get("assets")
        if not isinstance(assets, dict):
            add("ASSETS_INVALID", "assets", "Asset manifest must be a JSON object.")
        else:
            policy_errors = validate_usage_policies(assets.get("usage_policies", {}), brand.get("channels", []))
            errors.extend(policy_errors)
            usage_policies = assets.get("usage_policies", {}) if isinstance(assets.get("usage_policies", {}), dict) else {}
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
                    policy = usage_policies.get(asset.get("kind"))
                    if asset.get("status") == "approved" and isinstance(policy, dict):
                        try:
                            width, height = int(asset.get("width", 0)), int(asset.get("height", 0))
                        except (TypeError, ValueError):
                            width, height = 0, 0
                        minimum_width = int(policy.get("min_width", 0) or 0)
                        minimum_height = int(policy.get("min_height", 0) or 0)
                        if width < minimum_width:
                            add("ASSET_MIN_WIDTH_NOT_MET", f"{path}.width", f"Approved {asset.get('kind')} assets require at least {minimum_width}px width; this asset is {width}px.")
                        if height < minimum_height:
                            add("ASSET_MIN_HEIGHT_NOT_MET", f"{path}.height", f"Approved {asset.get('kind')} assets require at least {minimum_height}px height; this asset is {height}px.")
                        allowed_palette = policy.get("palette_hex") or []
                        if (
                            isinstance(allowed_palette, list)
                            and allowed_palette
                            and all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in allowed_palette)
                        ):
                            measured_palette = asset.get("palette")
                            if not isinstance(measured_palette, list) or not measured_palette:
                                add(
                                    "ASSET_PALETTE_UNMEASURABLE",
                                    f"{path}.palette",
                                    "A palette rule is configured, but this asset has no measured palette. Re-upload the asset to extract its palette or remove the palette rule.",
                                )
                            else:
                                tolerance = policy.get("palette_tolerance", 80)
                                required_ratio = policy.get("minimum_palette_match_ratio", 0.7)
                                if (
                                    isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool)
                                    and isinstance(required_ratio, (int, float)) and not isinstance(required_ratio, bool)
                                ):
                                    score = palette_match_ratio(measured_palette, allowed_palette, float(tolerance))
                                    if score < float(required_ratio):
                                        add("ASSET_PALETTE_POLICY_NOT_MET", f"{path}.palette", f"Only {score:.0%} of the measured palette is within the approved brand palette tolerance; at least {float(required_ratio):.0%} is required.")

        sources = snapshot.get("sources", {"sources": []})
        if not isinstance(sources, dict) or not isinstance(sources.get("sources", []), list):
            add("SOURCES_INVALID", "sources", "Source registry must contain a sources array.")
        else:
            seen_sources: set[str] = set()
            source_by_id: dict[str, dict[str, Any]] = {}
            logical_source_versions: set[tuple[str, int]] = set()
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
                if source_id:
                    source_by_id[source_id] = source
                if not str(source.get("name", "")).strip():
                    add("SOURCE_NAME_REQUIRED", f"{path}.name", "Every source requires a display name.")
                if source.get("status", "draft") not in ALLOWED_RECORD_STATUSES:
                    add("SOURCE_STATUS_INVALID", f"{path}.status", "Unsupported source status.")
                if source.get("source_type", "reference_text") not in {"reference_text", "policy_document", "product_specification", "campaign_terms", "guideline", "other"}:
                    add("SOURCE_TYPE_INVALID", f"{path}.source_type", "Unsupported source type.")
                try:
                    source_version = int(source.get("version", 1))
                    if source_version < 1:
                        raise ValueError
                    logical_key = (str(source.get("name", "")).strip().casefold(), source_version)
                    if logical_key[0] and logical_key in logical_source_versions:
                        add("SOURCE_LOGICAL_VERSION_DUPLICATE", f"{path}.version", "A logical source name cannot have duplicate version numbers in one draft.")
                    logical_source_versions.add(logical_key)
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

            def _parsed_scope_date(value: Any) -> datetime | None:
                if not value:
                    return None
                try:
                    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    return parsed if parsed.tzinfo is not None else None
                except (TypeError, ValueError):
                    return None

            def _validity_overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
                left_start = _parsed_scope_date(left.get("valid_from"))
                left_end = _parsed_scope_date(left.get("valid_until"))
                right_start = _parsed_scope_date(right.get("valid_from"))
                right_end = _parsed_scope_date(right.get("valid_until"))
                if left_end and right_start and left_end < right_start:
                    return False
                if right_end and left_start and right_end < left_start:
                    return False
                return True

            def _scope_values(record: dict[str, Any], field: str) -> set[str]:
                nested = record.get("scope") if isinstance(record.get("scope"), dict) else {}
                raw = record.get(field)
                if raw in (None, ""):
                    raw = nested.get(field)
                if raw in (None, ""):
                    return set()
                values = raw if isinstance(raw, (list, tuple, set)) else [raw]
                return {str(item).strip().casefold() for item in values if str(item).strip()}

            def _scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
                # An omitted dimension is broad scope; explicit differing values
                # are disjoint. Lists support policies which apply to multiple scopes.
                dimensions = (
                    "subject", "predicate", "product", "product_id", "offer_id",
                    "geography", "region", "channel", "locale", "audience", "population",
                )
                for field in dimensions:
                    left_values = _scope_values(left, field)
                    right_values = _scope_values(right, field)
                    if not left_values or not right_values:
                        continue
                    if {"all", "*"} & left_values or {"all", "*"} & right_values:
                        continue
                    if left_values.isdisjoint(right_values):
                        return False
                return True

            approved_facts = [
                (index, fact) for index, fact in enumerate(facts)
                if isinstance(fact, dict) and fact.get("status") == "approved"
            ]
            for position, (left_index, left) in enumerate(approved_facts):
                for right_index, right in approved_facts[position + 1 :]:
                    left_authority = left.get("source_precedence", left.get("authority_rank", 1))
                    right_authority = right.get("source_precedence", right.get("authority_rank", 1))
                    left_value = tuple(str(left.get(field, "")).strip().casefold() for field in ("value", "unit", "qualifier", "denominator", "comparator", "baseline", "period"))
                    right_value = tuple(str(right.get(field, "")).strip().casefold() for field in ("value", "unit", "qualifier", "denominator", "comparator", "baseline", "period"))
                    if (
                        _scopes_overlap(left, right)
                        and left_authority == right_authority
                        and left_value != right_value
                        and _validity_overlaps(left, right)
                    ):
                        add("APPROVED_FACT_CONFLICT", f"facts[{left_index}]", f"Approved fact conflicts with facts[{right_index}] at the same authority and overlapping scope/validity.")
                        add("APPROVED_FACT_CONFLICT", f"facts[{right_index}]", f"Approved fact conflicts with facts[{left_index}] at the same authority and overlapping scope/validity.")

            approved_policies = [
                (index, policy) for index, policy in enumerate(policies)
                if isinstance(policy, dict) and policy.get("status") == "approved"
            ]
            for position, (left_index, left) in enumerate(approved_policies):
                for right_index, right in approved_policies[position + 1 :]:
                    left_rule = str(left.get("conflict_key", left.get("rule_id", left.get("name", "")))).strip().casefold()
                    right_rule = str(right.get("conflict_key", right.get("rule_id", right.get("name", "")))).strip().casefold()
                    same_category = str(left.get("category", "")).strip().casefold() == str(right.get("category", "")).strip().casefold()
                    conflicting_action = (
                        left.get("severity"), left.get("required_action", left.get("action")),
                        left.get("enabled", True), left.get("decision", ""), str(left.get("rule", "")).strip().casefold(),
                    ) != (
                        right.get("severity"), right.get("required_action", right.get("action")),
                        right.get("enabled", True), right.get("decision", ""), str(right.get("rule", "")).strip().casefold(),
                    )
                    if (
                        left_rule and left_rule == right_rule and same_category
                        and _scopes_overlap(left, right)
                        and conflicting_action
                        and _validity_overlaps(left, right)
                    ):
                        add("APPROVED_POLICY_CONFLICT", f"policies[{left_index}]", f"Policy conflicts with policies[{right_index}] for the same rule and overlapping scope/validity.")
                        add("APPROVED_POLICY_CONFLICT", f"policies[{right_index}]", f"Policy conflicts with policies[{left_index}] for the same rule and overlapping scope/validity.")

            if isinstance(terminology, dict):
                preferred = terminology.get("preferred_terms", [])
                prohibited = terminology.get("prohibited_or_review_terms", [])
                preferred_rows = preferred if isinstance(preferred, list) else []
                prohibited_rows = prohibited if isinstance(prohibited, list) else []

                def _term_scope_values(record: dict[str, Any]) -> set[str]:
                    raw_scope = record.get("scope", [])
                    values = raw_scope if isinstance(raw_scope, (list, tuple, set)) else [raw_scope]
                    return {str(value).strip().casefold() for value in values if str(value).strip()}

                def _term_scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
                    left_scope, right_scope = _term_scope_values(left), _term_scope_values(right)
                    if not left_scope or not right_scope or {"all", "*"} & left_scope or {"all", "*"} & right_scope:
                        return True
                    return not left_scope.isdisjoint(right_scope)

                preferred_by_id = {
                    str(record.get("term_id")): record for record in preferred_rows
                    if isinstance(record, dict) and str(record.get("term_id", "")).strip()
                }
                for preferred_index, preferred_record in enumerate(preferred_rows):
                    if not isinstance(preferred_record, dict) or preferred_record.get("status", "approved") != "approved":
                        continue
                    preferred_text = str(preferred_record.get("preferred", "")).strip().casefold()
                    preferred_locale = str(preferred_record.get("locale", "")).strip().casefold()
                    for other_index, other_record in enumerate(preferred_rows[preferred_index + 1 :], preferred_index + 1):
                        if not isinstance(other_record, dict) or other_record.get("status", "approved") != "approved":
                            continue
                        other_text = str(other_record.get("preferred", "")).strip().casefold()
                        other_locale = str(other_record.get("locale", "")).strip().casefold()
                        locale_overlaps = not preferred_locale or not other_locale or preferred_locale == other_locale
                        if preferred_text and preferred_text == other_text and locale_overlaps and _term_scopes_overlap(preferred_record, other_record):
                            add("DUPLICATE_PREFERRED_TERMINOLOGY", f"terminology.preferred_terms[{other_index}]", f"Preferred term duplicates terminology.preferred_terms[{preferred_index}] in an overlapping locale/scope.")
                    for prohibited_index, prohibited_record in enumerate(prohibited_rows):
                        if not isinstance(prohibited_record, dict) or prohibited_record.get("status", "approved") != "approved":
                            continue
                        prohibited_text = str(prohibited_record.get("variant", "")).strip().casefold()
                        prohibited_locale = str(prohibited_record.get("locale", "")).strip().casefold()
                        locale_overlaps = not preferred_locale or not prohibited_locale or preferred_locale == prohibited_locale
                        if preferred_text and preferred_text == prohibited_text and locale_overlaps and _term_scopes_overlap(preferred_record, prohibited_record):
                            add("APPROVED_TERMINOLOGY_CONFLICT", f"terminology.preferred_terms[{preferred_index}]", f"Preferred term conflicts with terminology.prohibited_or_review_terms[{prohibited_index}] for an overlapping locale/scope.")
                            add("APPROVED_TERMINOLOGY_CONFLICT", f"terminology.prohibited_or_review_terms[{prohibited_index}]", f"Prohibited term conflicts with terminology.preferred_terms[{preferred_index}] for an overlapping locale/scope.")
                for prohibited_index, prohibited_record in enumerate(prohibited_rows):
                    if not isinstance(prohibited_record, dict):
                        continue
                    preferred_term_id = prohibited_record.get("preferred_term_id")
                    if preferred_term_id:
                        preferred_record = preferred_by_id.get(str(preferred_term_id))
                        if preferred_record is None:
                            add("TERMINOLOGY_PREFERRED_REFERENCE_MISSING", f"terminology.prohibited_or_review_terms[{prohibited_index}].preferred_term_id", "The linked preferred term does not exist in this Knowledge Pack draft.")
                        else:
                            link_locale = str(prohibited_record.get("locale", "")).strip().casefold()
                            preferred_locale = str(preferred_record.get("locale", "")).strip().casefold()
                            if link_locale and preferred_locale and link_locale != preferred_locale:
                                add("TERMINOLOGY_PREFERRED_LOCALE_MISMATCH", f"terminology.prohibited_or_review_terms[{prohibited_index}].preferred_term_id", "A prohibited variant and its preferred term must use the same locale.")
                            if not _term_scopes_overlap(prohibited_record, preferred_record):
                                add("TERMINOLOGY_PREFERRED_SCOPE_MISMATCH", f"terminology.prohibited_or_review_terms[{prohibited_index}].preferred_term_id", "A prohibited variant and its preferred term must have overlapping scope tags.")

            if isinstance(voice, dict):
                voice_examples = voice.get("approved_examples", [])
                voice_patterns = voice.get("disallowed_patterns", [])
                if isinstance(voice_examples, list) and isinstance(voice_patterns, list):
                    for example_index, example in enumerate(voice_examples):
                        if not isinstance(example, dict) or not str(example.get("text", "")).strip():
                            continue
                        example_locale = str(example.get("locale", "")).strip().casefold()
                        example_text = str(example.get("text", "")).casefold()
                        for pattern_index, pattern in enumerate(voice_patterns):
                            if not isinstance(pattern, dict):
                                continue
                            phrase = str(pattern.get("pattern", "")).strip()
                            pattern_locale = str(pattern.get("locale", "")).strip().casefold()
                            locale_overlaps = not example_locale or not pattern_locale or example_locale == pattern_locale
                            if phrase and locale_overlaps and phrase.casefold() in example_text:
                                add(
                                    "APPROVED_VOICE_EXAMPLE_CONFLICT",
                                    f"voice.approved_examples[{example_index}]",
                                    f"Approved voice example contains disallowed pattern from voice.disallowed_patterns[{pattern_index}]: {phrase}.",
                                )

            # Keep source replacement history a single, reciprocal version chain.
            successor_seen: set[str] = set()
            for index, source in enumerate(sources.get("sources", [])):
                if not isinstance(source, dict):
                    continue
                source_id = str(source.get("source_id", ""))
                path = f"sources.sources[{index}]"
                predecessor_id = source.get("supersedes_source_id")
                successor_id = source.get("superseded_by")
                if predecessor_id and str(predecessor_id) == source_id:
                    add("SOURCE_LINEAGE_SELF_REFERENCE", path, "A source version cannot supersede itself.")
                if successor_id and str(successor_id) == source_id:
                    add("SOURCE_LINEAGE_SELF_REFERENCE", path, "A source version cannot point to itself as its successor.")
                if predecessor_id:
                    predecessor = source_by_id.get(str(predecessor_id))
                    if predecessor is None:
                        add("SOURCE_PREDECESSOR_MISSING", f"{path}.supersedes_source_id", "The previous source version is missing from this draft history.")
                    else:
                        try:
                            consecutive = int(source.get("version", 0)) == int(predecessor.get("version", 0)) + 1
                        except (TypeError, ValueError):
                            consecutive = False
                        same_document = str(source.get("name", "")).strip().casefold() == str(predecessor.get("name", "")).strip().casefold()
                        reciprocal = str(predecessor.get("superseded_by", "")) == source_id and predecessor.get("status") == "superseded"
                        if not consecutive or not same_document or not reciprocal:
                            add("SOURCE_LINEAGE_INCONSISTENT", f"{path}.supersedes_source_id", "The source replacement link, logical name, version increment and predecessor state must agree.")
                if successor_id:
                    successor_key = str(successor_id)
                    if successor_key in successor_seen:
                        add("SOURCE_LINEAGE_MULTIPLE_SUCCESSORS", f"{path}.superseded_by", "A source version may have only one direct successor.")
                    successor_seen.add(successor_key)
                    successor = source_by_id.get(successor_key)
                    if successor is None or str(successor.get("supersedes_source_id", "")) != source_id or source.get("status") != "superseded":
                        add("SOURCE_LINEAGE_INCONSISTENT", f"{path}.superseded_by", "A superseded source must point to an existing successor that points back to it.")
                if source.get("status") == "superseded" and not successor_id:
                    add("SOURCE_SUPERSEDED_SUCCESSOR_REQUIRED", path, "A superseded source must identify the source version that replaced it.")
                if source.get("status") != "superseded" and successor_id:
                    add("SOURCE_SUPERSEDED_STATUS_REQUIRED", f"{path}.status", "A source with a successor must have superseded status.")
                if source.get("superseded_from_status") not in (None, "draft", "approved", "rejected", "not_approved"):
                    add("SOURCE_SUPERSEDED_ORIGIN_STATUS_INVALID", f"{path}.superseded_from_status", "The recorded pre-supersession state is not supported.")

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
                    elif not str(approved_source.get("reference_text") or "").strip():
                        add("FACT_SOURCE_TEXT_UNAVAILABLE", f"facts[{index}].source_ref.quote", "A source URI alone is provenance metadata; approved facts require retained source text against which the exact quote can be checked.")
                    elif quote not in str(approved_source["reference_text"]):
                        add("FACT_SOURCE_QUOTE_NOT_FOUND", f"facts[{index}].source_ref.quote", "The fact's source quote is not present in the approved source record's reference text.")

        source_rows_for_policy = (sources.get("sources", []) if isinstance(sources, dict) else [])
        approved_source_map = {
            str(item.get("source_id")): item for item in source_rows_for_policy
            if isinstance(item, dict) and item.get("status") == "approved"
        }
        for index, policy in enumerate(policies):
            if not isinstance(policy, dict) or policy.get("status") != "approved":
                continue
            if not policy.get("approved_by") or not policy.get("approved_at"):
                add("POLICY_APPROVAL_PROVENANCE_REQUIRED", f"policies[{index}]", "Approved policies require approved_by and approved_at.")
            if policy.get("source_provenance_required"):
                source_ref = policy.get("source_ref")
                source_id = source_ref.get("source_id") if isinstance(source_ref, dict) else None
                approved_source = approved_source_map.get(str(source_id)) if source_id else None
                if approved_source is None:
                    add("POLICY_SOURCE_NOT_APPROVED", f"policies[{index}].source_ref", "A new approved policy must link to an approved source registry record.")
                else:
                    try:
                        if int(source_ref.get("source_version", 0)) != int(approved_source.get("version", 1)):
                            add("POLICY_SOURCE_VERSION_MISMATCH", f"policies[{index}].source_ref.source_version", "The policy must cite the exact approved source version.")
                    except (TypeError, ValueError):
                        add("POLICY_SOURCE_VERSION_INVALID", f"policies[{index}].source_ref.source_version", "Source version must be a positive integer.")
                    quote = str(source_ref.get("quote", "")).strip()
                    reference_text = str(approved_source.get("reference_text") or "")
                    if not quote or not reference_text.strip():
                        add("POLICY_SOURCE_QUOTE_REQUIRED", f"policies[{index}].source_ref.quote", "Approved policies require the exact clause excerpt and retained source text.")
                    elif quote not in reference_text:
                        add("POLICY_SOURCE_QUOTE_NOT_FOUND", f"policies[{index}].source_ref.quote", "The policy excerpt is not present in the approved source text.")
                    if approved_source.get("storage_key") and (approved_source.get("scan_status") != "CLEAN" or approved_source.get("extraction_status") != "COMPLETED"):
                        add("POLICY_SOURCE_NOT_READY", f"policies[{index}].source_ref", "Uploaded policy source must pass malware scanning and complete extraction.")

        return errors
