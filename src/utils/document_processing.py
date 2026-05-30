import io
import re
import zipfile
from functools import lru_cache
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from utils.config import (
    OCR_ENABLED,
    OCR_LANGUAGE,
    OCR_MIN_TEXT_CHARS,
    OCR_RENDER_SCALE,
    OCR_TESSERACT_CONFIG,
    OCR_TIMEOUT_SECONDS,
    TESSERACT_CMD,
)

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


def normalize_text(text: str) -> str:
    """Normaliza espacos em branco do texto."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_docx_text(file_bytes: bytes) -> str:
    """Extrai o texto principal de um arquivo DOCX."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            xml_content = archive.read("word/document.xml")
    except Exception:
        return ""

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return ""

    paragraphs = []
    current_parts = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "t" and element.text:
            current_parts.append(element.text)
        elif tag == "p":
            paragraph = "".join(current_parts).strip()
            if paragraph:
                paragraphs.append(paragraph)
            current_parts = []

    trailing = "".join(current_parts).strip()
    if trailing:
        paragraphs.append(trailing)

    return normalize_text("\n".join(paragraphs))


def extract_pdf_pages(file_bytes: bytes, progress_callback=None) -> list[dict]:
    """Extrai texto de cada pagina de um PDF, com OCR opcional para paginas pobres em texto."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        return []

    pdf_document = _open_pdfium_document(file_bytes) if is_ocr_available() else None
    extracted_pages = []

    try:
        total_pages = len(reader.pages)
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                raw_direct_text = page.extract_text() or ""
                direct_text = repair_extracted_pdf_text(raw_direct_text)
            except Exception:
                direct_text = ""

            selected_text = direct_text
            extraction_method = "text"

            if pdf_document is not None and _page_needs_ocr(direct_text):
                ocr_text = _extract_page_ocr_text(pdf_document, page_number - 1)
                if _should_prefer_ocr(direct_text, ocr_text):
                    selected_text = ocr_text
                    extraction_method = "ocr"

            if selected_text:
                extracted_pages.append(
                    {
                        "page_number": page_number,
                        "text": selected_text,
                        "extraction_method": extraction_method,
                    }
                )
            if callable(progress_callback):
                progress_callback(
                    page_number,
                    total_pages,
                    f"Processando pagina {page_number} de {total_pages}",
                )
    finally:
        _safe_close(pdf_document)

    return extracted_pages


def extract_pdf_text(file_bytes: bytes, progress_callback=None) -> str:
    """Extrai o texto completo de um PDF usando OCR quando necessario."""
    pages = extract_pdf_pages(file_bytes, progress_callback=progress_callback)
    page_blocks = []
    for page in pages:
        page_blocks.append(f"[Pagina {page['page_number']}]\n{page['text']}")
    return "\n\n".join(page_blocks).strip()


def repair_extracted_pdf_text(raw_text: str) -> str:
    """Reconstrui palavras quando o PDF foi extraido com letras separadas."""
    if not raw_text:
        return ""

    normalized_source = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    merged_lines = []
    single_char_buffer = []

    for raw_line in normalized_source.split("\n"):
        stripped_line = raw_line.strip()
        if not stripped_line:
            if single_char_buffer:
                merged_lines.append("".join(single_char_buffer))
                single_char_buffer = []
            continue

        if len(stripped_line) == 1:
            single_char_buffer.append(stripped_line)
            continue

        if single_char_buffer:
            merged_lines.append("".join(single_char_buffer))
            single_char_buffer = []

        merged_lines.append(_collapse_spaced_letters_in_line(stripped_line))

    if single_char_buffer:
        merged_lines.append("".join(single_char_buffer))

    return normalize_text("\n".join(merged_lines))


@lru_cache(maxsize=1)
def is_ocr_available() -> bool:
    """Indica se o OCR esta pronto para uso."""
    if not OCR_ENABLED or pdfium is None or pytesseract is None:
        return False

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False

    return True


def _open_pdfium_document(file_bytes: bytes):
    """Abre o PDF em um renderer apto para OCR."""
    if pdfium is None:
        return None

    try:
        return pdfium.PdfDocument(file_bytes)
    except Exception:
        return None


def _page_needs_ocr(extracted_text: str) -> bool:
    """Decide se vale tentar OCR em uma pagina."""
    if not extracted_text:
        return True

    if len(extracted_text) < OCR_MIN_TEXT_CHARS:
        return True

    terms = re.findall(r"[a-zA-Z0-9_-]{3,}", extracted_text)
    return len(terms) < 12


def _should_prefer_ocr(direct_text: str, ocr_text: str) -> bool:
    """Compara o texto extraido nativamente com o OCR."""
    if not ocr_text:
        return False

    if not direct_text:
        return True

    if len(ocr_text) >= len(direct_text) * 1.25:
        return True

    direct_terms = set(re.findall(r"[a-zA-Z0-9_-]{3,}", direct_text.lower()))
    ocr_terms = set(re.findall(r"[a-zA-Z0-9_-]{3,}", ocr_text.lower()))
    if not direct_terms:
        return True

    return len(ocr_terms) > len(direct_terms) * 1.2 and len(ocr_text) > len(direct_text)


def _extract_page_ocr_text(pdf_document, page_index: int) -> str:
    """Renderiza uma pagina e aplica OCR."""
    if pdf_document is None or pytesseract is None:
        return ""

    page = None
    bitmap = None
    image = None
    try:
        page = pdf_document[page_index]
        bitmap = page.render(scale=OCR_RENDER_SCALE)
        image = bitmap.to_pil()
        ocr_text = pytesseract.image_to_string(
            image,
            lang=OCR_LANGUAGE,
            config=OCR_TESSERACT_CONFIG,
            timeout=OCR_TIMEOUT_SECONDS,
        )
        return normalize_text(ocr_text)
    except Exception:
        return ""
    finally:
        _safe_close(image)
        _safe_close(bitmap)
        _safe_close(page)


def _safe_close(resource) -> None:
    """Fecha recursos quando suportado."""
    if resource is None:
        return

    close_method = getattr(resource, "close", None)
    if callable(close_method):
        try:
            close_method()
        except Exception:
            pass


def _collapse_spaced_letters_in_line(line: str) -> str:
    """Colapsa linhas em que as letras vieram separadas por espacos."""
    tokens = line.split()
    if not tokens:
        return ""

    single_char_ratio = sum(len(token) == 1 for token in tokens) / len(tokens)
    if len(tokens) < 3 or single_char_ratio < 0.55:
        return line

    parts = re.split(r"(\s{2,})", line)
    collapsed_parts = []
    for part in parts:
        if not part or part.isspace():
            if part:
                collapsed_parts.append(" ")
            continue

        segment_tokens = part.split()
        segment_single_char_ratio = sum(len(token) == 1 for token in segment_tokens) / max(len(segment_tokens), 1)
        if len(segment_tokens) >= 2 and segment_single_char_ratio >= 0.55:
            collapsed_parts.append("".join(segment_tokens))
        else:
            collapsed_parts.append(part.strip())

    return re.sub(r"\s+", " ", "".join(collapsed_parts)).strip()
