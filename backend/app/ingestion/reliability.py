"""Reliability scoring based on evidence type (label)."""
from typing import Dict

# Label -> reliability score (0-1). Labels normalized to lowercase with underscores.
LABEL_RELIABILITY_MAP: Dict[str, float] = {
    # Police/digital static data (0.95)
    "gps": 0.95,
    "cad": 0.95,
    "body_cam": 0.95,
    "digital_log": 0.95,
    "weather": 0.95,
    "metadata": 0.95,
    # Physical evidence (0.90)
    "receipt": 0.90,
    "badge_swipe": 0.90,
    "forensic": 0.90,
    "physical": 0.90,
    # Third-party accounts (0.70)
    "third_party": 0.70,
    "witness": 0.70,
    "bystander": 0.70,
    # Invested party (0.55)
    "suspect": 0.55,
    "alibi": 0.55,
    "interested_party": 0.55,
}

DEFAULT_RELIABILITY = 0.50


def get_reliability_score(label: str) -> float:
    """Return reliability score (0-1) for the given evidence label.

    Args:
        label: Evidence type (e.g., 'witness', 'gps', 'alibi').

    Returns:
        Score between 0 and 1.
    """
    if not label or not isinstance(label, str):
        return DEFAULT_RELIABILITY
    normalized = label.strip().lower().replace("-", "_").replace(" ", "_")
    return LABEL_RELIABILITY_MAP.get(normalized, DEFAULT_RELIABILITY)
