/**
 * API client and label mapping for TracePoint backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Display labels shown in the UI */
export const LABELS = [
  "Forensic Log",
  "Interview Transcript",
  "Witness Statement",
  "Physical Evidence",
  "Access Log",
  "Network Log",
  "Sensor Data",
  "Surveillance",
  "HR Record",
  "Financial Record",
  "Maintenance Log",
  "Communications",
  "Ransom Note",
  "Open Source Intelligence",
  "Administrative",
] as const;

/** Map frontend display labels to backend snake_case labels */
export const LABEL_TO_BACKEND: Record<string, string> = {
  "Forensic Log": "forensic_log",
  "Interview Transcript": "security_interview",
  "Witness Statement": "witness_statement",
  "Physical Evidence": "physical",
  "Access Log": "access_log",
  "Network Log": "network_log",
  "Sensor Data": "sensor_data",
  "Surveillance": "surveillance",
  "HR Record": "hr_record",
  "Financial Record": "financial_record",
  "Maintenance Log": "maintenance_log",
  "Communications": "communications",
  "Ransom Note": "ransom_note",
  "Open Source Intelligence": "osint",
  "Administrative": "administrative",
};

export function toBackendLabel(displayLabel: string): string {
  const mapped = LABEL_TO_BACKEND[displayLabel];
  if (mapped !== undefined) return mapped;
  // Pass through unmapped labels (e.g. from evidence clerk returning labels
  // outside our 15, or backend labels shown via toDisplayLabel fallback).
  // Silently converting to "forensic_log" would lose the user's selection.
  return displayLabel;
}


// ---------------------------------------------------------------------------
// Shared API types (aligned with backend schemas)
// ---------------------------------------------------------------------------

export type EffortLevel = "standard" | "adversarial" | "deep" | "proof";

export type VerdictLabel =
  | "true"
  | "likely_true"
  | "uncertain"
  | "likely_false"
  | "false";

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

export interface CaseBriefResponse {
  id: number;
  case_id: string;
  title: string;
  brief_text: string;
  source_file: string | null;
  created_at: string;
}

// --- Planner types ---

export interface MetadataFilterItem {
  key: string;
  value: string;
}

export interface PlannerTask {
  type: string;
  question_text: string;
  vector_query: string;
  metadata_filter: MetadataFilterItem[];
}

export interface FrictionSummary {
  has_friction: boolean;
  description: string | null;
}

export interface PlannerResponse {
  case_id: string;
  fact_to_check: string;
  friction_summary: FrictionSummary;
  tasks: PlannerTask[];
}

// --- Gatekeeper types ---

export interface GatekeeperResult {
  valid: boolean;
  reasons: string[];
  needs_regeneration: boolean;
}

// --- Research types ---

export interface EvidenceSnippet {
  source_document: string | null;
  case_id: string | null;
  score: number;
  chunk_before: string | null;
  chunk: string;
  chunk_after: string | null;
}

export interface ResearchTaskResult {
  question_text: string;
  vector_query: string;
  metadata_filter: MetadataFilterItem[];
  evidence: EvidenceSnippet[];
}

export interface ResearchResponse {
  case_id: string;
  fact_to_check: string;
  tasks: ResearchTaskResult[];
}

// --- Judge types ---

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
  verdict: VerdictLabel;
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
  needs_refinement?: boolean;
  gatekeeper_passed?: boolean;
  gatekeeper_reasons?: string[];
}

// --- Workflow types ---

export interface PipelineStepEvent {
  step: string;
  status: "running" | "complete";
  iteration: number;
  total_iterations: number;
  progress?: string;
  data?: Record<string, unknown>;
}

export interface IterationResult {
  iteration: number;
  planner: PlannerResponse;
  gatekeeper: GatekeeperResult;
  research: ResearchResponse;
  judge: JudgeResponse;
}

export interface ProofTestResult {
  validated_supporting: JudgeTaskFact[];
  validated_contradicting: JudgeTaskFact[];
  invalidated_supporting: unknown[];
  invalidated_contradicting: unknown[];
  replacements: JudgeTaskFact[];
  adjusted_verdict: Record<string, unknown>;
}

export interface ReconciliationResponse {
  case_id: string;
  verdict: VerdictLabel;
  rationale: string;
  supporting_facts: JudgeTaskFact[];
  contradicting_facts: JudgeTaskFact[];
}

export interface WorkflowResponse {
  log_id: number;
  effort_level: EffortLevel;
  iterations: IterationResult[];
  final_verdict: JudgeResponse | ReconciliationResponse;
  proof_test_result?: ProofTestResult | null;
}

export interface InvestigationLogSummary {
  id: number;
  claim: string;
  effort_level: EffortLevel | string;
  verdict: string;
  created_at: string;
}

export interface EvidenceDocumentResponse {
  source_document: string;
  content: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

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

// --- Auto-label types ---

export interface LabelScoreItem {
  label: string;
  score: number;
}

export interface AutoLabelResponse {
  suggested_labels: string[];
  all_scores: LabelScoreItem[];
  clerk: {
    summary: string;
    parties: string[];
    locations: string[];
    times: string[];
    evidence_type: string | null;
    confidence: number;
    label_scores: LabelScoreItem[];
  };
}

/** Map backend snake_case labels to frontend display labels */
const BACKEND_TO_LABEL: Record<string, string> = Object.fromEntries(
  Object.entries(LABEL_TO_BACKEND).map(([display, backend]) => [backend, display])
);

export function toDisplayLabel(backendLabel: string): string {
  return BACKEND_TO_LABEL[backendLabel] ?? backendLabel;
}

/** Auto-label a file by sending it to the evidence clerk for scoring. */
export async function autoLabelFile(file: File): Promise<AutoLabelResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/ingest/auto-label`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `autoLabelFile failed: ${res.status}`);
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

/** Legacy synchronous workflow (kept for backward compatibility) */
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

/**
 * SSE streaming workflow. Calls POST /workflow/run-stream and invokes
 * callbacks as events arrive.
 *
 * Returns an AbortController so the caller can cancel the stream.
 */
export function runWorkflowStream(
  caseId: string,
  factToCheck: string,
  options: {
    briefId?: number;
    effortLevel?: EffortLevel;
    onStep?: (event: PipelineStepEvent) => void;
    onDone?: (data: { log_id: number; data: WorkflowResponse }) => void;
    onError?: (error: Error) => void;
  } = {}
): AbortController {
  const controller = new AbortController();
  const { briefId, effortLevel = "standard", onStep, onDone, onError } = options;

  const body: Record<string, unknown> = {
    case_id: caseId,
    fact_to_check: factToCheck,
    effort_level: effortLevel,
  };
  if (briefId != null) body.brief_id = briefId;

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/workflow/run-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || `runWorkflowStream failed: ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No readable stream");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            try {
              const parsed = JSON.parse(jsonStr);
              if (currentEventType === "step") {
                onStep?.(parsed as PipelineStepEvent);
              } else if (currentEventType === "done") {
                onDone?.(parsed);
              } else if (currentEventType === "error") {
                onError?.(new Error(parsed.detail ?? "Pipeline error"));
              }
            } catch {
              /* skip malformed JSON lines */
            }
            currentEventType = "";
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        onError?.(e instanceof Error ? e : new Error(String(e)));
      }
    }
  })();

  return controller;
}

// --- Investigation log endpoints ---

export async function listInvestigationLogs(
  caseId: string
): Promise<InvestigationLogSummary[]> {
  const res = await fetch(`${API_BASE}/workflow/logs/${caseId}`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `listInvestigationLogs failed: ${res.status}`);
  }
  return res.json();
}

export async function getInvestigationLog(
  caseId: string,
  logId: number
): Promise<WorkflowResponse> {
  const res = await fetch(`${API_BASE}/workflow/logs/${caseId}/${logId}`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `getInvestigationLog failed: ${res.status}`);
  }
  return res.json();
}

// --- Evidence document endpoint ---

export async function getEvidenceDocument(
  caseId: string,
  sourceDocument: string
): Promise<EvidenceDocumentResponse> {
  const res = await fetch(
    `${API_BASE}/ingest/document/${caseId}/${encodeURIComponent(sourceDocument)}`
  );
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `getEvidenceDocument failed: ${res.status}`);
  }
  return res.json();
}

// --- Brief endpoints ---

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

export async function updateBrief(
  caseId: string,
  briefId: number,
  payload: { title?: string; brief_text?: string }
): Promise<CaseBriefResponse> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/briefs/${briefId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `updateBrief failed: ${res.status}`);
  }
  return res.json();
}

export async function deleteBrief(
  caseId: string,
  briefId: number
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/cases/${caseId}/briefs/${briefId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `deleteBrief failed: ${res.status}`);
  }
  return res.json();
}
