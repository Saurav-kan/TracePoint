"""Canonical planner question archetypes.

These templates are used in the planner system prompt so that the
model generalizes each category (verification, impossibility,
environmental, negative proof, recall-stress) to any fact-checking
domain.
"""
from textwrap import dedent


VERIFICATION_TEMPLATE = dedent(
    """
    VERIFICATION questions ask: "What direct records, artifacts, or logs
    could independently confirm or disconfirm the claim?" Examples include
    device logs, receipts, access-control entries, GPS traces, and digital
    system events.
    """
).strip()


IMPOSSIBILITY_TEMPLATE = dedent(
    """
    IMPOSSIBILITY questions ask: "What evidence could prove that the claim
    cannot be true at the same time as other known facts?" Examples include
    mutually exclusive locations or times, closed hours, or resource limits
    that make the claim impossible.
    """
).strip()


ENVIRONMENTAL_TEMPLATE = dedent(
    """
    ENVIRONMENTAL questions ask: "What surrounding conditions should match
    if the claim is true?" This covers weather, lighting, layout, traffic,
    crowd size, background sounds, or other context that leaves traces in
    logs, images, or reports.
    """
).strip()


NEGATIVE_PROOF_TEMPLATE = dedent(
    """
    NEGATIVE_PROOF questions ask: "What should exist if the claim were true,
    but appears to be missing?" Examples include missing access logs,
    missing alerts, or the absence of routine records that would normally
    be created by the claimed event.
    """
).strip()


RECALL_STRESS_TEMPLATE = dedent(
    """
    RECALL_STRESS questions ask: "Which peripheral details around the claim
    would be hard to fabricate consistently under stress?" Examples include
    minor objects, peripheral people, background conversations, smells, or
    side-events that genuine witnesses remember but fabricators often omit
    or contradict.
    """
).strip()


ALL_TEMPLATES = {
    "VERIFICATION": VERIFICATION_TEMPLATE,
    "IMPOSSIBILITY": IMPOSSIBILITY_TEMPLATE,
    "ENVIRONMENTAL": ENVIRONMENTAL_TEMPLATE,
    "NEGATIVE_PROOF": NEGATIVE_PROOF_TEMPLATE,
    "RECALL_STRESS": RECALL_STRESS_TEMPLATE,
}
