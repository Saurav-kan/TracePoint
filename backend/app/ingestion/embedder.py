"""Gemini-based embeddings for evidence chunks."""
from typing import List

from google import genai
from google.genai import types

from app.config import EMBEDDING_DIM, EMBEDDING_MODEL, GOOGLE_API_KEY

BATCH_SIZE = 100


def _get_client() -> genai.Client:
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is required for embeddings. Set it in .env or environment."
        )
    return genai.Client(api_key=GOOGLE_API_KEY)


def embed_texts(texts: List[str], model: str | None = None) -> List[List[float]]:
    """Embed a list of text chunks using Gemini.

    Args:
        texts: List of chunk strings.
        model: Override embedding model (default from config).

    Returns:
        List of embedding vectors (each a list of floats).
    """
    if not texts:
        return []
    client = _get_client()
    m = model or EMBEDDING_MODEL
    all_embeddings: List[List[float]] = []
    try:
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            result = client.models.embed_content(
                model=m,
                contents=batch,
                config=types.EmbedContentConfig(
                    output_dimensionality=EMBEDDING_DIM,
                ),
            )
            for emb in result.embeddings:
                vec = emb.values if hasattr(emb, "values") else emb
                all_embeddings.append(list(vec) if not isinstance(vec, list) else vec)
    finally:
        client.close()
    return all_embeddings
