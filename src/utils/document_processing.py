import io
import re
import zipfile
from xml.etree import ElementTree as ET

from pypdf import PdfReader


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
    """Extrai texto de cada pagina de um PDF usando a extracao nativa do arquivo."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        return []

    extracted_pages = []
    total_pages = len(reader.pages)
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw_text = page.extract_text() or ""
            page_text = repair_extracted_pdf_text(raw_text)
        except Exception:
            page_text = ""

        if page_text:
            extracted_pages.append(
                {
                    "page_number": page_number,
                    "text": page_text,
                    "extraction_method": "text",
                }
            )
        if callable(progress_callback):
            progress_callback(
                page_number,
                total_pages,
                f"Processando pagina {page_number} de {total_pages}",
            )

    return extracted_pages


def extract_pdf_text(file_bytes: bytes, progress_callback=None) -> str:
    """Extrai o texto completo de um PDF usando a extracao nativa do arquivo."""
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
