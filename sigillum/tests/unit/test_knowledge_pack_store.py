from pathlib import Path

import pytest

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


def test_generic_editor_cannot_inject_uploaded_asset_storage_provenance(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_asset_scope", "owner-1", "brand_alpha", "Alpha")
    assets = dict(draft["snapshot"]["assets"])
    assets["approved_assets"] = [{
        "asset_id": "ASSET-OTHER-BRAND",
        "name": "Foreign asset reference",
        "kind": "logo",
        "status": "draft",
        "storage_key": "brand-assets/tenant_other/brand_beta/draft/asset.png",
    }]
    with pytest.raises(ValueError, match="upload provenance"):
        store.update_section("tenant_asset_scope", draft["draft_id"], "assets", assets, "owner-1", "brand_alpha")


def test_generic_editor_cannot_change_uploaded_source_extraction_provenance(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_provenance", "owner-1")
    source = {
        "source_id": "SRC-UPLOADED-001",
        "name": "Uploaded source",
        "source_type": "policy_document",
        "version": 1,
        "status": "draft",
        "storage_key": "brand-source-documents/tenant_source_provenance/brand_orbita_demo/draft/original.docx",
        "file_sha256": "a" * 64,
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_bytes": 2048,
        "uploaded_by": "owner-1",
        "uploaded_at": "2026-11-09T00:00:00+00:00",
        "source_format": "docx",
        "original_filename": "source.docx",
        "scan_status": "CLEAN",
        "scan_engine": "clamav",
        "scan_scanned_at": "2026-11-09T00:00:00+00:00",
        "scan_signature": None,
        "extraction_key": "brand-source-extractions/tenant_source_provenance/brand_orbita_demo/draft/extraction.json",
        "extraction_status": "COMPLETED",
        "extraction_warnings": [],
        "region_count": 1,
        "reference_text": "Approved exact source wording.",
        "sha256": "b" * 64,
    }
    store.append_source("tenant_source_provenance", "brand_orbita_demo", draft["draft_id"], source, "owner-1")
    latest = store.get_draft("tenant_source_provenance", draft["draft_id"], "brand_orbita_demo")
    changed = dict(latest["snapshot"]["sources"])
    changed["sources"] = [dict(item) for item in changed["sources"]]
    changed["sources"][-1]["reference_text"] = "A forged replacement excerpt."

    with pytest.raises(ValueError, match="immutable upload provenance"):
        store.update_section("tenant_source_provenance", draft["draft_id"], "sources", changed, "owner-1", "brand_orbita_demo")


def test_version_comparison_reports_precise_brand_field_changes(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_version_compare", "owner-1")
    changed_brand = dict(draft["snapshot"]["brand"])
    changed_brand["description"] = "A new, reviewable version description."
    store.update_section("tenant_version_compare", draft["draft_id"], "brand", changed_brand, "owner-1")
    assert store.validate_draft("tenant_version_compare", draft["draft_id"])["valid"] is True
    store.publish_draft("tenant_version_compare", draft["draft_id"], "owner-1")

    comparison = store.compare_versions("tenant_version_compare", "brand_orbita_demo", "v0001", "v0002")

    assert comparison["change_count"] >= 1
    brand_change = next(item for item in comparison["changes"] if item["section"] == "brand")
    description = next(item for item in brand_change["fields"] if item["field"] == "description")
    assert description["after"] == "A new, reviewable version description."


def test_version_diff_redacts_private_object_storage_references_and_bounds_source_text():
    private_key = "brand-source-documents/tenant/brand/draft/file.docx"
    assert KnowledgePackStore._diff_value(private_key, "storage_key") == "[redacted private storage reference]"

    safe = KnowledgePackStore._diff_record({
        "source_id": "SRC-001",
        "storage_key": private_key,
        "metadata": {"extraction_key": "private/extraction.json"},
        "reference_text": "x" * 800,
    })

    assert safe["storage_key"] == "[redacted private storage reference]"
    assert safe["metadata"]["extraction_key"] == "[redacted private storage reference]"
    assert len(safe["reference_text"]) == 500
    assert private_key not in str(safe)


def test_asset_usage_policy_enforces_dimensions_and_measured_palette(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_asset_policy", "owner-1", "brand_alpha", "Alpha")
    snapshot = draft["snapshot"]
    snapshot["assets"]["approved_assets"] = [{
        "asset_id": "ASSET-POLICY-001",
        "name": "Small black logo",
        "kind": "logo",
        "status": "approved",
        "width": 80,
        "height": 24,
        "palette": [{"hex": "#000000", "ratio": 1.0}],
    }]
    snapshot["assets"]["usage_policies"] = {
        "logo": {
            "allowed_channels": ["direct_web"],
            "allowed_uses": ["brand_lockup"],
            "min_width": 300,
            "min_height": 80,
            "palette_hex": ["#FFFFFF"],
            "palette_tolerance": 5,
            "minimum_palette_match_ratio": 0.8,
            "clear_space_ratio": 0.1,
            "severity": "review_required",
        }
    }
    errors = store._validate(snapshot, require_identity=True)
    codes = {item["code"] for item in errors}
    assert "ASSET_MIN_WIDTH_NOT_MET" in codes
    assert "ASSET_MIN_HEIGHT_NOT_MET" in codes
    assert "ASSET_PALETTE_POLICY_NOT_MET" in codes


def test_palette_policy_abstains_when_approved_asset_has_no_measured_palette(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_asset_palette_missing", "owner-1", "brand_alpha", "Alpha")
    snapshot = draft["snapshot"]
    snapshot["assets"]["approved_assets"] = [{
        "asset_id": "ASSET-LEGACY-001",
        "name": "Legacy logo without extracted palette",
        "kind": "logo",
        "status": "approved",
        "width": 640,
        "height": 320,
    }]
    snapshot["assets"]["usage_policies"] = {
        "logo": {"palette_hex": ["#FFFFFF"], "palette_tolerance": 20, "minimum_palette_match_ratio": 0.8}
    }
    errors = store._validate(snapshot, require_identity=True)
    codes = {item["code"] for item in errors}
    assert "ASSET_PALETTE_UNMEASURABLE" in codes
    assert "ASSET_PALETTE_POLICY_NOT_MET" not in codes


def test_asset_usage_policy_rejects_unknown_channels_and_invalid_colours():
    store = KnowledgePackStore(seed_root(), Path("/tmp/sigillum-asset-policy-schema-test"))
    draft = store.create_draft("tenant_asset_policy_schema", "owner-1", "brand_alpha", "Alpha")
    snapshot = draft["snapshot"]
    snapshot["assets"]["usage_policies"] = {
        "logo": {
            "allowed_channels": ["not_a_brand_channel"],
            "allowed_uses": ["brand_lockup"],
            "palette_hex": ["blue"],
        }
    }
    errors = store._validate(snapshot, require_identity=True)
    codes = {item["code"] for item in errors}
    assert "ASSET_USAGE_CHANNEL_UNKNOWN" in codes
    assert "ASSET_USAGE_PALETTE_INVALID" in codes


def test_conflict_validation_detects_overlapping_wildcard_fact_scope(tmp_path):
    from copy import deepcopy
    from sigillum.modules.knowledge.brand_pack import BrandPack

    snapshot = BrandPack(root=seed_root()).snapshot()
    snapshot["facts"] = [
        {
            "fact_id": "FACT-A", "subject": "Product A", "predicate": "maximum_saving",
            "value": 10, "unit": "%", "qualifier": "up_to", "offer_id": "OFFER-A",
            "channel": "social", "source_precedence": 2, "status": "approved",
            "valid_from": "2026-01-01T00:00:00+00:00", "valid_until": "2026-12-31T00:00:00+00:00",
        },
        {
            "fact_id": "FACT-B", "subject": "Product A", "predicate": "maximum_saving",
            "value": 12, "unit": "%", "qualifier": "up_to", "offer_id": "OFFER-A",
            # An omitted channel is broad scope and therefore overlaps social.
            "source_precedence": 2, "status": "approved",
            "valid_from": "2026-02-01T00:00:00+00:00", "valid_until": "2026-11-30T00:00:00+00:00",
        },
    ]
    result = KnowledgePackStore._validate(deepcopy(snapshot), require_identity=True)
    assert any(item["code"] == "APPROVED_FACT_CONFLICT" for item in result)


def test_conflict_validation_does_not_merge_distinct_offer_scopes(tmp_path):
    from copy import deepcopy
    from sigillum.modules.knowledge.brand_pack import BrandPack

    snapshot = BrandPack(root=seed_root()).snapshot()
    first = {
        "fact_id": "FACT-A", "subject": "Product A", "predicate": "maximum_saving",
        "value": 10, "unit": "%", "qualifier": "up_to", "offer_id": "OFFER-A",
        "channel": "social", "source_precedence": 2, "status": "approved",
        "valid_from": "2026-01-01T00:00:00+00:00", "valid_until": "2026-12-31T00:00:00+00:00",
    }
    second = {**first, "fact_id": "FACT-B", "value": 12, "offer_id": "OFFER-B"}
    snapshot["facts"] = [first, second]
    result = KnowledgePackStore._validate(deepcopy(snapshot), require_identity=True)
    assert not any(item["code"] == "APPROVED_FACT_CONFLICT" for item in result)


def test_conflict_validation_checks_policy_and_voice_guidance(tmp_path):
    from copy import deepcopy
    from sigillum.modules.knowledge.brand_pack import BrandPack

    snapshot = BrandPack(root=seed_root()).snapshot()
    snapshot["policies"] = [
        {"policy_id": "POL-A", "name": "Campaign disclaimer", "category": "legal", "rule": "Show disclaimer", "severity": "blocking", "required_action": "disclose", "scope": {"channel": ["social"]}, "status": "approved"},
        {"policy_id": "POL-B", "name": "Campaign disclaimer", "category": "legal", "rule": "Show disclaimer differently", "severity": "suggestion", "required_action": "remove", "scope": {"channel": ["social", "direct_web"]}, "status": "approved"},
    ]
    snapshot["voice"] = {
        "voice_traits": ["clear"],
        "approved_examples": [{"example_id": "VOICE-A", "text": "This is the world's best product.", "labels": ["confident"], "locale": "en-IN"}],
        "disallowed_patterns": [{"pattern_id": "VOICE-P1", "pattern": "world's best", "reason": "Unapproved superlative", "severity": "review_required", "locale": "en-IN"}],
    }
    result = KnowledgePackStore._validate(deepcopy(snapshot), require_identity=True)
    codes = {item["code"] for item in result}
    assert "APPROVED_POLICY_CONFLICT" in codes
    assert "APPROVED_VOICE_EXAMPLE_CONFLICT" in codes


def test_source_replacement_supersedes_old_record_without_rewriting_history(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_versions", "owner-1")
    original = {
        "source_id": "SRC-ORIGINAL", "name": "Product specification", "source_type": "product_specification",
        "version": 1, "reference_text": "Version one evidence", "sha256": "a" * 64,
        "status": "draft", "owner_id": "owner-1",
    }
    store.append_source("tenant_source_versions", "brand_orbita_demo", draft["draft_id"], original, "owner-1")
    replacement = {
        "source_id": "SRC-REPLACEMENT", "name": "Product specification", "source_type": "product_specification",
        "version": 2, "reference_text": "Version two evidence", "sha256": "b" * 64,
        "status": "draft", "owner_id": "owner-1",
    }
    result = store.append_source_version(
        "tenant_source_versions", "brand_orbita_demo", draft["draft_id"], "SRC-ORIGINAL", replacement, "owner-1"
    )
    source_rows = result["snapshot"]["sources"]["sources"]
    previous = next(item for item in source_rows if item["source_id"] == "SRC-ORIGINAL")
    latest = next(item for item in source_rows if item["source_id"] == "SRC-REPLACEMENT")
    assert previous["status"] == "superseded"
    assert previous["superseded_by"] == "SRC-REPLACEMENT"
    assert latest["version"] == 2
    assert latest["supersedes_source_id"] == "SRC-ORIGINAL"
    assert all(item.get("source_id") != "SRC-ORIGINAL" for item in store.active_pack("tenant_source_versions").sources["sources"])


def test_unpublished_unreferenced_source_can_be_removed_from_draft(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_remove", "owner-1")
    source = {
        "source_id": "SRC-DELETE", "name": "Discarded draft source", "source_type": "reference_text",
        "version": 1, "reference_text": "Temporary text", "status": "draft", "owner_id": "owner-1",
    }
    store.append_source("tenant_source_remove", "brand_orbita_demo", draft["draft_id"], source, "owner-1")
    removed = store.remove_unpublished_source("tenant_source_remove", "brand_orbita_demo", draft["draft_id"], "SRC-DELETE", "owner-1")
    latest = store.get_draft("tenant_source_remove", draft["draft_id"], "brand_orbita_demo")
    assert removed["source_id"] == "SRC-DELETE"
    assert not any(item.get("source_id") == "SRC-DELETE" for item in latest["snapshot"]["sources"]["sources"])


def test_source_delete_is_blocked_when_fact_references_it(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_referenced", "owner-1")
    source = {
        "source_id": "SRC-REFERENCED", "name": "Evidence source", "source_type": "reference_text",
        "version": 1, "reference_text": "A quote", "status": "draft", "owner_id": "owner-1",
    }
    store.append_source("tenant_source_referenced", "brand_orbita_demo", draft["draft_id"], source, "owner-1")
    facts = list(draft["snapshot"]["facts"])
    facts.append({"fact_id": "FACT-REF", "source_ref": {"source_id": "SRC-REFERENCED"}, "status": "draft"})
    store.update_section("tenant_source_referenced", draft["draft_id"], "facts", facts, "owner-1", "brand_orbita_demo")
    with pytest.raises(ValueError, match="referenced by fact"):
        store.remove_unpublished_source("tenant_source_referenced", "brand_orbita_demo", draft["draft_id"], "SRC-REFERENCED", "owner-1")


def test_source_history_rejects_broken_successor_links(tmp_path):
    from sigillum.modules.knowledge.brand_pack import BrandPack

    snapshot = BrandPack(root=seed_root()).snapshot()
    snapshot["sources"] = {
        "schema_version": "1.0.0",
        "sources": [
            {
                "source_id": "SRC-V1", "name": "Terms", "source_type": "campaign_terms",
                "version": 1, "status": "superseded", "superseded_by": "SRC-MISSING",
            }
        ],
    }
    codes = {item["code"] for item in KnowledgePackStore._validate(snapshot, require_identity=True)}
    assert "SOURCE_LINEAGE_INCONSISTENT" in codes


def test_deleting_latest_source_version_restores_prior_owner_approved_version(tmp_path):
    store = KnowledgePackStore(seed_root(), tmp_path / "packs")
    draft = store.create_draft("tenant_source_restore", "owner-1")
    original = {
        "source_id": "SRC-RESTORE-V1", "name": "Warranty Terms", "source_type": "campaign_terms",
        "version": 1, "reference_text": "Warranty is 24 months.", "sha256": "a" * 64,
        "status": "approved", "approved_by": "owner-1", "approved_at": "2026-11-09T00:00:00+00:00",
        "owner_id": "owner-1",
    }
    store.append_source("tenant_source_restore", "brand_orbita_demo", draft["draft_id"], original, "owner-1")
    replacement = {
        "source_id": "SRC-RESTORE-V2", "name": "Warranty Terms", "source_type": "campaign_terms",
        "version": 2, "reference_text": "Warranty is 36 months.", "sha256": "b" * 64,
        "status": "draft", "owner_id": "owner-1",
    }
    store.append_source_version(
        "tenant_source_restore", "brand_orbita_demo", draft["draft_id"], "SRC-RESTORE-V1", replacement, "owner-1"
    )
    with pytest.raises(ValueError, match="successor version"):
        store.remove_unpublished_source("tenant_source_restore", "brand_orbita_demo", draft["draft_id"], "SRC-RESTORE-V1", "owner-1")

    store.remove_unpublished_source("tenant_source_restore", "brand_orbita_demo", draft["draft_id"], "SRC-RESTORE-V2", "owner-1")
    restored = store.get_draft("tenant_source_restore", draft["draft_id"], "brand_orbita_demo")
    rows = restored["snapshot"]["sources"]["sources"]
    assert len([item for item in rows if item.get("source_id") == "SRC-RESTORE-V1"]) == 1
    source = next(item for item in rows if item.get("source_id") == "SRC-RESTORE-V1")
    assert source["status"] == "approved"
    assert source["approved_by"] == "owner-1"
    assert "superseded_by" not in source
    assert "superseded_from_status" not in source


def test_policy_schema_validation_rejects_empty_rule_and_invalid_interval(tmp_path):
    from sigillum.modules.knowledge.brand_pack import BrandPack

    snapshot = BrandPack(root=seed_root()).snapshot()
    snapshot["policies"] = [{
        "policy_id": "POL-BAD", "name": "Missing rule", "rule": "", "category": "claims",
        "severity": "blocking", "required_action": "invent", "scope": {"channel": ["social", ""]},
        "valid_from": "2026-11-10T00:00:00+00:00", "valid_until": "2026-11-01T00:00:00+00:00",
        "status": "draft",
    }]
    codes = {item["code"] for item in KnowledgePackStore._validate(snapshot, require_identity=True)}
    assert {"POLICY_RULE_REQUIRED", "POLICY_ACTION_INVALID", "POLICY_SCOPE_VALUE_INVALID", "POLICY_VALIDITY_INTERVAL_INVALID"} <= codes


def test_terminology_conflicts_respect_locale_and_scope_and_validate_links(tmp_path):
    from sigillum.modules.knowledge.brand_pack import BrandPack

    snapshot = BrandPack(root=seed_root()).snapshot()
    snapshot["terminology"] = {
        "schema_version": "1.0.0",
        "preferred_terms": [
            {"term_id": "TERM-A", "preferred": "ORBITA Air One", "locale": "en-IN", "scope": ["OFFER-A"], "status": "approved"},
        ],
        "prohibited_or_review_terms": [
            {"term_id": "TERM-B", "variant": "ORBITA Air One", "preferred_term_id": "MISSING", "locale": "en-IN", "scope": ["OFFER-B"], "reason": "test", "severity": "review_required", "status": "approved"},
        ],
    }
    codes = {item["code"] for item in KnowledgePackStore._validate(snapshot, require_identity=True)}
    assert "TERMINOLOGY_PREFERRED_REFERENCE_MISSING" in codes
    assert "APPROVED_TERMINOLOGY_CONFLICT" not in codes

    snapshot["terminology"]["prohibited_or_review_terms"][0]["scope"] = ["OFFER-A"]
    codes = {item["code"] for item in KnowledgePackStore._validate(snapshot, require_identity=True)}
    assert "APPROVED_TERMINOLOGY_CONFLICT" in codes
