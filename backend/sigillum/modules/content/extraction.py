"""Safe, bounded extraction adapters for the MVP-supported input formats."""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

import pytesseract
from docx import Document
from PIL import Image, UnidentifiedImageError
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


def extract(filename: str, data: bytes) -> ExtractionResult:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("UNSUPPORTED_FILE")
    if not data:
        raise ValueError("EMPTY_FILE")

    if extension == ".txt":
        text = data.decode("utf-8-sig")
        if not text.strip():
            return ExtractionResult(
                text,
                confidence=0.0,
                status="PARTIAL",
                warnings=["CONTENT_EMPTY: no readable text was found."],
            )
        return ExtractionResult(text)

    if extension == ".docx":
        _validate_docx_archive(data)
        document = Document(BytesIO(data))
        blocks = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(blocks)
        if not text.strip():
            return ExtractionResult(
                text,
                confidence=0.0,
                status="PARTIAL",
                warnings=["DOCX_TEXT_EMPTY: manual inspection is required."],
            )
        warnings_list = [
            "DOCX_EMBEDDED_MEDIA_NOT_ANALYSED: embedded images and drawing objects require manual visual inspection."
        ]
        return ExtractionResult(text, warnings=warnings_list)

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
                if page_text.strip():
                    regions.append(
                        {
                            "kind": "page_text",
                            "page": page_number,
                            "start": offset,
                            "end": offset + len(page_text),
                        }
                    )
                else:
                    empty_pages.append(page_number)
                offset += len(page_text) + 1
            text = "\n".join(pages)
            warnings_list = [
                "PDF_VISUAL_CONTENT_NOT_ANALYSED: embedded raster images and complex visual layout require manual inspection."
            ]
            if empty_pages:
                warnings_list.append(
                    "PDF_PAGES_WITHOUT_EXTRACTABLE_TEXT: " + ", ".join(map(str, empty_pages))
                )
            if not text.strip():
                warnings_list.append(
                    "PDF_TEXT_EMPTY: this may be a scanned PDF; page-image OCR is not enabled in this build."
                )
                return ExtractionResult(text, 0.0, "PARTIAL", warnings_list, regions)
            return ExtractionResult(text, warnings=warnings_list, regions=regions)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PARSE_FAILED_PDF: {type(exc).__name__}") from exc

    if extension in {".png", ".jpg", ".jpeg"}:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(BytesIO(data))
                width, height = image.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("IMAGE_PIXEL_LIMIT_EXCEEDED")
                image = image.convert("RGB")
            pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd
            raw = pytesseract.image_to_data(image, output_type=Output.DICT, config="--psm 6")
            words: list[str] = []
            regions: list[dict[str, Any]] = []
            confidences: list[float] = []
            cursor = 0
            for index, token in enumerate(raw["text"]):
                token = (token or "").strip()
                try:
                    confidence = float(raw["conf"][index])
                except (TypeError, ValueError):
                    confidence = -1
                if not token or confidence < 0:
                    continue
                start = cursor
                words.append(token)
                cursor += len(token) + 1
                normalised_confidence = confidence / 100.0
                confidences.append(normalised_confidence)
                regions.append(
                    {
                        "kind": "ocr_word",
                        "text": token,
                        "start": start,
                        "end": start + len(token),
                        "confidence": round(normalised_confidence, 3),
                        "bbox": {
                            "x": int(raw["left"][index]),
                            "y": int(raw["top"][index]),
                            "width": int(raw["width"][index]),
                            "height": int(raw["height"][index]),
                        },
                    }
                )
            text = " ".join(words)
            average = sum(confidences) / len(confidences) if confidences else 0.0
            warnings_list: list[str] = []
            if average < 0.75:
                warnings_list.append(
                    "LOW_OCR_CONFIDENCE: extracted text is uncertain and requires visual inspection."
                )
            if not text:
                warnings_list.append("OCR_EMPTY: no readable text was extracted from this image.")
            status = "COMPLETED" if text and average >= 0.75 else "PARTIAL"
            return ExtractionResult(text, average, status, warnings_list, regions)
        except ValueError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ValueError(f"INVALID_OR_UNSAFE_IMAGE: {type(exc).__name__}") from exc
        except Exception as exc:
            return ExtractionResult(
                "",
                0.0,
                "PARTIAL",
                [f"OCR_UNAVAILABLE: {type(exc).__name__}; manual visual review is required."],
                [],
            )

    raise ValueError("UNSUPPORTED_FILE")
