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
  created_at: string;
  evidence: EvidenceSummary[];
}

export interface CaseSummaryResponse {
  case_id: string;
  title: string;
  status: string;
  created_at: string;
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

export interface CaseBriefResponse {
  id: number;
  case_id: string;
  title: string;
  brief_text: string;
  source_file: string | null;
  created_at: string;
}

export async function runWorkflow(
  caseId: string,
  factToCheck: string,
  briefId?: number
): Promise<JudgeResponse> {
  const body: { case_id: string; fact_to_check: string; brief_id?: number } = {
    case_id: caseId,
    fact_to_check: factToCheck,
  };
  if (briefId != null) body.brief_id = briefId;

  const res = await fetch(`${API_BASE}/workflow/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `runWorkflow failed: ${res.status}`);
  }
  return res.json();
}

export async function listBriefs(caseId: string): Promise<CaseBriefResponse[]> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/briefs`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `listBriefs failed: ${res.status}`);
  }
  return res.json();
}

export async function addBrief(
  caseId: string,
  options: { title?: string; briefText?: string; file?: File }
): Promise<CaseBriefResponse> {
  const form = new FormData();
  if (options.title) form.append("title", options.title);
  if (options.briefText) form.append("brief_text", options.briefText);
  if (options.file) form.append("file", options.file);

  const res = await fetch(`${API_BASE}/cases/${caseId}/briefs`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `addBrief failed: ${res.status}`);
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

export async function listCases(): Promise<CaseSummaryResponse[]> {
  const res = await fetch(`${API_BASE}/cases`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `listCases failed: ${res.status}`);
  }
  return res.json();
}

export async function updateCaseBrief(
  caseId: string,
  brief: string
): Promise<CaseDetailResponse> {
  const res = await fetch(`${API_BASE}/cases/${caseId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_brief_text: brief }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `updateCaseBrief failed: ${res.status}`);
  }
  return res.json();
}
