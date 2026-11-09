from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageDraw
from docx import Document

from sigillum.modules.content.extraction import (
    extract,
    perceptual_hash_distance,
    perceptual_hash_from_bytes,
    render_pdf_page_png,
)


def _pdf_bytes(text: str, rotation: int = 0) -> bytes:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 110), text, fontsize=22)
    if rotation:
        page.set_rotation(rotation)
    result = document.tobytes()
    document.close()
    return result


def test_searchable_pdf_has_rotation_aware_text_polygons_and_render_preview():
    payload = _pdf_bytes("Saves up to 40% on ORBITA Air One.", rotation=90)
    result = extract("offer.pdf", payload)

    assert result.status == "COMPLETED"
    assert "Saves up to 40%" in result.text
    page_region = next(item for item in result.regions if item["kind"] == "pdf_page")
    line_region = next(item for item in result.regions if item["kind"] == "pdf_text_line")
    assert page_region["rotation_degrees"] == 90
    assert page_region["width"] == line_region["page_dimensions"]["width"]
    assert line_region["coordinate_system"] == "rendered-page-pixels-top-left-origin"
    assert len(line_region["polygon"]) == 4
    assert line_region["start"] < line_region["end"]
    assert result.text[line_region["start"] : line_region["end"]] == line_region["text"]

    png, width, height = render_pdf_page_png(payload, 1, page_region["render_scale"])
    with Image.open(BytesIO(png)) as preview:
        assert preview.format == "PNG"
        assert preview.size == (width, height)
    assert (width, height) == (page_region["width"], page_region["height"])


def test_scanned_pdf_uses_bounded_page_ocr_and_keeps_page_offsets(monkeypatch):
    from sigillum.modules.content import extraction

    source_image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(source_image)
    draw.text((100, 100), "SAVES UP TO 40 PERCENT", fill="black")
    image_buffer = BytesIO()
    source_image.save(image_buffer, format="PNG")

    document = fitz.open()
    page = document.new_page(width=600, height=400)
    page.insert_image(page.rect, stream=image_buffer.getvalue())
    payload = document.tobytes()
    document.close()

    def fake_ocr(_image, output_type=None, lang=None, config=None, timeout=None):
        assert lang == "eng"
        assert timeout == 20
        return {
            "text": ["SAVES", "UP", "TO", "40", "PERCENT"],
            "conf": ["96", "95", "96", "94", "95"],
            "left": [100, 210, 280, 360, 410],
            "top": [100, 100, 100, 100, 100],
            "width": [100, 55, 45, 30, 150],
            "height": [36, 36, 36, 36, 36],
            "page_num": [1, 1, 1, 1, 1],
            "block_num": [1, 1, 1, 1, 1],
            "par_num": [1, 1, 1, 1, 1],
            "line_num": [1, 1, 1, 1, 1],
        }

    monkeypatch.setattr(extraction.pytesseract, "image_to_data", fake_ocr)
    result = extract("scanned.pdf", payload)

    assert result.status == "COMPLETED"
    assert "SAVES UP TO 40 PERCENT" in result.text
    page_region = next(item for item in result.regions if item["kind"] == "pdf_page")
    ocr_region = next(item for item in result.regions if item["kind"] == "pdf_ocr_line")
    assert page_region["ocr_used"] is True
    assert page_region["ocr_language"] == "eng"
    assert ocr_region["page"] == 1
    assert ocr_region["coordinate_system"] == "rendered-page-pixels-top-left-origin"
    assert ocr_region["start"] < ocr_region["end"]
    assert result.text[ocr_region["start"] : ocr_region["end"]] == ocr_region["text"]
    assert len(ocr_region["polygon"]) == 4


def test_docx_regions_retain_heading_runs_table_cells_and_header_footer_offsets():
    document = Document()
    document.add_heading("Launch terms", level=1)
    paragraph = document.add_paragraph()
    paragraph.add_run("Saves up to ")
    paragraph.add_run("28%")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Product"
    table.cell(0, 1).text = "ORBITA Air One"
    document.sections[0].header.paragraphs[0].text = "Approved header statement"
    buffer = BytesIO()
    document.save(buffer)

    result = extract("terms.docx", buffer.getvalue())

    assert "Launch terms" in result.text
    assert "Saves up to 28%" in result.text
    assert "Product | ORBITA Air One" in result.text
    assert "approved header statement" in result.text.lower()
    assert any(item["kind"] == "docx_heading" for item in result.regions)
    assert any(item["kind"] == "docx_run" and item["text"] == "28%" for item in result.regions)
    assert any(item["kind"] == "docx_table_cell" and item["text"] == "ORBITA Air One" for item in result.regions)
    for region in result.regions:
        if "start" in region and "end" in region and isinstance(region.get("text"), str):
            assert result.text[region["start"] : region["end"]] == region["text"]


def test_image_metadata_reports_perceptual_hash_and_approved_palette_comparison():
    image_path = Path(__file__).parents[2] / "fixtures" / "images" / "social_supported_clean.png"
    data = image_path.read_bytes()
    result = extract(
        image_path.name,
        data,
        palette_policy={
            "palette_hex": ["#000000"],
            "palette_tolerance": 0,
            "minimum_palette_match_ratio": 0.95,
        },
    )
    metadata = next(item for item in result.regions if item["kind"] == "image_metadata")
    assert len(metadata["perceptual_hash"]) == 16
    assert metadata["perceptual_hash_algorithm"] == "dhash-64-v1"
    assert metadata["palette_comparison"]["status"] in {"PASS", "FAIL", "UNMEASURABLE"}
    assert metadata["palette_comparison"]["reason"] != "NO_APPROVED_PALETTE_POLICY"
    assert perceptual_hash_from_bytes(data) == metadata["perceptual_hash"]


def test_perceptual_hash_distance_is_bounded_and_rejects_invalid_values():
    assert perceptual_hash_distance("0000000000000000", "0000000000000001") == 1
    assert perceptual_hash_distance("0000000000000000", "ffffffffffffffff") == 64
    assert perceptual_hash_distance("not-a-hash", "0000000000000000") is None


def test_visual_similarity_and_palette_issues_are_review_candidates_only():
    from types import SimpleNamespace

    from sigillum.application.services.review_service import ReviewService

    service = ReviewService.__new__(ReviewService)
    service.pack = SimpleNamespace(
        assets={
            "approved_assets": [{
                "asset_id": "ASSET-ORIGINAL",
                "name": "Approved campaign mark",
                "kind": "campaign_image",
                "status": "approved",
                "sha256": "a" * 64,
                "perceptual_hash": "0000000000000000",
            }]
        }
    )
    metadata = {
        "kind": "image_metadata",
        "perceptual_hash": "0000000000000001",
        "palette_comparison": {
            "status": "FAIL",
            "reason": "APPROVED_PALETTE_TOLERANCE_MEASURED",
            "score": 0.2,
            "threshold": 0.8,
            "tolerance_rgb_distance": 20,
            "allowed_palette": ["#000000"],
        },
    }
    version = SimpleNamespace(
        mime_type="image/png", regions=[metadata], sha256="b" * 64,
        extraction_confidence=0.92,
    )
    submission = SimpleNamespace(intended_use="campaign", channel="social")

    findings = service._image_visual_findings(submission, version)
    assert {item["code"] for item in findings} == {
        "VISUAL_PALETTE_REVIEW", "VISUAL_ASSET_SIMILARITY_CANDIDATE"
    }
    assert all(item["verdict"] == "NEEDS_MANUAL_REVIEW" for item in findings)
    assert all(item["evidence_sufficiency"] == "INSUFFICIENT" for item in findings)


def test_finding_source_mapping_prefers_docx_run_and_table_cell_regions():
    from sigillum.modules.verification.engine import VerificationEngine

    paragraph = {"kind": "docx_paragraph", "start": 0, "end": 22, "text": "Saves up to 28% today"}
    run = {"kind": "docx_run", "start": 13, "end": 16, "text": "28%"}
    row = {"kind": "docx_table_row", "start": 23, "end": 44, "text": "Product | ORBITA Air One"}
    cell = {"kind": "docx_table_cell", "start": 33, "end": 44, "text": "ORBITA Air One"}

    assert VerificationEngine._region_for(13, 16, [paragraph, run]) is run
    assert VerificationEngine._region_for(33, 44, [row, cell]) is cell
    assert VerificationEngine._region_for(2, 7, [paragraph, run]) is paragraph


def test_scanned_pdf_page_limit_stays_partial_and_never_calls_ocr(monkeypatch):
    from types import SimpleNamespace

    from sigillum.modules.content import extraction

    source_image = Image.new("RGB", (300, 200), "white")
    image_buffer = BytesIO()
    source_image.save(image_buffer, format="PNG")
    document = fitz.open()
    page = document.new_page(width=300, height=200)
    page.insert_image(page.rect, stream=image_buffer.getvalue())
    payload = document.tobytes()
    document.close()

    monkeypatch.setattr(
        extraction,
        "get_settings",
        lambda: SimpleNamespace(
            pdf_ocr_max_pages=0,
            pdf_render_dpi=96,
            pdf_render_max_dimension=1200,
            ocr_timeout_seconds=20,
            tesseract_cmd="tesseract",
            tesseract_lang="eng",
        ),
    )

    def forbidden_ocr(*_args, **_kwargs):
        raise AssertionError("OCR must not run when PDF_OCR_MAX_PAGES=0")

    monkeypatch.setattr(extraction.pytesseract, "image_to_data", forbidden_ocr)
    result = extract("page-limited.pdf", payload)

    assert result.status == "PARTIAL"
    assert any("PDF_OCR_PAGE_LIMIT" in warning for warning in result.warnings)
    page_region = next(region for region in result.regions if region["kind"] == "pdf_page")
    assert page_region["ocr_used"] is False
