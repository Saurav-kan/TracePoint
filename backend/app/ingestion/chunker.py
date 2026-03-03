"""Document parsing and chunking via Docling."""
from pathlib import Path
from typing import List

from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
import tiktoken

from app.config import CHUNK_SIZE


def _get_chunker() -> HybridChunker:
    """Build HybridChunker with tiktoken (aligned with embedding model token limits)."""
    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.encoding_for_model("gpt-4"),
        max_tokens=CHUNK_SIZE,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def load_document(source: str | Path, *, is_text: bool = False):
    """Load a document into DoclingDocument.

    Args:
        source: File path or raw text string.
        is_text: If True, treat source as raw text; else treat as file path.

    Returns:
        DoclingDocument.
    """
    converter = DocumentConverter()
    if is_text:
        result = converter.convert_string(str(source), format=InputFormat.MD)
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        # .txt not natively supported; wrap as markdown
        if path.suffix.lower() == ".txt":
            content = path.read_text(encoding="utf-8", errors="replace")
            result = converter.convert_string(content, format=InputFormat.MD)
        else:
            result = converter.convert(path)
    return result.document


def chunk_document(doc) -> List[str]:
    """Chunk a DoclingDocument using HybridChunker.

    Uses contextualize() for metadata-enriched text (headers, captions).

    Args:
        doc: DoclingDocument from load_document().

    Returns:
        List of chunk strings ready for embedding.
    """
    chunker = _get_chunker()
    chunks = []
    for chunk in chunker.chunk(dl_doc=doc):
        text = chunker.contextualize(chunk=chunk)
        if text.strip():
            chunks.append(text.strip())
    return chunks


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: float | None = None,
) -> List[str]:
    """Chunk raw text (backward-compatible interface).

    Wraps text as Markdown and uses Docling's HybridChunker.

    Args:
        text: Raw document text.
        chunk_size: Ignored (Docling uses config CHUNK_SIZE).
        overlap: Ignored (HybridChunker uses merge/split logic).

    Returns:
        List of chunk strings.
    """
    doc = load_document(text, is_text=True)
    return chunk_document(doc)


def chunk_file(file_path: str | Path) -> List[str]:
    """Chunk a document file (PDF, DOCX, images, Markdown, etc.).

    Args:
        file_path: Path to the document.

    Returns:
        List of chunk strings.
    """
    doc = load_document(file_path, is_text=False)
    return chunk_document(doc)
