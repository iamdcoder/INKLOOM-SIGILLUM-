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
