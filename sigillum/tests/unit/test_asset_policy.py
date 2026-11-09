from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from sigillum.modules.knowledge.asset_policy import (
    asset_policy_violations,
    extract_palette,
    palette_match_ratio,
    validate_usage_policies,
)


def _image_bytes(color: tuple[int, int, int] = (12, 34, 56)) -> bytes:
    image = Image.new("RGB", (32, 24), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_extract_palette_returns_weighted_hex_colours():
    palette = extract_palette(_image_bytes())
    assert palette
    assert palette[0]["hex"] == "#0C2238"
    assert palette[0]["ratio"] == 1.0


def test_palette_match_ratio_measures_weighted_coverage():
    observed = [
        {"hex": "#000000", "ratio": 0.75},
        {"hex": "#FFFFFF", "ratio": 0.25},
    ]
    assert palette_match_ratio(observed, ["#000000"], 1) == 0.75


def test_usage_policy_validation_checks_channel_use_and_temporal_schema():
    errors = validate_usage_policies(
        {
            "logo": {
                "allowed_channels": ["missing_channel"],
                "allowed_uses": ["unsupported_use"],
                "valid_from": "2026-11-09T12:00:00",
            }
        },
        ["direct_web", "social"],
    )
    codes = {item["code"] for item in errors}
    assert "ASSET_USAGE_CHANNEL_UNKNOWN" in codes
    assert "ASSET_USAGE_USES_INVALID" in codes
    assert "ASSET_USAGE_VALIDITY_INVALID" in codes


def test_asset_policy_detects_channel_use_and_validity_violations():
    policy = {
        "allowed_channels": ["direct_web"],
        "allowed_uses": ["brand_lockup"],
        "valid_from": "2026-11-10T00:00:00+00:00",
        "valid_until": None,
    }
    asset = {"kind": "logo", "valid_from": None, "valid_until": None}
    violations = asset_policy_violations(
        asset,
        policy,
        "social",
        "social_ad",
        datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
    )
    assert {item["code"] for item in violations} == {
        "ASSET_CHANNEL_NOT_ALLOWED",
        "ASSET_USE_NOT_ALLOWED",
        "ASSET_POLICY_OUTSIDE_VALIDITY",
    }


def test_review_service_applies_usage_rules_only_to_exact_approved_asset_hash():
    from sigillum.application.services.review_service import ReviewService
    from sigillum.modules.knowledge.brand_pack import BrandPack
    from tests.unit.test_verification_engine import PACK

    digest = "a" * 64
    snapshot = PACK.snapshot()
    snapshot["assets"] = {
        "schema_version": "1.1.0",
        "approved_assets": [{
            "asset_id": "ASSET-EXACT-001",
            "name": "Approved exact-match logo",
            "kind": "logo",
            "status": "approved",
            "sha256": digest,
        }],
        "usage_policies": {
            "logo": {
                "allowed_channels": ["direct_web"],
                "allowed_uses": ["brand_lockup"],
                "severity": "blocking",
                "clear_space_ratio": 0.1,
            }
        },
    }
    service = ReviewService(db=None, pack=BrandPack.from_snapshot(snapshot), storage_root=".")
    submission = SimpleNamespace(
        channel="social",
        intended_use="social_ad",
        publication_at="2026-11-11T12:00:00+00:00",
    )
    exact_version = SimpleNamespace(mime_type="image/png", sha256=digest, extraction_confidence=1.0)
    findings = service._exact_asset_usage_findings(submission, exact_version)
    codes = {item["code"] for item in findings}
    assert "BRAND_ASSET_ASSET_CHANNEL_NOT_ALLOWED" in codes
    assert "BRAND_ASSET_ASSET_USE_NOT_ALLOWED" in codes
    assert "BRAND_ASSET_CLEAR_SPACE_MANUAL_REVIEW" in codes
    assert all(item["evidence"][0]["asset_id"] == "ASSET-EXACT-001" for item in findings)

    unrelated_version = SimpleNamespace(mime_type="image/png", sha256="b" * 64, extraction_confidence=1.0)
    assert service._exact_asset_usage_findings(submission, unrelated_version) == []
