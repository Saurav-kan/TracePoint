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
EVIDENCE_CLERK_PROVIDER = os.getenv("EVIDENCE_CLERK_PROVIDER", "gemini").lower()
EVIDENCE_CLERK_MODEL = os.getenv("EVIDENCE_CLERK_MODEL", "gemini-3.0-flash")
SILICONFLOW_EVIDENCE_CLERK_MODEL = os.getenv("SILICONFLOW_EVIDENCE_CLERK_MODEL", "Qwen/Qwen2.5-7B-Instruct")

# OpenAI configuration (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_PLANNER_MODEL = os.getenv("OPENAI_PLANNER_MODEL", "gpt-4.1-mini")

# Groq configuration (optional, OpenAI-compatible API)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_PLANNER_MODEL = os.getenv("GROQ_PLANNER_MODEL", "gpt-oss-120b")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# Research agent configuration
RESEARCH_TIME_FILTER_ENABLED = (
    os.getenv("RESEARCH_TIME_FILTER_ENABLED", "false").lower() == "true"
)
RESEARCH_METADATA_FILTER_ENABLED = (
    os.getenv("RESEARCH_METADATA_FILTER_ENABLED", "false").lower() == "true"
)
RESEARCH_DISTANCE_METRIC = os.getenv("RESEARCH_DISTANCE_METRIC", "cosine").lower()
if RESEARCH_DISTANCE_METRIC not in {"cosine", "l2"}:
    RESEARCH_DISTANCE_METRIC = "cosine"
RESEARCH_TOP_K = int(os.getenv("RESEARCH_TOP_K", "5"))

# Provider switches
# PLANNER_PROVIDER can be: "gemini" (default), "openai", or "groq"
PLANNER_PROVIDER = os.getenv("PLANNER_PROVIDER", "gemini").lower()

# Judge agent configuration
# JUDGE_PROVIDER: "groq" | "siliconflow" | "none" (none = heuristic only, no LLM)
JUDGE_PROVIDER = os.getenv("JUDGE_PROVIDER", "groq").lower()
# Groq judge (reuses GROQ_API_KEY, GROQ_BASE_URL from planner)
GROQ_JUDGE_MODEL = os.getenv("GROQ_JUDGE_MODEL", "gpt-oss-120b")
# SiliconFlow judge (OpenAI-compatible API)
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv(
    "SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"
)
SILICONFLOW_JUDGE_MODEL = os.getenv(
    "SILICONFLOW_JUDGE_MODEL", "Qwen/Qwen3-VL-30B-A3B-Thinking"
)
# If true, final verdict LLM sees raw evidence chunks; if false, only sub-answers
JUDGE_FINAL_VIEW_CHUNKS = (
    os.getenv("JUDGE_FINAL_VIEW_CHUNKS", "false").lower() == "true"
)
# If true, require every key_fact to have at least one valid evidence_indices entry
JUDGE_GATEKEEPER_STRICT_LINKING = (
    os.getenv("JUDGE_GATEKEEPER_STRICT_LINKING", "false").lower() == "true"
)
# Max judge retries when gatekeeper fails
JUDGE_GATEKEEPER_RETRY_COUNT = int(os.getenv("JUDGE_GATEKEEPER_RETRY_COUNT", "2"))

# Default evidence labels used when a case has no ingested evidence yet.
# These provide a small global taxonomy for the planner to fall back on.
DEFAULT_EVIDENCE_LABELS = [
    "forensic_log",
    "security_interview",
    "witness_statement",
    "physical",
    "access_log",
    "network_log",
    "sensor_data",
    "surveillance",
    "hr_record",
    "financial_record",
    "maintenance_log",
    "communications",
    "ransom_note",
    "osint",
    "administrative",
]
