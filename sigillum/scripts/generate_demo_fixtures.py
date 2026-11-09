from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docx import Document
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "fixtures" / "documents"
IMAGES = ROOT / "fixtures" / "images"
ASSETS = ROOT / "fixtures" / "brand_pack" / "v1" / "assets"

for directory in (DOCS, IMAGES, ASSETS):
    directory.mkdir(parents=True, exist_ok=True)

UNSUPPORTED = (
    "ORBITA Air One launch offer\n\n"
    "Saves up to 40% on ORBITA Air One.\n"
    "Explore the new ORBITA Air One today.\n\n"
    "Offer applies to eligible ORBITA Air One direct-web orders in India. "
    "Offer ends 30 November 2026. Terms apply.\n"
)
SUPPORTED = (
    "ORBITA Air One launch offer\n\n"
    "Save up to 28% on eligible ORBITA Air One orders.\n"
    "Explore the new ORBITA Air One today.\n\n"
    "Offer applies to eligible ORBITA Air One direct-web orders in India. "
    "Offer ends 30 November 2026. Terms apply.\n"
)

(DOCS / "claim_40_percent.txt").write_text(UNSUPPORTED, encoding="utf-8")
(DOCS / "claim_28_percent.txt").write_text(SUPPORTED, encoding="utf-8")
(DOCS / "expired_20_percent.txt").write_text(
    "Previous ORBITA Air One offer\n\nSave up to 20% on ORBITA Air One.\n"
    "This offer ended 30 September 2026.\n", encoding="utf-8"
)
(DOCS / "future_25_percent.txt").write_text(
    "Upcoming ORBITA Air One offer\n\nSave up to 25% on ORBITA Air One.\n"
    "This offer starts 1 December 2026.\n", encoding="utf-8"
)
(DOCS / "conflicting_29_percent.txt").write_text(
    "Conflict evaluation case\n\nSave up to 29% on ORBITA Air One under the isolated conflict-test offer.\n", encoding="utf-8"
)
(DOCS / "absent_evidence_72_hours.txt").write_text(
    "ORBITA Air One runs continuously for 72 hours.\n", encoding="utf-8"
)
(DOCS / "terminology_variant.txt").write_text(
    "Introducing the Orbita Air for your home.\n", encoding="utf-8"
)
(DOCS / "unsupported_tone.txt").write_text(
    "The world's best air purifier with guaranteed results.\n", encoding="utf-8"
)

# DOCX version of the unsupported anchor claim.
doc = Document()
doc.add_heading("ORBITA Air One launch offer", 0)
doc.add_paragraph("Saves up to 40% on ORBITA Air One.")
doc.add_paragraph("Explore the new ORBITA Air One today.")
doc.add_paragraph("Offer applies to eligible ORBITA Air One direct-web orders in India. Offer ends 30 November 2026. Terms apply.")
doc.save(DOCS / "claim_40_percent.docx")

# PDF version of the same claim. Coordinates are deterministic and kept in manifest.
pdf_path = DOCS / "claim_40_percent.pdf"
c = canvas.Canvas(str(pdf_path), pagesize=A4)
width, height = A4
c.setFont("Helvetica-Bold", 22)
c.drawString(52, height - 80, "ORBITA Air One launch offer")
c.setFont("Helvetica-Bold", 18)
c.drawString(52, height - 130, "Saves up to 40% on ORBITA Air One.")
c.setFont("Helvetica", 12)
c.drawString(52, height - 170, "Explore the new ORBITA Air One today.")
c.setFont("Helvetica", 9)
c.drawString(52, height - 220, "Offer applies to eligible ORBITA Air One direct-web orders in India.")
c.drawString(52, height - 235, "Offer ends 30 November 2026. Terms apply.")
c.save()

# Minimal generated logos: approved asset is the only authority; no real brand assets are used.
(ASSETS / "orbita_primary_logo.svg").write_text(
    '''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="180" viewBox="0 0 640 180">\n'''
    '''  <rect width="640" height="180" rx="22" fill="#F5F7FA"/>\n'''
    '''  <circle cx="92" cy="90" r="48" fill="#12304A"/>\n'''
    '''  <path d="M92 54 L101 81 L130 81 L106 98 L115 126 L92 109 L69 126 L78 98 L54 81 L83 81 Z" fill="#61D6C8"/>\n'''
    '''  <text x="166" y="108" font-family="Arial, sans-serif" font-size="70" font-weight="700" letter-spacing="5" fill="#12304A">ORBITA</text>\n'''
    '''</svg>\n''', encoding="utf-8"
)

try:
    font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 74)
    font_sub = ImageFont.truetype("DejaVuSans.ttf", 38)
    font_offer = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
    font_fine = ImageFont.truetype("DejaVuSans.ttf", 20)
except OSError:
    font_title = ImageFont.load_default()
    font_sub = ImageFont.load_default()
    font_offer = ImageFont.load_default()
    font_fine = ImageFont.load_default()


def make_flyer(path: Path, percent: int, *, legacy_logo: bool, low_contrast: bool, blur: bool = False) -> None:
    img = Image.new("RGB", (1080, 1350), "#F2F5F7")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((48, 48, 1032, 1302), radius=42, fill="#FFFFFF", outline="#D7E0E8", width=4)
    if legacy_logo:
        # Deliberately non-approved visual variant for a matching test case.
        draw.text((100, 105), "ORBITA", font=font_title, fill="#285F74")
        draw.line((105, 205, 490, 205), fill="#E08E52", width=11)
        draw.text((100, 235), "AIR / ONE", font=font_sub, fill="#285F74")
    else:
        draw.ellipse((100, 104, 220, 224), fill="#12304A")
        draw.polygon([(160, 125), (174, 158), (210, 158), (181, 179), (192, 213), (160, 192), (128, 213), (139, 179), (110, 158), (146, 158)], fill="#61D6C8")
        draw.text((252, 116), "ORBITA", font=font_title, fill="#12304A")
        draw.text((258, 210), "AIR ONE", font=font_sub, fill="#436174")
    draw.rounded_rectangle((100, 370, 980, 850), radius=34, fill="#12304A")
    draw.text((154, 445), "THE NEW", font=font_sub, fill="#CDE8E7")
    draw.text((154, 515), "ORBITA AIR ONE", font=font_sub, fill="#FFFFFF")
    draw.text((154, 625), f"SAVE UP TO {percent}%", font=font_offer, fill="#61D6C8")
    draw.text((104, 925), "Clearer everyday air starts here.", font=font_sub, fill="#243B4A")
    fine_colour = "#AEB7BD" if low_contrast else "#344B5A"
    draw.text((104, 1120), "Eligible direct-web orders in India. Offer ends 30 November 2026.", font=font_fine, fill=fine_colour)
    draw.text((104, 1155), "Terms and conditions apply. See offer details before purchase.", font=font_fine, fill=fine_colour)
    if blur:
        img = img.resize((360, 450)).resize((1080, 1350)).filter(ImageFilter.GaussianBlur(radius=2.2))
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        img.save(path, quality=90, optimize=True)
    else:
        img.save(path, optimize=True)

make_flyer(IMAGES / "social_unsupported_claim.png", 40, legacy_logo=True, low_contrast=True)
make_flyer(IMAGES / "social_unsupported_claim.jpg", 40, legacy_logo=True, low_contrast=True)
make_flyer(IMAGES / "social_supported_clean.png", 28, legacy_logo=False, low_contrast=False)
make_flyer(IMAGES / "social_low_confidence_ocr.png", 40, legacy_logo=True, low_contrast=True, blur=True)

# Invalid PDF and an oversized upload fixture for intake validation.
(DOCS / "malformed.pdf").write_bytes(b"%PDF-1.4\nTHIS IS INTENTIONALLY NOT A VALID PDF OBJECT GRAPH\n%%EOF")
(DOCS / "oversized_upload.txt").write_text("SIGILLUM OVERSIZED FIXTURE\n" + ("synthetic-data-" * 100000), encoding="utf-8")

manifest = {
    "schema_version": "1.0.0",
    "synthetic_only": True,
    "generation_script": "scripts/generate_demo_fixtures.py",
    "cases": [
        {"file": "documents/claim_40_percent.txt", "case_id": "GOLD-001", "expected": "CONTRADICTED", "format": "TXT"},
        {"file": "documents/claim_40_percent.docx", "case_id": "GOLD-001", "expected": "CONTRADICTED", "format": "DOCX"},
        {"file": "documents/claim_40_percent.pdf", "case_id": "GOLD-001", "expected": "CONTRADICTED", "format": "PDF", "page": 1, "approx_claim_bbox_points": [52, height - 145, 400, height - 115]},
        {"file": "documents/claim_28_percent.txt", "case_id": "GOLD-002", "expected": "SUPPORTED", "format": "TXT"},
        {"file": "documents/expired_20_percent.txt", "case_id": "GOLD-003", "expected": "STALE_OR_UNVERIFIABLE", "format": "TXT"},
        {"file": "documents/future_25_percent.txt", "case_id": "GOLD-004", "expected": "UNVERIFIABLE_OR_NOT_YET_VALID", "format": "TXT"},
        {"file": "documents/conflicting_29_percent.txt", "case_id": "GOLD-005", "expected": "CONFLICTING", "format": "TXT"},
        {"file": "documents/absent_evidence_72_hours.txt", "case_id": "GOLD-006", "expected": "UNVERIFIABLE", "format": "TXT"},
        {"file": "documents/terminology_variant.txt", "case_id": "GOLD-011", "expected": "TERMINOLOGY_VARIANT", "format": "TXT"},
        {"file": "documents/unsupported_tone.txt", "case_id": "GOLD-012", "expected": "TONE_REVIEW_REQUIRED", "format": "TXT"},
        {"file": "images/social_unsupported_claim.png", "case_id": "GOLD-007", "expected": ["ASSET_NOT_APPROVED", "CONTRAST_REVIEW_REQUIRED"], "format": "PNG", "image_size": [1080, 1350]},
        {"file": "images/social_unsupported_claim.jpg", "case_id": "GOLD-007", "expected": ["ASSET_NOT_APPROVED", "CONTRAST_REVIEW_REQUIRED"], "format": "JPG", "image_size": [1080, 1350]},
        {"file": "images/social_supported_clean.png", "case_id": "GOLD-002", "expected": "SUPPORTED_CLEAN_VISUAL", "format": "PNG", "image_size": [1080, 1350]},
        {"file": "images/social_low_confidence_ocr.png", "case_id": "GOLD-008", "expected": "EXTRACTION_WARNING_AND_MANUAL_REVIEW", "format": "PNG", "image_size": [1080, 1350]},
        {"file": "documents/malformed.pdf", "case_id": "GOLD-009", "expected": "INTAKE_REJECTED", "format": "PDF"},
        {"file": "documents/oversized_upload.txt", "case_id": "GOLD-009", "expected": "INTAKE_REJECTED", "format": "TXT"}
    ]
}
for case in manifest["cases"]:
    p = ROOT / "fixtures" / case["file"]
    case["bytes"] = p.stat().st_size
    case["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
(ROOT / "fixtures" / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Generated {len(manifest['cases'])} fixture files.")
print(f"Oversized fixture bytes: {(DOCS / 'oversized_upload.txt').stat().st_size}")
