import hashlib
import re
import shutil
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path


import pytesseract
from PIL import Image
from docx import Document
from pptx import Presentation
from pypdf import PdfReader
from pypdf.errors import PyPdfError


# Kept for compatibility with other files in the project.
MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 400_000

SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".txt", ".md"}


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    page: int
    text: str

    def to_dict(self):
        return asdict(self)


def find_tesseract():
    """Find the installed OCR program on Windows or in PATH."""
    if shutil.which("tesseract"):
        return

    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]

    for candidate in candidates:
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return

    raise ValueError(
        "OCR is needed for this scanned page. Install Tesseract OCR "
        "and restart EvidenceDesk."
    )


def read_pdf(content: bytes):
    try:
        reader = PdfReader(BytesIO(content))

        if reader.is_encrypted:
            raise ValueError("Use a PDF without password protection.")

        pages = []
        ocr_document = None

        try:
            for index, page in enumerate(reader.pages):
                text = page.extract_text() or ""

                # If a page has no readable text, try OCR on its image.
                if not text.strip():
                    find_tesseract()

                    if ocr_document is None:
                        ocr_document = fitz.open(
                            stream=content,
                            filetype="pdf",
                        )

                    rendered = ocr_document[index].get_pixmap(
                        matrix=fitz.Matrix(2, 2),
                        alpha=False,
                    )

                    image = Image.open(
                        BytesIO(rendered.tobytes("png"))
                    )
                    text = pytesseract.image_to_string(image)

                pages.append((index + 1, text))

        finally:
            if ocr_document is not None:
                ocr_document.close()

        return pages

    except PyPdfError as error:
        raise ValueError(
            "This PDF could not be read. Try exporting it again."
        ) from error


def parse_document(name: str, content: bytes) -> list[tuple[int, str]]:
    suffix = Path(name).suffix.lower()

    if suffix == ".pdf":
        pages = read_pdf(content)

    elif suffix == ".pptx":
        presentation = Presentation(BytesIO(content))
        pages = []

        for number, slide in enumerate(presentation.slides, 1):
            text_parts = []

            for shape in slide.shapes:
                if shape.has_text_frame:
                    text_parts.append(shape.text)

                if shape.has_table:
                    for row in shape.table.rows:
                        text_parts.append(
                            " | ".join(cell.text for cell in row.cells)
                        )

            pages.append((number, "\n".join(text_parts)))

    elif suffix == ".docx":
        document = Document(BytesIO(content))
        text_parts = [p.text for p in document.paragraphs]

        for table in document.tables:
            for row in table.rows:
                text_parts.append(
                    " | ".join(cell.text for cell in row.cells)
                )

        # Word files do not reliably store fixed page boundaries.
        pages = [(1, "\n".join(text_parts))]

    elif suffix in {".md", ".txt"}:
        pages = [(1, content.decode("utf-8-sig"))]

    else:
        raise ValueError(
            "Supported formats: PDF, PPTX, DOCX, TXT and Markdown."
        )

    if not any(text.strip() for _, text in pages):
        raise ValueError(
            "No readable text was found in this document."
        )

    return pages


def chunk_document(
    name: str,
    content: bytes,
    size: int = 180,
    overlap: int = 35,
) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError(
            "Chunk overlap must be smaller than the chunk size"
        )

    chunks = []

    for page, text in parse_document(name, content):
        words = re.sub(r"[ \t]+", " ", text).split()

        for start in range(0, len(words), size - overlap):
            passage = " ".join(words[start:start + size])
            identity = f"{name}:{page}:{start}:{passage}"

            chunks.append(
                Chunk(
                    hashlib.sha256(identity.encode()).hexdigest()[:16],
                    name,
                    page,
                    passage,
                )
            )

            if start + size >= len(words):
                break

    return chunks


def load_documents(directory: Path) -> tuple[list[Chunk], list[dict]]:
    chunks = []
    warnings = []

    for path in sorted(directory.glob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                chunks.extend(
                    chunk_document(path.name, path.read_bytes())
                )
            except Exception as error:
                warnings.append(
                    {"source": path.name, "error": str(error)}
                )

    return chunks, warnings