from pathlib import Path

from sigillum.modules.knowledge.store import KnowledgePackStore


def seed_root() -> Path:
    return Path(__file__).parents[2] / "fixtures" / "brand_pack" / "v1"


def test_store_initializes_seed_as_immutable_v1(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")

    pack = store.active_pack("tenant_unit")
    metadata = store.active_metadata("tenant_unit")

    assert pack.version() == "1.0.0-demo"
    assert metadata["version_id"] == "v0001"
    assert metadata["is_active"] is True
    assert (store.active_root("tenant_unit") / "assets" / "orbita_primary_logo.svg").exists()


def test_publish_creates_a_new_immutable_version_and_preserves_previous(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    original_root = store.active_root("tenant_unit")
    original_hash = store.active_metadata("tenant_unit")["fingerprint"]

    draft = store.create_draft("tenant_unit", "owner-1")
    changed_brand = dict(draft["snapshot"]["brand"])
    changed_brand["description"] = "Updated synthetic brand description for a controlled test."
    store.update_section("tenant_unit", draft["draft_id"], "brand", changed_brand, "owner-1")

    result = store.validate_draft("tenant_unit", draft["draft_id"])
    assert result["valid"] is True

    published = store.publish_draft("tenant_unit", draft["draft_id"], "owner-1")
    active_pack = store.active_pack("tenant_unit")

    assert published["version_id"] == "v0002"
    assert published["pack_version"] == "1.0.1"
    assert active_pack.brand["description"] == changed_brand["description"]
    assert published["fingerprint"] != original_hash
    assert (original_root / "brand.json").exists()
    assert store._read_json(original_root / "version.json")["fingerprint"] == original_hash
    assert store.get_draft("tenant_unit", draft["draft_id"])["status"] == "PUBLISHED"


def test_invalid_duplicate_ids_cannot_be_published(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_unit", "owner-1")
    facts = list(draft["snapshot"]["facts"])
    facts.append(dict(facts[0]))
    store.update_section("tenant_unit", draft["draft_id"], "facts", facts, "owner-1")

    result = store.validate_draft("tenant_unit", draft["draft_id"])
    assert result["valid"] is False
    assert any(item["code"] == "DUPLICATE_FACT_ID" for item in result["errors"])

    try:
        store.publish_draft("tenant_unit", draft["draft_id"], "owner-1")
    except ValueError as exc:
        assert "Validate" in str(exc)
    else:
        raise AssertionError("An invalid draft must never be published")


def test_stale_draft_cannot_overwrite_a_newer_publication(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    first = store.create_draft("tenant_unit", "owner-1")
    second = store.create_draft("tenant_unit", "owner-1")

    for draft in (first, second):
        brand = dict(draft["snapshot"]["brand"])
        brand["description"] = f"Draft {draft['draft_id']}"
        store.update_section("tenant_unit", draft["draft_id"], "brand", brand, "owner-1")
        assert store.validate_draft("tenant_unit", draft["draft_id"])["valid"]

    store.publish_draft("tenant_unit", first["draft_id"], "owner-1")
    try:
        store.publish_draft("tenant_unit", second["draft_id"], "owner-1")
    except RuntimeError as exc:
        assert "stale" in str(exc).lower()
    else:
        raise AssertionError("A stale draft must not overwrite a newer publication")


def test_asset_manifest_rejects_cross_platform_path_traversal(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_unit", "owner-1")
    assets = dict(draft["snapshot"]["assets"])
    approved = [dict(item) for item in assets["approved_assets"]]
    approved[0]["file_path"] = "..\\private\\secret.svg"
    assets["approved_assets"] = approved
    store.update_section("tenant_unit", draft["draft_id"], "assets", assets, "owner-1")

    result = store.validate_draft("tenant_unit", draft["draft_id"])
    assert result["valid"] is False
    assert any(item["code"] == "ASSET_PATH_UNSAFE" for item in result["errors"])


def test_invalid_fact_temporal_intervals_cannot_be_published(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_unit", "owner-1")
    facts = [dict(item) for item in draft["snapshot"]["facts"]]
    facts[0]["valid_from"] = "2026-12-01T00:00:00+05:30"
    facts[0]["valid_until"] = "2026-11-01T00:00:00+05:30"
    store.update_section("tenant_unit", draft["draft_id"], "facts", facts, "owner-1")
    validation = store.validate_draft("tenant_unit", draft["draft_id"])
    assert validation["valid"] is False
    assert any(error["code"] == "FACT_VALIDITY_INTERVAL_INVALID" for error in validation["errors"])


def test_each_brand_in_a_tenant_has_an_isolated_knowledge_pack(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")

    alpha = store.active_pack("tenant_shared", "brand_alpha", "Alpha Brand")
    beta = store.active_pack("tenant_shared", "brand_beta", "Beta Brand")

    assert alpha.brand["brand_id"] == "brand_alpha"
    assert alpha.brand["brand_name"] == "Alpha Brand"
    assert beta.brand["brand_id"] == "brand_beta"
    assert beta.brand["brand_name"] == "Beta Brand"
    assert alpha.brand["pack_id"] != beta.brand["pack_id"]
    assert alpha.facts == [] and alpha.policies == []
    assert beta.facts == [] and beta.policies == []
    assert alpha.assets["approved_assets"] == []
    assert beta.assets["approved_assets"] == []
    assert store.active_root("tenant_shared", "brand_alpha") != store.active_root("tenant_shared", "brand_beta")

    alpha_draft = store.create_draft("tenant_shared", "owner-alpha", "brand_alpha", "Alpha Brand")
    alpha_brand = dict(alpha_draft["snapshot"]["brand"])
    alpha_brand["description"] = "Alpha-only approved context"
    store.update_section("tenant_shared", alpha_draft["draft_id"], "brand", alpha_brand, "owner-alpha", "brand_alpha")
    assert store.validate_draft("tenant_shared", alpha_draft["draft_id"], "brand_alpha")["valid"]
    store.publish_draft("tenant_shared", alpha_draft["draft_id"], "owner-alpha", "brand_alpha")

    assert store.active_pack("tenant_shared", "brand_alpha").brand["description"] == "Alpha-only approved context"
    assert store.active_pack("tenant_shared", "brand_beta").brand["description"] != "Alpha-only approved context"
    try:
        store.get_draft("tenant_shared", alpha_draft["draft_id"], "brand_beta")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("A draft from one brand must not be readable from another brand")


def test_legacy_tenant_pack_is_migrated_only_to_default_brand(tmp_path):
    import json
    import shutil
    from datetime import datetime, timezone
    from sigillum.modules.knowledge.store import _canonical_hash

    root = tmp_path / "packs"
    tenant_root = root / "tenant_legacy"
    seed = seed_root()
    pack_id = json.loads((seed / "brand.json").read_text(encoding="utf-8"))["pack_id"]
    legacy_pack = tenant_root / pack_id
    version_root = legacy_pack / "versions" / "v0001"
    version_root.mkdir(parents=True, exist_ok=True)
    for item in seed.iterdir():
        if item.is_dir():
            shutil.copytree(item, version_root / item.name)
        elif item.is_file():
            shutil.copy2(item, version_root / item.name)
    snapshot = {
        "brand": json.loads((version_root / "brand.json").read_text(encoding="utf-8")),
        "facts": json.loads((version_root / "facts.json").read_text(encoding="utf-8"))["facts"],
        "policies": json.loads((version_root / "policies.json").read_text(encoding="utf-8"))["policies"],
        "terminology": json.loads((version_root / "terminology.json").read_text(encoding="utf-8")),
        "voice": json.loads((version_root / "voice.json").read_text(encoding="utf-8")),
        "assets": json.loads((version_root / "asset_manifest.json").read_text(encoding="utf-8")),
    }
    fingerprint = _canonical_hash(snapshot)
    metadata = {
        "version_id": "v0001", "pack_id": pack_id, "pack_version": "1.0.0-demo",
        "fingerprint": fingerprint, "status": "PUBLISHED", "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "legacy", "base_version_id": None,
    }
    (version_root / "version.json").write_text(json.dumps(metadata), encoding="utf-8")
    (legacy_pack / "active.json").write_text(json.dumps({"version_id": "v0001", "fingerprint": fingerprint}), encoding="utf-8")

    store = KnowledgePackStore(seed, root)
    migrated = store.active_pack("tenant_legacy", "brand_orbita_demo", "ORBITA")
    assert migrated.brand["brand_id"] == "brand_orbita_demo"
    assert len(migrated.facts) == 5
    assert store.active_metadata("tenant_legacy", "brand_orbita_demo")["fingerprint"] == fingerprint
    other = store.active_pack("tenant_legacy", "brand_second", "Second Brand")
    assert other.facts == []


def test_approved_fact_must_reference_the_exact_approved_source_version(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_version", "owner-1")
    snapshot = draft["snapshot"]
    fact = snapshot["facts"][0]
    fact["approved_by"] = "owner-1"
    fact["approved_at"] = "2026-11-09T00:00:00+05:30"
    source_id = fact["source_ref"]["source_id"]
    source = next(item for item in snapshot["sources"]["sources"] if item["source_id"] == source_id)
    source["version"] = int(fact["source_ref"]["source_version"]) + 1

    errors = store._validate(snapshot, require_identity=True)
    assert any(item["code"] == "FACT_SOURCE_VERSION_MISMATCH" for item in errors)


def test_approved_fact_quote_must_be_found_in_approved_source_text(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_quote", "owner-1")
    snapshot = draft["snapshot"]
    fact = snapshot["facts"][0]
    fact["approved_by"] = "owner-1"
    fact["approved_at"] = "2026-11-09T00:00:00+05:30"
    fact["source_ref"]["quote"] = "A different excerpt that is not in the source."

    errors = store._validate(snapshot, require_identity=True)
    assert any(item["code"] == "FACT_SOURCE_QUOTE_NOT_FOUND" for item in errors)


def test_source_reference_text_must_match_its_recorded_hash(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_hash", "owner-1")
    snapshot = draft["snapshot"]
    snapshot["sources"]["sources"][0]["reference_text"] = "Tampered source excerpt."

    errors = store._validate(snapshot, require_identity=True)
    assert any(item["code"] == "SOURCE_HASH_MISMATCH" for item in errors)


def test_uploaded_asset_storage_key_cannot_cross_tenant_or_brand_namespace(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_asset_scope", "owner-1", "brand_alpha", "Alpha")
    assets = dict(draft["snapshot"]["assets"])
    assets["approved_assets"] = [{
        "asset_id": "ASSET-OTHER-BRAND",
        "name": "Foreign asset reference",
        "kind": "logo",
        "status": "approved",
        "approved_by": "owner-1",
        "approved_at": "2026-11-09T00:00:00+05:30",
        "sha256": "0" * 64,
        "storage_key": "brand-assets/tenant_other/brand_beta/draft/asset.png",
    }]
    store.update_section("tenant_asset_scope", draft["draft_id"], "assets", assets, "owner-1", "brand_alpha")

    validation = store.validate_draft("tenant_asset_scope", draft["draft_id"], "brand_alpha")
    assert validation["valid"] is False
    assert any(item["code"] == "ASSET_SCOPE_INVALID" for item in validation["errors"])
