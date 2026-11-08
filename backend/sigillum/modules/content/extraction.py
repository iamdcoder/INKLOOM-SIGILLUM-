"""Safe, bounded extraction adapters with source-mapped logical and visual regions."""
from __future__ import annotations

import hashlib
import statistics
import warnings
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
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
            if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                raise ValueError("INVALID_DOCX_PACKAGE_PATH")
    except BadZipFile as exc:
        raise ValueError("INVALID_DOCX_PACKAGE") from exc


def sniff_file(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("UNSUPPORTED_FILE: allowed formats are PDF, DOCX, TXT, PNG and JPG")
    if not data:
        raise ValueError("EMPTY_FILE")

    valid = False
    if extension == ".pdf":
        valid = data.startswith(b"%PDF-")
    elif extension == ".docx":
        valid = data.startswith(b"PK")
        if valid:
            _validate_docx_archive(data)
    elif extension == ".txt":
        try:
            data.decode("utf-8-sig")
            valid = True
        except UnicodeDecodeError:
            valid = False
    elif extension == ".png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg", ".jpeg"}:
        valid = data.startswith(b"\xff\xd8\xff")

    if not valid:
        raise ValueError("INVALID_FILE_SIGNATURE: file contents do not match the declared format")

    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }[extension]


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
) -> tuple[str, list[dict[str, Any]], list[float]]:
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
        group_key = tuple(str(raw.get(key, [0] * (index + 1))[index]) for key in keys)
        grouped.setdefault(group_key, []).append({"text": token, "confidence": confidence, "bbox": box})

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
        bbox = {"x": min(xs), "y": min(ys), "width": max(rights) - min(xs), "height": max(bottoms) - min(ys)}
        confidence = sum(word["confidence"] for word in words) / len(words)
        if text_parts:
            cursor += 1  # newline between line groups
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
            "region_id": f"ocr-line-{line_number:04d}",
            "kind": "ocr_line",
            "page": 1,
            "text": line_text,
            "start": start,
            "end": end,
            "confidence": round(confidence, 3),
            "bbox": bbox,
            "polygon": _polygon_from_bbox(bbox),
            "normalised_bbox": _normalised_bbox(bbox, image.width, image.height),
            "coordinate_system": "image-pixels-top-left-origin",
            "page_dimensions": {"width": image.width, "height": image.height, "units": "pixels"},
            "words": word_boxes,
            "contrast": measure_region_contrast(image, bbox, contrast_threshold, confidence),
        })
        text_parts.append(line_text)
        cursor = end
        confidences.append(confidence)
    return "\n".join(text_parts), regions, confidences


def extract(filename: str, data: bytes, contrast_threshold: float | None = None) -> ExtractionResult:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("UNSUPPORTED_FILE")
    if not data:
        raise ValueError("EMPTY_FILE")

    if extension == ".txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return ExtractionResult(
                "", 0.0, "PARTIAL", ["TXT_ENCODING_UNREADABLE: UTF-8 decoding failed; manual inspection required."], []
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
            return ExtractionResult(text, 0.0, "PARTIAL", ["CONTENT_EMPTY: no readable text was found."], regions)
        return ExtractionResult(text, regions=regions)

    if extension == ".docx":
        _validate_docx_archive(data)
        document = Document(BytesIO(data))
        blocks: list[str] = []
        regions: list[dict[str, Any]] = []
        cursor = 0
        for paragraph_index, paragraph in enumerate(document.paragraphs, start=1):
            paragraph_text = paragraph.text
            if not paragraph_text.strip():
                continue
            if blocks:
                cursor += 1
            start = cursor
            end = start + len(paragraph_text)
            blocks.append(paragraph_text)
            regions.append({
                "region_id": f"docx-paragraph-{paragraph_index:04d}",
                "kind": "docx_paragraph",
                "paragraph": paragraph_index,
                "style": paragraph.style.name if paragraph.style else None,
                "start": start,
                "end": end,
                "text": paragraph_text,
                "coordinate_system": "unicode-character-offsets",
                "coordinates_available": False,
            })
            cursor = end
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                row_text = " | ".join(cell.text for cell in row.cells)
                if not row_text.strip():
                    continue
                if blocks:
                    cursor += 1
                start = cursor
                end = start + len(row_text)
                blocks.append(row_text)
                regions.append({
                    "region_id": f"docx-table-{table_index:03d}-row-{row_index:03d}",
                    "kind": "docx_table_row",
                    "table": table_index,
                    "row": row_index,
                    "start": start,
                    "end": end,
                    "text": row_text,
                    "coordinate_system": "unicode-character-offsets",
                    "coordinates_available": False,
                })
                cursor = end
        text = "\n".join(blocks)
        if not text.strip():
            return ExtractionResult(
                text, confidence=0.0, status="PARTIAL",
                warnings=["DOCX_TEXT_EMPTY: manual inspection is required."], regions=regions,
            )
        warnings_list = [
            "DOCX_RENDERED_PAGE_COORDINATES_UNAVAILABLE: paragraph and table offsets are available; layout coordinates require a renderer.",
            "DOCX_EMBEDDED_MEDIA_NOT_ANALYSED: embedded images and drawing objects require manual visual inspection.",
        ]
        return ExtractionResult(text, warnings=warnings_list, regions=regions)

    if extension == ".pdf":
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError("PASSWORD_PROTECTED_PDF")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ValueError("PDF_PAGE_LIMIT_EXCEEDED")
            pages: list[str] = []
            regions: list[dict[str, Any]] = []
            offset = 0
            empty_pages: list[int] = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                pages.append(page_text)
                try:
                    page_width = float(page.mediabox.width)
                    page_height = float(page.mediabox.height)
                except (AttributeError, TypeError, ValueError):
                    page_width = page_height = None
                if page_text.strip():
                    regions.append({
                        "region_id": f"pdf-page-{page_number:04d}",
                        "kind": "pdf_page_text",
                        "page": page_number,
                        "start": offset,
                        "end": offset + len(page_text),
                        "width": page_width,
                        "height": page_height,
                        "coordinate_system": "pdf-points-bottom-left-origin",
                        "coordinates_available": False,
                        "text": page_text,
                    })
                else:
                    empty_pages.append(page_number)
                offset += len(page_text) + 1
            text = "\n".join(pages)
            warnings_list = [
                "PDF_VISUAL_CONTENT_NOT_ANALYSED: embedded raster images and complex visual layout require manual inspection.",
                "PDF_RENDERED_COORDINATES_UNAVAILABLE: text offsets and page dimensions are retained; a renderer is required for region polygons.",
            ]
            if empty_pages:
                warnings_list.append("PDF_PAGES_WITHOUT_EXTRACTABLE_TEXT: " + ", ".join(map(str, empty_pages)))
            if not text.strip():
                warnings_list.append("PDF_TEXT_EMPTY: this may be a scanned PDF; page-image OCR is not enabled in this build.")
                return ExtractionResult(text, 0.0, "PARTIAL", warnings_list, regions)
            return ExtractionResult(text, warnings=warnings_list, regions=regions)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PARSE_FAILED_PDF: {type(exc).__name__}") from exc

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
            metadata_region = {
                "region_id": "image-metadata",
                "kind": "image_metadata",
                "width": width,
                "height": height,
                "format": image_format,
                "exif_orientation": int(exif_orientation) if isinstance(exif_orientation, int) else 1,
                "coordinate_system": "image-pixels-top-left-origin",
                "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                "palette": _dominant_palette(image),
                "palette_notice": "Descriptive dominant-colour inventory only; no brand-palette verdict is inferred without an approved tolerance rule.",
                "region_schema_version": "1.0",
                "preprocessing": ["EXIF orientation applied", "RGB conversion"],
                "ocr_engine": "Tesseract",
                "ocr_config": "--psm 6",
            }
            pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd
            try:
                metadata_region["ocr_engine_version"] = str(pytesseract.get_tesseract_version())
            except Exception:
                metadata_region["ocr_engine_version"] = "unavailable"
            raw = pytesseract.image_to_data(image, output_type=Output.DICT, config="--psm 6", timeout=20)
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
        except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ValueError(f"INVALID_OR_UNSAFE_IMAGE: {type(exc).__name__}") from exc
        except Exception as exc:
            warning_list = [f"OCR_UNAVAILABLE: {type(exc).__name__}; manual visual review is required."]
            metadata_regions = [metadata_region] if metadata_region else []
            return ExtractionResult("", 0.0, "PARTIAL", warning_list, metadata_regions)

    raise ValueError("UNSUPPORTED_FILE")
