"""Application configuration loaded from environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load from backend/.env when running from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)
load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://tracepoint:tracepoint_dev@localhost:5432/tracepoint",
)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEY2 = os.getenv("GOOGLE_API_KEY2", "")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = float(os.getenv("CHUNK_OVERLAP", "0.1"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EVIDENCE_CLERK_MODEL = os.getenv("EVIDENCE_CLERK_MODEL", "gemini-3.0-flash-lite")
