"""
NexClaim OCR Module.

Extracts text from PDF and image files using Tesseract OCR with
pdf2image for PDF rendering. Applies OpenCV image enhancements and
post-processing artifact correction. Falls back to pypdf text extraction
if Tesseract/Poppler binaries are not available.
"""

import io
import logging
import os
from pathlib import Path
import tempfile
import httpx
from typing import Optional

try:
    from app.ai.ocr.image_enhancement import ImageEnhancer
except ImportError:
    ImageEnhancer = None

try:
    from app.ai.ocr.post_processor import OCRPostProcessor
except ImportError:
    OCRPostProcessor = None

logger = logging.getLogger(__name__)


class OcrProcessor:
    """Handles OCR text extraction from PDF and image files."""

    SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
    SUPPORTED_PDF_EXTENSION = ".pdf"

    def __init__(self):
        self.post_processor = OCRPostProcessor() if OCRPostProcessor else None

    def extract_text_from_file(self, file_path: str) -> tuple[str, float]:
        """
        Extract text from a file using OCR or direct text extraction.
        Handles both local file paths and remote URLs.

        Returns:
            Tuple of (extracted_text, quality_score 0.0-1.0)
        """
        temp_file_path = None
        if file_path.startswith("http://") or file_path.startswith("https://"):
            try:
                response = httpx.get(file_path, timeout=30.0)
                response.raise_for_status()
                # Determine extension from URL or content-type
                extension = ".pdf" if "pdf" in response.headers.get("content-type", "").lower() else ".jpg"
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
                temp_file.write(response.content)
                temp_file.close()
                temp_file_path = temp_file.name
                file_path_to_process = temp_file_path
                extension = Path(temp_file_path).suffix.lower()
            except Exception as e:
                logger.error("Failed to download file for OCR from %s: %s", file_path, e)
                return "", 0.0
        else:
            path = Path(file_path)
            extension = path.suffix.lower()
            if not path.exists():
                logger.error("File not found for OCR: %s", file_path)
                return "", 0.0
            file_path_to_process = file_path

        try:
            if extension == self.SUPPORTED_PDF_EXTENSION:
                text, score = self._extract_from_pdf(file_path_to_process)
            elif extension in self.SUPPORTED_IMAGE_EXTENSIONS:
                text, score = self._extract_from_image(file_path_to_process)
            else:
                logger.warning("Unsupported file extension for OCR: %s", extension)
                return "", 0.0
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.warning("Failed to remove temp file %s: %s", temp_file_path, e)
            
        if self.post_processor:
            text = self.post_processor.process(text)
            
        return text, score

    def _extract_from_pdf(self, file_path: str) -> tuple[str, float]:
        """Extract text from a PDF file."""
        # Try native PDF text extraction first (100% accurate for digital PDFs)
        try:
            text, score = self._pdf_via_pypdf(file_path)
            # If we extracted a reasonable amount of text, it's a native PDF.
            if len(text.strip()) > 50:
                logger.info("Native PDF text extracted successfully (%d chars)", len(text))
                return text, score
            logger.info("Native PDF extraction returned too little text. Falling back to OCR.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("pypdf extraction failed: %s. Trying Tesseract OCR.", exc)

        # Fallback: Tesseract OCR for scanned PDFs
        try:
            return self._pdf_via_tesseract(file_path)
        except ImportError:
            logger.info("Tesseract/pdf2image not available")
            return "", 0.0
        except Exception as exc:  # noqa: BLE001
            logger.error("Tesseract PDF extraction failed: %s", exc)
            return "", 0.0

    def _pdf_via_tesseract(self, file_path: str) -> tuple[str, float]:
        """Extract text from PDF pages using Tesseract OCR via pdf2image."""
        from pdf2image import convert_from_path  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        pages = convert_from_path(file_path, dpi=300)
        all_text_parts = []
        total_confidence = 0.0
        valid_pages = 0

        for page_image in pages:
            if ImageEnhancer:
                page_image = ImageEnhancer.enhance_for_ocr(page_image)
                
            data = pytesseract.image_to_data(
                page_image,
                output_type=pytesseract.Output.DICT,
                config="--psm 6",
            )
            page_text = pytesseract.image_to_string(page_image, config="--psm 6")
            all_text_parts.append(page_text)

            confidences = [
                int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0
            ]
            if confidences:
                total_confidence += sum(confidences) / len(confidences)
                valid_pages += 1

        combined_text = "\n".join(all_text_parts).strip()
        quality_score = (total_confidence / valid_pages / 100.0) if valid_pages else 0.0
        logger.info(
            "PDF OCR complete via Tesseract: %d chars, quality=%.2f",
            len(combined_text),
            quality_score,
        )
        return combined_text, min(quality_score, 1.0)

    def _pdf_via_pypdf(self, file_path: str) -> tuple[str, float]:
        """Extract text from PDF using pypdf library."""
        try:
            import pypdf  # type: ignore

            reader = pypdf.PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)

            combined = "\n".join(text_parts).strip()
            # Quality is lower for direct PDF extraction (not image-based)
            quality = 0.75 if combined else 0.0
            logger.info(
                "PDF text extracted via pypdf: %d chars, quality=%.2f",
                len(combined),
                quality,
            )
            return combined, quality
        except Exception as exc:  # noqa: BLE001
            logger.error("pypdf extraction failed for %s: %s", file_path, exc)
            return "", 0.0

    def _extract_from_image(self, file_path: str) -> tuple[str, float]:
        """Extract text from an image file using Tesseract OCR."""
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            image = Image.open(file_path)
            if ImageEnhancer:
                image = ImageEnhancer.enhance_for_ocr(image)
                
            data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config="--psm 6",
            )
            text = pytesseract.image_to_string(image, config="--psm 6")

            confidences = [
                int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0
            ]
            quality = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
            logger.info(
                "Image OCR complete: %d chars, quality=%.2f", len(text), quality
            )
            return text.strip(), min(quality, 1.0)
        except ImportError:
            logger.warning("pytesseract not available for image OCR")
            return "", 0.0
        except Exception as exc:  # noqa: BLE001
            logger.error("Image OCR failed for %s: %s", file_path, exc)
            return "", 0.0


ocr_processor = OcrProcessor()
