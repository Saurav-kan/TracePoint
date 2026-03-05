/**
 * API client and label mapping for TracePoint backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Display labels shown in the UI */
export const LABELS = [
  "Forensic Log",
  "Interview Transcript",
  "Physical Evidence",
  "Ransom Note",
  "Open Source Intelligence",
] as const;

/** Map frontend display labels to backend snake_case labels */
export const LABEL_TO_BACKEND: Record<string, string> = {
  "Forensic Log": "forensic_log",
  "Interview Transcript": "security_interview",
  "Physical Evidence": "physical",
  "Ransom Note": "ransom_note",
  "Open Source Intelligence": "osint",
};

export function toBackendLabel(displayLabel: string): string {
  return LABEL_TO_BACKEND[displayLabel] ?? "forensic_log";
}

// --- API types (aligned with backend schemas) ---

export interface CaseCreateResponse {
  case_id: string;
  status: string;
}

export interface IngestResponse {
  case_id: string;
  chunks_created: number;
}

export interface EvidenceSummary {
  label: string;
  source_document: string | null;
  reliability: number;
  summary: string;
}

export interface CaseDetailResponse {
  case_id: string;
  title: string;
  brief: string;
  status: string;
  evidence: EvidenceSummary[];
}

export interface JudgeTaskFact {
  description: string;
  supports_claim: boolean;
  source_task_index: number;
  evidence_indices: number[];
}

export interface JudgeTaskAssessment {
  question_text: string;
  answer: string;
  sufficient_evidence: boolean;
  confidence?: number;
  key_facts: JudgeTaskFact[];
  notes?: string;
}

export interface JudgeOverallVerdict {
  claim: string;
  verdict: "true" | "likely_true" | "uncertain" | "likely_false" | "false";
  rationale: string;
  supporting_facts: JudgeTaskFact[];
  contradicting_facts: JudgeTaskFact[];
}

export interface JudgeResponse {
  case_id: string;
  fact_to_check: string;
  tasks: JudgeTaskAssessment[];
  overall_verdict: JudgeOverallVerdict;
  refinement_performed?: boolean;
  refinement_suggestion?: string;
}

// --- API functions ---

export async function createCase(
  title: string,
  caseBriefText: string
): Promise<CaseCreateResponse> {
  const res = await fetch(`${API_BASE}/cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      case_brief_text: caseBriefText,
      status: "active",
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `createCase failed: ${res.status}`);
  }
  return res.json();
}

export async function ingestFile(
  file: File,
  label: string,
  caseId: string
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("label", label);
  form.append("case_id", caseId);

  const res = await fetch(`${API_BASE}/ingest/file`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `ingestFile failed: ${res.status}`);
  }
  return res.json();
}

export async function runWorkflow(
  caseId: string,
  factToCheck: string
): Promise<JudgeResponse> {
  const res = await fetch(`${API_BASE}/workflow/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      case_id: caseId,
      fact_to_check: factToCheck,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `runWorkflow failed: ${res.status}`);
  }
  return res.json();
}

export async function getCase(caseId: string): Promise<CaseDetailResponse> {
  const res = await fetch(`${API_BASE}/cases/${caseId}`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `getCase failed: ${res.status}`);
  }
  return res.json();
}
