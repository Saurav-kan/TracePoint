# TracePoint Project Truth

This document is the canonical, implementation-grounded reference for what TracePoint currently is, how it works, and where it should evolve.

## 1) Product Truth

- **Purpose:** TracePoint is a claim-verification system for investigations that checks a user-provided claim against ingested evidence.
- **Core interaction:** User creates a case, ingests evidence files, asks a claim/question, and receives a structured verdict with supporting and contradicting facts.
- **Primary mode:** Multi-pass, cyclic investigation (`planner -> gatekeeper -> research -> judge`) with optional refinement loops.

## 2) Current Architecture Truth

### Frontend (`frontend/`)

- Next.js app with case creation, evidence upload, auto-label assistance, claim verification, and a detailed case workspace UI.
- Uses streaming workflow endpoint to display step-by-step pipeline updates and final verdict.
- Supports investigation history and source-document drill-down.

### Backend (`backend/`)

- FastAPI API server with routers for:
  - `cases`
  - `ingest`
  - `planner`
  - `workflow`
- LangGraph-based cyclic workflow compiled in backend graph module.
- Agent modules:
  - Planner agent (task generation)
  - Gatekeeper (planner output validation)
  - Research agent (vector retrieval)
  - Judge agent (task assessment + final verdict synthesis)
  - Friction detector (claim/brief inconsistency signal)

### Database (`database/`, SQLAlchemy models)

- PostgreSQL + pgvector.
- Main entities:
  - `cases`
  - `case_briefs`
  - `evidence_chunks`
  - `investigation_logs`
- Evidence includes embeddings, reliability score, labels, metadata JSON, and source document linkage.

## 3) Workflow Truth (As Implemented)

1. **Case setup**
   - Case record is created with case brief text.
2. **Evidence ingestion**
   - Files/text are parsed/chunked, embedded, labeled, and persisted as evidence chunks.
3. **Planner pass**
   - Planner generates tasks:
     - Main pass expects exactly 10 tasks.
     - First half confirmational, second half disconfirming.
   - Friction summary from case brief vs claim is injected into planning context.
4. **Gatekeeper validation**
   - Enforces schema and quality checks (task count, type coverage, metadata filters, non-confirmational balance, friction targeting).
   - Invalid output triggers planner retry (main pass only).
5. **Research retrieval**
   - Embeds each task query and runs vector similarity retrieval in pgvector.
   - Applies case/time/metadata filters; returns snippets with neighboring chunk context.
6. **Judge synthesis**
   - Per-task assessment + overall verdict.
   - Returns `needs_refinement` and up to three `refinement_questions`.
7. **Cyclic refinement**
   - If refinement needed and iteration budget remains, planner runs in refinement mode (1-3 supplemental tasks), then research/judge rerun.
8. **Persistence + streaming**
   - Streaming endpoint emits step events.
   - Full workflow result is stored in `investigation_logs`.

## 4) Prompt and Reasoning Guardrail Truth

### Planner prompt behavior

- Strongly enforces balanced confirming/disconfirming task generation.
- Explicitly warns against confusing credential ownership with physical action.
- Encourages objective signals (forensics/logs/physical traces) over subjective recall.
- Requires structured metadata filters, ideally by clerk-extracted `evidence_type`.

### Judge prompt behavior

- Uses explicit evidence hierarchy (physical authorship > physical placement > digital > credential > testimony).
- Includes anti-pitfall rules:
  - Authorization is not proof of action.
  - Credential events are not actor identity proof.
  - Verdict must match rationale and claim literal wording.
  - Outliers should be flagged, not discarded.
- Supports refinement decisioning for unresolved questions.

## 5) Known Strengths

- **Cyclic architecture:** Better than one-shot pipelines for uncertain or sparse evidence conditions.
- **Bias countermeasure:** Disconfirming-task requirement reduces pure confirmation-bias planning.
- **Operational transparency:** Step-level streaming lets users inspect planner/research/judge behavior.
- **Traceability:** Persisted investigation logs and source snippets support auditability.
- **Case-scoped retrieval constraints:** Metadata/time filtering helps reduce cross-case retrieval noise.

## 6) Current Constraints and Risks

- **Domain overfitting risk:** Prompts and heuristics are currently tuned toward law-enforcement-style scenarios.
- **Heuristic fallback quality gap:** Non-LLM judge path is simplistic and may over-credit retrieved evidence.
- **Retrieval fragility:** Heavy dependence on embedding quality and metadata labeling correctness.
- **Limited adversarial robustness:** No dedicated deception/manipulation classifier for planted or staged evidence patterns.
- **Evidence reliability underused:** Reliability scores exist in data model, but not fully integrated into final probabilistic verdict aggregation.
- **Single-claim framing:** Workflow optimizes for one claim at a time, not a graph of interdependent hypotheses.

## 7) Improvements to Make TracePoint More Generally Applicable

## A) Generalization beyond investigative niche

- Introduce **domain profiles** (investigation, compliance, medical review, incident response, audit) that swap prompt packs, evidence weighting priors, and task archetypes.
- Move hard-coded prompt assumptions into a **versioned policy config** (`yaml/json`) loaded per domain.
- Add configurable output schemas so users can request verdicts as:
  - binary decision
  - risk score
  - uncertainty interval
  - ranked hypotheses.

## B) Better handling of complex logic and multi-hop reasoning

- Add a **hypothesis graph layer** where claims, subclaims, and counterclaims are explicit nodes with dependency edges.
- Require judge to emit **claim decomposition proofs** (which subclaims drove verdict and with what confidence).
- Add temporal/causal consistency checks:
  - event ordering contradictions
  - impossible co-occurrence
  - missing prerequisite event detection.

## C) Stronger defense against reasoning pitfalls

- Add explicit checks for:
  - base-rate neglect
  - anchoring on first high-salience evidence
  - single-source overreliance
  - narrative fallacy (coherent story unsupported by data).
- Add a dedicated **red-team challenger pass** that tries to falsify the current verdict before finalization.
- Require minimum source diversity before high-confidence verdicts.

## D) Evidence bias and adversarial-trick resistance

- Integrate **source provenance scoring** (chain-of-custody confidence, tamper indicators, source authenticity).
- Add adversarial-pattern detectors:
  - staged corroboration
  - synchronized fabricated logs
  - credential-framing signatures
  - selective data omission patterns.
- Introduce contradiction clustering to detect when many weakly independent sources may actually stem from one manipulated origin.

## E) Quantitative confidence and calibration upgrades

- Replace mostly qualitative confidence with **calibrated confidence model** (historical outcomes + reliability features).
- Combine retrieval score, source reliability, contradiction severity, and evidence diversity into a normalized confidence function.
- Maintain post-deployment calibration metrics (Brier score, reliability curves) to prevent confidence drift.

## F) Operational and product improvements

- Add explicit "insufficient evidence" UX state with action checklist:
  - what evidence is missing
  - what to collect next
  - expected impact on verdict.
- Introduce workflow replay/debug mode with deterministic seeds for prompt experimentation.
- Add benchmark suites with adversarial cases and trap scenarios to track regression on reasoning quality.

## 8) Implementation Priorities (Suggested)

1. **Short term:** Externalize prompts/policies by domain + add challenger pass + source diversity checks.
2. **Medium term:** Add hypothesis graph + temporal/causal consistency validators.
3. **Long term:** Add calibrated probabilistic scoring and continuous evaluation against adversarial benchmark cases.

## 9) Definition of Truth Maintenance

This file should be updated whenever any of the following changes:

- Workflow topology or loop conditions
- Prompt contracts or reasoning rules
- Evidence scoring/weighting logic
- API contracts for workflow outputs
- Domain assumptions and supported use cases

When architecture docs and implementation diverge, implementation wins until docs are updated.
