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
    could independently confirm or disconfirm the claim?" Always distinguish
    between WHO DID access/act (physical evidence: logs showing who badged in,
    device fingerprints, biometrics) vs WHO COULD or SHOULD have accessed the
    system (authorization / role). Probe the former, not the latter. Examples:
    access-control logs showing who physically badged in, device logs showing
    who used a system, GPS traces, receipts, digital events tied to a specific
    human body — not just to an account name.
    """
).strip()


IMPOSSIBILITY_TEMPLATE = dedent(
    """
    IMPOSSIBILITY questions ask: "What evidence could prove that the claim
    cannot be true at the same time as other known facts?" Examples include
    mutually exclusive locations or times, closed hours, or resource limits
    that make the claim impossible. Crucially, always ask for physical trait
    logs (elevator loads, height measurements) and CROSS-REFERENCE them with
    the suspect's recorded physical profile in HR records to spot framing.
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


PHYSICAL_ARTIFACT_AUTHORSHIP_TEMPLATE = dedent(
    """
    PHYSICAL_ARTIFACT_AUTHORSHIP (use type VERIFICATION): Questions that ask
    "What forensic traces on the specific physical instrument of the crime
    (e.g., USB drive, weapon, device) identify who handled or created it?"
    Target: fingerprints, DNA, embedded code strings (ownership tags, developer
    signatures like 'property_of_X'), device serial numbers linked to a person.
    This evidence is near-conclusive and outweighs credential-based inferences.
    Always use type VERIFICATION for physical-artifact tasks — this is a guideline
    for designing VERIFICATION tasks, not a separate task type.
    """
).strip()


ALL_TEMPLATES = {
    "VERIFICATION": VERIFICATION_TEMPLATE,
    "IMPOSSIBILITY": IMPOSSIBILITY_TEMPLATE,
    "ENVIRONMENTAL": ENVIRONMENTAL_TEMPLATE,
    "NEGATIVE_PROOF": NEGATIVE_PROOF_TEMPLATE,
    "RECALL_STRESS": RECALL_STRESS_TEMPLATE,
    "PHYSICAL_ARTIFACT_AUTHORSHIP": PHYSICAL_ARTIFACT_AUTHORSHIP_TEMPLATE,
}
