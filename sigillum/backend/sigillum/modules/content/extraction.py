"""Safe, bounded extraction adapters with source-mapped logical and visual regions."""
from __future__ import annotations

import hashlib
import math
import statistics
import warnings
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PureWindowsPath
from typing import Any
from zipfile import BadZipFile, ZipFile

import pytesseract
from docx import Document
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pytesseract import Output

from sigillum.config import get_settings

ALLOWED = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
MAX_DOCX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_DOCX_MEMBERS = 2_000
MAX_IMAGE_PIXELS = 40_000_000
MAX_PDF_PAGES = 250


@dataclass
class ExtractionResult:
    text: str
    confidence: float = 1.0
    status: str = "COMPLETED"
    warnings: list[str] = field(default_factory=list)
    regions: list[dict[str, Any]] = field(default_factory=list)


def _validate_docx_archive(data: bytes) -> None:
    """Validate DOCX as a bounded OOXML package before handing it to python-docx."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_MEMBERS:
                raise ValueError("DOCX_MEMBER_LIMIT_EXCEEDED")
            expanded_size = sum(item.file_size for item in entries)
            if expanded_size > MAX_DOCX_EXPANDED_BYTES:
                raise ValueError("DOCX_EXPANDED_SIZE_LIMIT_EXCEEDED")
            names = {item.filename for item in entries}
            if "word/document.xml" not in names:
                raise ValueError("INVALID_DOCX_PACKAGE")
            if any(
                name.startswith(("/", "\\"))
                or "\\" in name
                or ":" in name.split("/", 1)[0]
                or ".." in Path(name).parts
                or ".." in PureWindowsPath(name).parts
                for name in names
            ):
                raise ValueError("INVALID_DOCX_PACKAGE_PATH")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise ValueError("DOCX_MACRO_CONTENT_NOT_SUPPORTED")
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ValueError("DOCX_ARCHIVE_CRC_FAILURE")
            # Relationships may contain external hyperlinks. The extraction pipeline
            # reads package XML only and never resolves/fetches those targets.
    except BadZipFile as exc:
        raise ValueError("INVALID_DOCX_PACKAGE") from exc


def safe_upload_filename(filename: str) -> str:
    """Return a bounded display filename without path components or control chars."""
    normalized = str(filename or "upload").replace("\\", "/")
    name = PureWindowsPath(normalized).name
    name = "".join(char for char in name if ord(char) >= 32 and ord(char) != 127)
    name = name.strip().strip(".")
    return (name or "upload")[:255]


def sniff_file(filename: str, data: bytes) -> str:
    # Treat Windows browser paths and POSIX paths consistently. The name is only
    # used to choose an allowed parser; media type is always derived from bytes.
    safe_name = safe_upload_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("UNSUPPORTED_FILE: allowed formats are PDF, DOCX, TXT, PNG and JPG")
    if not data:
        raise ValueError("EMPTY_FILE")

    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("INVALID_FILE_SIGNATURE: file contents do not match the declared format")
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError("PASSWORD_PROTECTED_PDF")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError("PDF_PAGE_LIMIT_EXCEEDED")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("INVALID_PDF_CONTAINER") from exc
        return "application/pdf"

    if extension == ".docx":
        if not data.startswith(b"PK"):
            raise ValueError("INVALID_FILE_SIGNATURE: file contents do not match the declared format")
        _validate_docx_archive(data)
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if extension == ".txt":
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("INVALID_TEXT_ENCODING: TXT uploads must be valid UTF-8") from exc
        return "text/plain"

    expected_signature = b"\x89PNG\r\n\x1a\n" if extension == ".png" else b"\xff\xd8\xff"
    if not data.startswith(expected_signature):
        raise ValueError("INVALID_FILE_SIGNATURE: file contents do not match the declared format")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data))
            if image.format not in ({"PNG"} if extension == ".png" else {"JPEG"}):
                raise ValueError("IMAGE_FORMAT_MISMATCH")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("IMAGE_PIXEL_LIMIT_EXCEEDED")
            image.verify()
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("INVALID_OR_UNSAFE_IMAGE") from exc
    return "image/png" if extension == ".png" else "image/jpeg"


def _rgb_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _median_rgb(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    return tuple(int(statistics.median(channel)) for channel in zip(*samples))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        channel = value / 255.0
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    light, dark = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _dominant_palette(image: Image.Image, limit: int = 6) -> list[dict[str, Any]]:
    """Return a descriptive palette inventory; it is not a compliance verdict."""
    sample = image if image.mode == "RGB" else image.convert("RGB")
    sample = sample.copy()
    sample.thumbnail((512, 512), Image.Resampling.BOX)
    quantized = sample.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    counts = quantized.getcolors(maxcolors=256 * 256) or []
    palette = quantized.getpalette() or []
    total = max(1, sum(count for count, _ in counts))
    result: list[dict[str, Any]] = []
    for count, index in sorted(counts, reverse=True)[:limit]:
        offset = index * 3
        if offset + 2 >= len(palette):
            continue
        color = (palette[offset], palette[offset + 1], palette[offset + 2])
        result.append({"hex": _rgb_hex(color), "coverage": round(count / total, 4)})
    return result


def measure_region_contrast(
    image: Image.Image,
    bbox: dict[str, int],
    threshold: float | None,
    ocr_confidence: float,
) -> dict[str, Any]:
    """Conservatively estimate local text/background contrast for one OCR line.

    A result is UNMEASURABLE unless a stable local background and a distinct text
    pixel cluster can be sampled. PASS/FAIL are measurements for this region only,
    not a statement of WCAG conformance for the complete asset.
    """
    if threshold is None or threshold <= 1:
        return {"status": "UNMEASURABLE", "reason": "NO_APPROVED_THRESHOLD", "threshold": None}
    if ocr_confidence < 0.70:
        return {
            "status": "UNMEASURABLE",
            "reason": "LOW_OCR_CONFIDENCE",
            "threshold": threshold,
            "measurement_confidence": 0.0,
        }

    width, height = image.size
    x, y = max(0, bbox["x"]), max(0, bbox["y"])
    right = min(width, x + bbox["width"])
    bottom = min(height, y + bbox["height"])
    if right <= x or bottom <= y or (right - x) * (bottom - y) < 12:
        return {"status": "UNMEASURABLE", "reason": "REGION_TOO_SMALL", "threshold": threshold}

    pad = max(3, min(12, int(max(3, bottom - y) * 0.35)))
    left_outer, top_outer = max(0, x - pad), max(0, y - pad)
    right_outer, bottom_outer = min(width, right + pad), min(height, bottom + pad)
    rgb_image = image if image.mode == "RGB" else image.convert("RGB")
    context = rgb_image.crop((left_outer, top_outer, right_outer, bottom_outer))
    # Bound per-region CPU/memory when an uploaded image contains unusually large
    # OCR boxes. Colour measurement is an estimate, so controlled downsampling is safe.
    sample_limit = 250_000
    if context.width * context.height > sample_limit:
        scale = (sample_limit / (context.width * context.height)) ** 0.5
        target = (max(1, int(context.width * scale)), max(1, int(context.height * scale)))
        context = context.resize(target, Image.Resampling.BOX)
    scale_x = context.width / max(1, right_outer - left_outer)
    scale_y = context.height / max(1, bottom_outer - top_outer)
    pixels = context.load()
    local_left = int((x - left_outer) * scale_x)
    local_top = int((y - top_outer) * scale_y)
    local_right = min(context.width, int((right - left_outer) * scale_x))
    local_bottom = min(context.height, int((bottom - top_outer) * scale_y))

    background_samples: list[tuple[int, int, int]] = []
    for py in range(context.height):
        for px in range(context.width):
            inside_text_box = local_left <= px < local_right and local_top <= py < local_bottom
            near_outer_edge = px < 2 or py < 2 or px >= context.width - 2 or py >= context.height - 2
            if not inside_text_box and near_outer_edge:
                background_samples.append(pixels[px, py])
    if len(background_samples) < 12:
        return {"status": "UNMEASURABLE", "reason": "INSUFFICIENT_BACKGROUND_SAMPLES", "threshold": threshold}

    background = _median_rgb(background_samples)
    bg_deviation = statistics.median(
        sum(abs(sample[channel] - background[channel]) for channel in range(3)) / 3
        for sample in background_samples
    )
    text_samples: list[tuple[int, int, int]] = []
    for py in range(local_top, local_bottom):
        for px in range(local_left, local_right):
            color = pixels[px, py]
            distance = sum((color[channel] - background[channel]) ** 2 for channel in range(3)) ** 0.5
            if distance >= 42:
                text_samples.append(color)

    region_area = max(1, (local_right - local_left) * (local_bottom - local_top))
    foreground_ratio = len(text_samples) / region_area
    if len(text_samples) < 8 or foreground_ratio < 0.004 or foreground_ratio > 0.80 or bg_deviation > 24:
        return {
            "status": "UNMEASURABLE",
            "reason": "UNRELIABLE_LOCAL_SEGMENTATION",
            "threshold": threshold,
            "background_color": _rgb_hex(background),
            "background_median_deviation": round(bg_deviation, 2),
            "foreground_sample_count": len(text_samples),
        }

    foreground = _median_rgb(text_samples)
    ratio = _contrast_ratio(foreground, background)
    # This confidence describes only the local colour segmentation, not truth or accessibility.
    segmentation_confidence = max(0.70, min(0.92, 0.92 - bg_deviation / 100.0))
    status = "PASS" if ratio >= threshold else "FAIL"
    return {
        "status": status,
        "reason": "MEASURED_LOCAL_CONTRAST",
        "threshold": threshold,
        "ratio": round(ratio, 2),
        "foreground_color": _rgb_hex(foreground),
        "background_color": _rgb_hex(background),
        "foreground_sample_count": len(text_samples),
        "background_sample_count": len(background_samples),
        "background_median_deviation": round(bg_deviation, 2),
        "measurement_confidence": round(segmentation_confidence, 2),
        "method": "local-border-median-and-colour-distance-v1",
        "limitation": "Local estimate for this OCR line only; inspect the original creative before making an accessibility decision.",
    }


def _polygon_from_bbox(bbox: dict[str, int]) -> list[list[int]]:
    x, y, width, height = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def _normalised_bbox(bbox: dict[str, int], width: int, height: int) -> dict[str, float]:
    return {
        "x": round(bbox["x"] / max(1, width), 6),
        "y": round(bbox["y"] / max(1, height), 6),
        "width": round(bbox["width"] / max(1, width), 6),
        "height": round(bbox["height"] / max(1, height), 6),
    }


def _ocr_line_regions(
    image: Image.Image,
    raw: dict[str, list[Any]],
    contrast_threshold: float | None,
    *,
    page_number: int = 1,
    region_prefix: str = "ocr-line",
    region_kind: str = "ocr_line",
    coordinate_system: str = "image-pixels-top-left-origin",
) -> tuple[str, list[dict[str, Any]], list[float]]:
    """Convert Tesseract word output into line regions with stable text offsets."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    keys = ("page_num", "block_num", "par_num", "line_num")
    for index, raw_token in enumerate(raw.get("text", [])):
        token = str(raw_token or "").strip()
        try:
            confidence = float(raw["conf"][index]) / 100.0
        except (KeyError, TypeError, ValueError, IndexError):
            confidence = -1.0
        if not token or confidence < 0:
            continue
        try:
            box = {
                "x": int(raw["left"][index]),
                "y": int(raw["top"][index]),
                "width": int(raw["width"][index]),
                "height": int(raw["height"][index]),
            }
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        group_key = tuple(
            str(raw.get(key, [0] * (index + 1))[index])
            if index < len(raw.get(key, [])) else "0"
            for key in keys
        )
        grouped.setdefault(group_key, []).append(
            {"text": token, "confidence": confidence, "bbox": box}
        )

    text_parts: list[str] = []
    regions: list[dict[str, Any]] = []
    confidences: list[float] = []
    cursor = 0
    for line_number, words in enumerate(grouped.values(), start=1):
        line_text = " ".join(word["text"] for word in words).strip()
        if not line_text:
            continue
        xs = [word["bbox"]["x"] for word in words]
        ys = [word["bbox"]["y"] for word in words]
        rights = [word["bbox"]["x"] + word["bbox"]["width"] for word in words]
        bottoms = [word["bbox"]["y"] + word["bbox"]["height"] for word in words]
        bbox = {
            "x": min(xs), "y": min(ys),
            "width": max(rights) - min(xs),
            "height": max(bottoms) - min(ys),
        }
        confidence = sum(word["confidence"] for word in words) / len(words)
        if text_parts:
            cursor += 1
        start = cursor
        end = start + len(line_text)
        word_boxes = []
        for word in words:
            word_bbox = word["bbox"]
            word_boxes.append({
                "text": word["text"],
                "confidence": round(word["confidence"], 3),
                "bbox": word_bbox,
                "polygon": _polygon_from_bbox(word_bbox),
            })
        regions.append({
            "region_id": f"{region_prefix}-{line_number:04d}",
            "kind": region_kind,
            "page": page_number,
            "line": line_number,
            "text": line_text,
            "start": start,
            "end": end,
            "confidence": round(confidence, 3),
            "bbox": bbox,
            "polygon": _polygon_from_bbox(bbox),
            "normalised_bbox": _normalised_bbox(bbox, image.width, image.height),
            "coordinate_system": coordinate_system,
            "page_dimensions": {
                "width": image.width, "height": image.height, "units": "pixels"
            },
            "words": word_boxes,
            "contrast": measure_region_contrast(image, bbox, contrast_threshold, confidence),
        })
        text_parts.append(line_text)
        cursor = end
        confidences.append(confidence)
    return "\n".join(text_parts), regions, confidences


def _perceptual_hash(image: Image.Image) -> str:
    """Return a 64-bit difference hash. It is a candidate signal, never identity proof."""
    grayscale = ImageOps.exif_transpose(image).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(grayscale.get_flattened_data())
    bits = []
    for row in range(8):
        offset = row * 9
        bits.extend(pixels[offset + column] > pixels[offset + column + 1] for column in range(8))
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def perceptual_hash_from_bytes(data: bytes) -> str:
    """Compute the versioned dHash used for human-confirmed asset candidates."""
    with Image.open(BytesIO(data)) as source:
        if source.width * source.height > MAX_IMAGE_PIXELS:
            raise ValueError("IMAGE_PIXEL_LIMIT_EXCEEDED")
        return _perceptual_hash(ImageOps.exif_transpose(source))


def perceptual_hash_distance(first: str, second: str) -> int | None:
    """Hamming distance for compatible 64-bit difference hashes."""
    try:
        if len(first) != 16 or len(second) != 16:
            return None
        return (int(first, 16) ^ int(second, 16)).bit_count()
    except (TypeError, ValueError):
        return None


def _pdf_render_scale(page: Any) -> float:
    settings = get_settings()
    dpi = max(72, min(200, int(getattr(settings, "pdf_render_dpi", 144))))
    max_dimension = max(600, min(4000, int(getattr(settings, "pdf_render_max_dimension", 2400))))
    page_rect = page.rect
    return min(dpi / 72.0, max_dimension / max(1.0, page_rect.width, page_rect.height))


def _pdf_polygon(rect_values: tuple[float, float, float, float], page: Any, scale: float) -> tuple[dict[str, float], list[list[float]]]:
    """Map PyMuPDF's unrotated point coordinates to displayed rendered pixels."""
    import fitz

    rect = fitz.Rect(*rect_values) * page.rotation_matrix
    bbox = {
        "x": round(rect.x0 * scale, 2),
        "y": round(rect.y0 * scale, 2),
        "width": round(rect.width * scale, 2),
        "height": round(rect.height * scale, 2),
    }
    polygon = [
        [round(point.x * scale, 2), round(point.y * scale, 2)]
        for point in (rect.tl, rect.tr, rect.br, rect.bl)
    ]
    return bbox, polygon


def _pdf_page_lines(page: Any, page_number: int, scale: float, base_offset: int) -> tuple[str, list[dict[str, Any]]]:
    """Extract page lines in reading order and bind them to rendered-page polygons."""
    page_dict = page.get_text("dict", sort=True)
    page_lines: list[str] = []
    regions: list[dict[str, Any]] = []
    cursor = base_offset
    line_number = 0
    for block_number, block in enumerate(page_dict.get("blocks", []), start=1):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(str(span.get("text", "")) for span in spans)
            if not line_text.strip():
                continue
            if page_lines:
                cursor += 1
            start = cursor
            end = start + len(line_text)
            raw_bbox = tuple(float(value) for value in line.get("bbox", (0, 0, 0, 0)))
            bbox, polygon = _pdf_polygon(raw_bbox, page, scale)
            line_number += 1
            regions.append({
                "region_id": f"pdf-p{page_number:04d}-b{block_number:03d}-l{line_number:04d}",
                "kind": "pdf_text_line",
                "page": page_number,
                "block": block_number,
                "line": line_number,
                "start": start,
                "end": end,
                "text": line_text,
                "bbox": bbox,
                "polygon": polygon,
                "normalised_bbox": _normalised_bbox(
                    {key: int(round(value)) for key, value in bbox.items()},
                    max(1, int(math.ceil(page.rect.width * scale))),
                    max(1, int(math.ceil(page.rect.height * scale))),
                ),
                "pdf_bbox_points_unrotated": [round(value, 3) for value in raw_bbox],
                "rotation_degrees": int(page.rotation or 0),
                "coordinate_system": "rendered-page-pixels-top-left-origin",
                "page_dimensions": {
                    "width": max(1, int(round(page.rect.width * scale))),
                    "height": max(1, int(round(page.rect.height * scale))),
                    "units": "pixels",
                },
                "confidence": 1.0,
                "method": "pymupdf-text-layout-v1",
            })
            page_lines.append(line_text)
            cursor = end
    return "\n".join(page_lines), regions


def _extract_pdf(data: bytes, contrast_threshold: float | None) -> ExtractionResult:
    """Parse searchable PDF text and OCR scanned pages with rotation-aware geometry."""
    import fitz

    settings = get_settings()
    max_ocr_pages = max(0, min(50, int(getattr(settings, "pdf_ocr_max_pages", 20))))
    ocr_timeout = max(1, min(120, int(getattr(settings, "ocr_timeout_seconds", 20))))
    try:
        document = fitz.open(stream=data, filetype="pdf")
        if document.needs_pass:
            raise ValueError("PASSWORD_PROTECTED_PDF")
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError("PDF_PAGE_LIMIT_EXCEEDED")
        if document.page_count < 1:
            raise ValueError("INVALID_PDF_CONTAINER")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("INVALID_PDF_CONTAINER") from exc

    all_pages: list[str] = []
    regions: list[dict[str, Any]] = []
    warnings_list: list[str] = []
    page_confidences: list[tuple[int, float]] = []
    scanned_pages: list[int] = []
    ocr_attempted = 0
    ocr_failed_pages: list[int] = []

    try:
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            scale = _pdf_render_scale(page)
            page_rect = page.rect
            rendered_width = max(1, int(math.ceil(page_rect.width * scale)))
            rendered_height = max(1, int(math.ceil(page_rect.height * scale)))
            page_text, page_regions = _pdf_page_lines(page, page_number, scale, 0)
            compact_length = len("".join(page_text.split()))
            needs_ocr = compact_length < 20
            page_confidence = 1.0
            if needs_ocr:
                scanned_pages.append(page_number)
                if ocr_attempted < max_ocr_pages:
                    ocr_attempted += 1
                    try:
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=True)
                        rendered_width, rendered_height = pixmap.width, pixmap.height
                        page_image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
                        raw = pytesseract.image_to_data(
                            page_image,
                            output_type=Output.DICT,
                            lang=settings.tesseract_lang,
                            config="--psm 6",
                            timeout=ocr_timeout,
                        )
                        ocr_text, ocr_regions, confidences = _ocr_line_regions(
                            page_image,
                            raw,
                            contrast_threshold,
                            page_number=page_number,
                            region_prefix=f"pdf-p{page_number:04d}-ocr",
                            region_kind="pdf_ocr_line",
                            coordinate_system="rendered-page-pixels-top-left-origin",
                        )
                        if ocr_text.strip():
                            page_text = ocr_text
                            page_regions = ocr_regions
                            page_confidence = sum(confidences) / len(confidences) if confidences else 0.0
                            if page_confidence < 0.75:
                                warnings_list.append(
                                    f"PDF_LOW_OCR_CONFIDENCE: page {page_number} OCR confidence is below 75%; inspect the rendered page manually."
                                )
                        else:
                            ocr_failed_pages.append(page_number)
                            warnings_list.append(
                                f"PDF_OCR_EMPTY: no readable text was extracted from scanned page {page_number}."
                            )
                    except Exception as exc:
                        ocr_failed_pages.append(page_number)
                        warnings_list.append(
                            f"PDF_OCR_UNAVAILABLE: page {page_number} OCR failed ({type(exc).__name__}); manual review is required."
                        )
                else:
                    ocr_failed_pages.append(page_number)
                    warnings_list.append(
                        f"PDF_OCR_PAGE_LIMIT: page {page_number} was not OCR-processed because the per-file OCR page limit was reached."
                    )

            # Rebase all logical spans into the combined, immutable version text.
            if all_pages:
                base_offset = sum(len(item) for item in all_pages) + len(all_pages)
            else:
                base_offset = 0
            for region in page_regions:
                region["start"] = int(region.get("start", 0)) + base_offset
                region["end"] = int(region.get("end", 0)) + base_offset
            regions.append({
                "region_id": f"pdf-page-{page_number:04d}",
                "kind": "pdf_page",
                "page": page_number,
                "source_width_points": round(float(page.mediabox.width), 3),
                "source_height_points": round(float(page.mediabox.height), 3),
                "width": rendered_width,
                "height": rendered_height,
                "rotation_degrees": int(page.rotation or 0),
                "render_scale": round(scale, 6),
                "render_dpi": round(scale * 72, 2),
                "coordinate_system": "rendered-page-pixels-top-left-origin",
                "page_dimensions": {"width": rendered_width, "height": rendered_height, "units": "pixels"},
                "ocr_used": needs_ocr and page_number not in ocr_failed_pages,
                "ocr_engine": "Tesseract" if needs_ocr else None,
                "ocr_engine_version": (
                    str(pytesseract.get_tesseract_version())
                    if needs_ocr and page_number not in ocr_failed_pages
                    else None
                ),
                "ocr_language": settings.tesseract_lang if needs_ocr else None,
                "preprocessing": ["PyMuPDF page rasterisation", "RGB conversion"] if needs_ocr else [],
            })
            regions.extend(page_regions)
            all_pages.append(page_text)
            page_confidences.append((max(1, len(page_text)), page_confidence))

            # Table extraction is best-effort metadata; its text is not appended a
            # second time to the canonical text, avoiding duplicate claim extraction.
            if hasattr(page, "find_tables"):
                try:
                    table_finder = page.find_tables()
                    for table_index, table in enumerate(table_finder.tables, start=1):
                        table_rows = table.extract() or []
                        table_rect = tuple(float(value) for value in table.bbox)
                        table_bbox, table_polygon = _pdf_polygon(table_rect, page, scale)
                        regions.append({
                            "region_id": f"pdf-p{page_number:04d}-table-{table_index:03d}",
                            "kind": "pdf_table",
                            "page": page_number,
                            "row_count": len(table_rows),
                            "column_count": max((len(row) for row in table_rows), default=0),
                            "table_text": table_rows[:100],
                            "bbox": table_bbox,
                            "polygon": table_polygon,
                            "coordinate_system": "rendered-page-pixels-top-left-origin",
                            "limitation": "Table cells are layout metadata; canonical text offsets are provided by the page line regions.",
                        })
                except Exception:
                    warnings_list.append(
                        f"PDF_TABLE_LAYOUT_UNAVAILABLE: table structure could not be extracted on page {page_number}; searchable page text remains available."
                    )

    finally:
        document.close()

    text = "\n".join(all_pages)
    if scanned_pages:
        warnings_list.append(
            "PDF_SCANNED_PAGES_DETECTED: " + ", ".join(map(str, scanned_pages)) + ". OCR is bounded and low-confidence text requires human inspection."
        )
    warnings_list.extend([
        "PDF_EMBEDDED_VISUALS_LIMITATION: OCR is applied to scanned pages; independently placed images/logos within otherwise searchable pages may require manual visual review.",
        "PDF_COORDINATES: text and OCR polygons use rendered-page pixels with top-left origin; the source PDF page size and rotation are retained.",
    ])
    confidence = (
        sum(weight * value for weight, value in page_confidences) / sum(weight for weight, _ in page_confidences)
        if page_confidences else 0.0
    )
    status = "PARTIAL" if ocr_failed_pages or confidence < 0.75 or not text.strip() else "COMPLETED"
    if not text.strip():
        warnings_list.append("PDF_TEXT_EMPTY: no searchable or OCR text was available; inspect the original PDF manually.")
    return ExtractionResult(text, confidence, status, list(dict.fromkeys(warnings_list)), regions)


def render_pdf_page_png(data: bytes, page_number: int, scale: float | None = None) -> tuple[bytes, int, int]:
    """Render one PDF page using the same bounded scale recorded during extraction."""
    import fitz

    try:
        document = fitz.open(stream=data, filetype="pdf")
        if document.needs_pass or page_number < 1 or page_number > document.page_count:
            raise ValueError("PDF_PAGE_UNAVAILABLE")
        page = document.load_page(page_number - 1)
        selected_scale = float(scale) if scale is not None else _pdf_render_scale(page)
        selected_scale = max(0.5, min(3.0, selected_scale))
        pixmap = page.get_pixmap(matrix=fitz.Matrix(selected_scale, selected_scale), alpha=False, annots=True)
        return pixmap.tobytes("png"), pixmap.width, pixmap.height
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF_PAGE_RENDER_FAILED") from exc
    finally:
        try:
            document.close()
        except (UnboundLocalError, Exception):
            pass


def extract(filename: str, data: bytes, contrast_threshold: float | None = None, palette_policy: dict[str, Any] | None = None) -> ExtractionResult:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("UNSUPPORTED_FILE")
    if not data:
        raise ValueError("EMPTY_FILE")

    if extension == ".txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return ExtractionResult(
                "", 0.0, "PARTIAL",
                ["TXT_ENCODING_UNREADABLE: UTF-8 decoding failed; manual inspection required."], [],
            )
        regions: list[dict[str, Any]] = []
        cursor = 0
        for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
            content = line.rstrip("\r\n")
            end = cursor + len(content)
            if content.strip():
                regions.append({
                    "region_id": f"txt-line-{line_number:04d}",
                    "kind": "txt_line",
                    "line": line_number,
                    "start": cursor,
                    "end": end,
                    "text": content,
                    "coordinate_system": "unicode-character-offsets",
                    "coordinates_available": False,
                })
            cursor += len(line)
        if not text.strip():
            return ExtractionResult(
                text, 0.0, "PARTIAL", ["CONTENT_EMPTY: no readable text was found."], regions
            )
        return ExtractionResult(text, regions=regions)

    if extension == ".docx":
        _validate_docx_archive(data)
        document = Document(BytesIO(data))
        blocks: list[str] = []
        regions: list[dict[str, Any]] = []
        cursor = 0

        def append_block(block_text: str) -> int:
            nonlocal cursor
            if blocks:
                cursor += 1
            start = cursor
            blocks.append(block_text)
            cursor += len(block_text)
            return start

        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph as DocxParagraph

        paragraph_counter = 0
        table_counter = 0
        for child in document.element.body.iterchildren():
            if child.tag.endswith("}p"):
                paragraph_counter += 1
                paragraph = DocxParagraph(child, document)
                paragraph_text = paragraph.text
                if not paragraph_text.strip():
                    continue
                start = append_block(paragraph_text)
                style_name = paragraph.style.name if paragraph.style else None
                kind = "docx_heading" if style_name and style_name.lower().startswith("heading") else "docx_paragraph"
                regions.append({
                    "region_id": f"docx-paragraph-{paragraph_counter:04d}",
                    "kind": kind,
                    "paragraph": paragraph_counter,
                    "style": style_name,
                    "start": start,
                    "end": start + len(paragraph_text),
                    "text": paragraph_text,
                    "coordinate_system": "unicode-character-offsets",
                    "coordinates_available": False,
                })
                run_cursor = 0
                for run_index, run in enumerate(paragraph.runs, start=1):
                    run_text = run.text or ""
                    if not run_text:
                        continue
                    run_start = start + run_cursor
                    regions.append({
                        "region_id": f"docx-p{paragraph_counter:04d}-run-{run_index:03d}",
                        "kind": "docx_run",
                        "paragraph": paragraph_counter,
                        "run": run_index,
                        "start": run_start,
                        "end": run_start + len(run_text),
                        "text": run_text,
                        "style": run.style.name if run.style else None,
                        "coordinate_system": "unicode-character-offsets",
                        "coordinates_available": False,
                    })
                    run_cursor += len(run_text)
            elif child.tag.endswith("}tbl"):
                table_counter += 1
                table = DocxTable(child, document)
                for row_index, row in enumerate(table.rows, start=1):
                    cells = []
                    seen_cells: set[int] = set()
                    for cell in row.cells:
                        marker = id(cell._tc)
                        if marker in seen_cells:
                            continue
                        seen_cells.add(marker)
                        cells.append(cell)
                    cell_texts = [cell.text for cell in cells]
                    row_text = " | ".join(cell_texts)
                    if not row_text.strip():
                        continue
                    row_start = append_block(row_text)
                    regions.append({
                        "region_id": f"docx-table-{table_counter:03d}-row-{row_index:03d}",
                        "kind": "docx_table_row",
                        "table": table_counter,
                        "row": row_index,
                        "start": row_start,
                        "end": row_start + len(row_text),
                        "text": row_text,
                        "coordinate_system": "unicode-character-offsets",
                        "coordinates_available": False,
                    })
                    cell_cursor = 0
                    for cell_index, (cell, cell_value) in enumerate(zip(cells, cell_texts, strict=True), start=1):
                        cell_start = row_start + cell_cursor
                        if cell_value.strip():
                            regions.append({
                                "region_id": f"docx-table-{table_counter:03d}-row-{row_index:03d}-cell-{cell_index:03d}",
                                "kind": "docx_table_cell",
                                "table": table_counter,
                                "row": row_index,
                                "cell": cell_index,
                                "start": cell_start,
                                "end": cell_start + len(cell_value),
                                "text": cell_value,
                                "coordinate_system": "unicode-character-offsets",
                                "coordinates_available": False,
                            })
                            paragraph_cursor = 0
                            for cell_paragraph_index, cell_paragraph in enumerate(cell.paragraphs, start=1):
                                paragraph_value = cell_paragraph.text or ""
                                run_cursor = 0
                                for run_index, run in enumerate(cell_paragraph.runs, start=1):
                                    run_text = run.text or ""
                                    if run_text:
                                        run_start = cell_start + paragraph_cursor + run_cursor
                                        regions.append({
                                            "region_id": f"docx-t{table_counter:03d}-r{row_index:03d}-c{cell_index:03d}-p{cell_paragraph_index:03d}-run{run_index:03d}",
                                            "kind": "docx_run",
                                            "table": table_counter,
                                            "row": row_index,
                                            "cell": cell_index,
                                            "paragraph": cell_paragraph_index,
                                            "run": run_index,
                                            "start": run_start,
                                            "end": run_start + len(run_text),
                                            "text": run_text,
                                            "coordinate_system": "unicode-character-offsets",
                                            "coordinates_available": False,
                                        })
                                        run_cursor += len(run_text)
                                paragraph_cursor += len(paragraph_value) + 1
                        cell_cursor += len(cell_value) + (3 if cell_index < len(cells) else 0)

        # Headers and footers are included as separately labelled logical blocks so
        # important legal/fine-print language is not silently omitted from review.
        header_footer_seen: set[tuple[str, str]] = set()
        for section_index, section in enumerate(document.sections, start=1):
            for label, container in (("header", section.header), ("footer", section.footer)):
                for paragraph_index, paragraph in enumerate(container.paragraphs, start=1):
                    value = paragraph.text or ""
                    key = (label, value)
                    if not value.strip() or key in header_footer_seen:
                        continue
                    header_footer_seen.add(key)
                    prefixed = f"[{label.upper()}] {value}"
                    start = append_block(prefixed)
                    regions.append({
                        "region_id": f"docx-{label}-s{section_index:02d}-p{paragraph_index:03d}",
                        "kind": f"docx_{label}",
                        "section": section_index,
                        "paragraph": paragraph_index,
                        "start": start,
                        "end": start + len(prefixed),
                        "text": prefixed,
                        "coordinate_system": "unicode-character-offsets",
                        "coordinates_available": False,
                    })

        image_regions = []
        for image_index, shape in enumerate(document.inline_shapes, start=1):
            description = ""
            try:
                description = str(shape._inline.docPr.get("descr") or "").strip()
            except Exception:
                description = ""
            image_regions.append({
                "region_id": f"docx-image-{image_index:04d}",
                "kind": "docx_image_metadata",
                "image_index": image_index,
                "width_emu": int(shape.width),
                "height_emu": int(shape.height),
                "alt_text_present": bool(description),
                "alt_text": description or None,
                "coordinate_system": "docx-emu-inline-shape",
                "coordinates_available": False,
            })
        regions.extend(image_regions)
        text = "\n".join(blocks)
        if not text.strip():
            return ExtractionResult(
                text, confidence=0.0, status="PARTIAL",
                warnings=["DOCX_TEXT_EMPTY: manual inspection is required."], regions=regions,
            )
        warnings_list = [
            "DOCX_RENDERED_PAGE_COORDINATES_UNAVAILABLE: paragraph, run, table-cell and header/footer offsets are available; use a renderer before claiming page geometry.",
        ]
        if image_regions:
            missing_alt = sum(not region["alt_text_present"] for region in image_regions)
            if missing_alt:
                warnings_list.append(
                    f"DOCX_IMAGE_ALT_TEXT_MISSING: {missing_alt} embedded image(s) have no alt text; inspect their content and accessibility manually."
                )
            warnings_list.append(
                "DOCX_EMBEDDED_MEDIA_NOT_OCR_ANALYSED: embedded image/drawing pixels are inventoried but are not included in searchable OCR text; inspect them manually."
            )
        return ExtractionResult(text, warnings=warnings_list, regions=regions)

    if extension == ".pdf":
        return _extract_pdf(data, contrast_threshold)

    if extension in {".png", ".jpg", ".jpeg"}:
        metadata_region: dict[str, Any] | None = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                source_image = Image.open(BytesIO(data))
                image_format = source_image.format or extension.lstrip(".").upper()
                source_width, source_height = source_image.size
                if source_width * source_height > MAX_IMAGE_PIXELS:
                    raise ValueError("IMAGE_PIXEL_LIMIT_EXCEEDED")
                exif_orientation = source_image.getexif().get(274, 1)
                image = ImageOps.exif_transpose(source_image).convert("RGB")
                width, height = image.size
            palette = _dominant_palette(image)
            for color in palette:
                color["ratio"] = color.get("coverage", 0.0)
            palette_comparison: dict[str, Any] = {
                "status": "UNMEASURABLE",
                "reason": "NO_APPROVED_PALETTE_POLICY",
                "score": None,
                "threshold": None,
            }
            if isinstance(palette_policy, dict) and palette_policy.get("palette_hex"):
                allowed_palette = palette_policy.get("palette_hex")
                tolerance = palette_policy.get("palette_tolerance", 80)
                required_ratio = palette_policy.get("minimum_palette_match_ratio", 0.7)
                if (
                    isinstance(allowed_palette, list)
                    and allowed_palette
                    and isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool)
                    and isinstance(required_ratio, (int, float)) and not isinstance(required_ratio, bool)
                ):
                    from sigillum.modules.knowledge.asset_policy import palette_match_ratio
                    observed = [{"hex": item["hex"], "ratio": item.get("coverage", 0.0)} for item in palette]
                    score = palette_match_ratio(observed, allowed_palette, float(tolerance))
                    palette_comparison = {
                        "status": "PASS" if score >= float(required_ratio) else "FAIL",
                        "reason": "APPROVED_PALETTE_TOLERANCE_MEASURED",
                        "score": round(score, 4),
                        "threshold": float(required_ratio),
                        "tolerance_rgb_distance": float(tolerance),
                        "allowed_palette": allowed_palette,
                        "method": "weighted-nearest-rgb-distance-v1",
                        "limitation": "Bounded RGB-distance comparison on dominant sampled colours; not colour-managed brand identity certification. Human confirmation is required for a failure.",
                    }
                else:
                    palette_comparison = {
                        "status": "UNMEASURABLE",
                        "reason": "APPROVED_PALETTE_POLICY_INVALID",
                        "score": None,
                        "threshold": required_ratio if isinstance(required_ratio, (int, float)) else None,
                    }
            metadata_region = {
                "region_id": "image-metadata",
                "kind": "image_metadata",
                "width": width,
                "height": height,
                "source_width": source_width,
                "source_height": source_height,
                "format": image_format,
                "exif_orientation": int(exif_orientation) if isinstance(exif_orientation, int) else 1,
                "coordinate_system": "image-pixels-top-left-origin",
                "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                "perceptual_hash": _perceptual_hash(image),
                "perceptual_hash_algorithm": "dhash-64-v1",
                "palette": palette,
                "palette_comparison": palette_comparison,
                "palette_notice": "Descriptive dominant-colour inventory only; comparison is reported only when an approved in-scope tolerance rule exists. Palette similarity is not brand identity certification.",
                "region_schema_version": "2.0",
                "preprocessing": ["EXIF orientation applied", "RGB conversion"],
                "ocr_engine": "Tesseract",
                "ocr_config": "--psm 6",
            }
            settings = get_settings()
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
            try:
                metadata_region["ocr_engine_version"] = str(pytesseract.get_tesseract_version())
            except Exception:
                metadata_region["ocr_engine_version"] = "unavailable"
            ocr_timeout = max(1, min(120, int(getattr(settings, "ocr_timeout_seconds", 20))))
            metadata_region["ocr_language"] = settings.tesseract_lang
            raw = pytesseract.image_to_data(
                image, output_type=Output.DICT, lang=settings.tesseract_lang,
                config="--psm 6", timeout=ocr_timeout
            )
            text, regions, confidences = _ocr_line_regions(image, raw, contrast_threshold)
            average = sum(confidences) / len(confidences) if confidences else 0.0
            warnings_list: list[str] = []
            if average < 0.75:
                warnings_list.append("LOW_OCR_CONFIDENCE: extracted text is uncertain and requires visual inspection.")
            if not text:
                warnings_list.append("OCR_EMPTY: no readable text was extracted from this image.")
            if not any(region.get("contrast", {}).get("status") in {"PASS", "FAIL"} for region in regions):
                warnings_list.append("CONTRAST_UNMEASURABLE: no OCR line produced a sufficiently reliable local contrast measurement.")
            status = "COMPLETED" if text and average >= 0.75 else "PARTIAL"
            return ExtractionResult(text, average, status, warnings_list, [metadata_region, *regions])
        except ValueError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError(f"INVALID_OR_UNSAFE_IMAGE: {type(exc).__name__}") from exc
        except Exception as exc:
            warning_list = [f"OCR_UNAVAILABLE: {type(exc).__name__}; manual visual review is required."]
            metadata_regions = [metadata_region] if metadata_region else []
            return ExtractionResult("", 0.0, "PARTIAL", warning_list, metadata_regions)

    raise ValueError("UNSUPPORTED_FILE")
