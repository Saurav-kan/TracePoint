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

# Model choices
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gemini-3.0")
FRICTION_MODEL = os.getenv("FRICTION_MODEL", "gemini-3.0-flash")
EVIDENCE_CLERK_MODEL = os.getenv("EVIDENCE_CLERK_MODEL", "gemini-3.0-flash")

# OpenAI configuration (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_PLANNER_MODEL = os.getenv("OPENAI_PLANNER_MODEL", "gpt-4.1-mini")

# Groq configuration (optional, OpenAI-compatible API)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_PLANNER_MODEL = os.getenv("GROQ_PLANNER_MODEL", "gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# Provider switches
# PLANNER_PROVIDER can be: "gemini" (default), "openai", or "groq"
PLANNER_PROVIDER = os.getenv("PLANNER_PROVIDER", "gemini").lower()
