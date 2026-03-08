"use client";

import {
  getCase,
  runWorkflowStream,
  listBriefs,
  addBrief,
  updateBrief,
  deleteBrief,
  listInvestigationLogs,
  getInvestigationLog,
  getEvidenceDocument,
  type CaseBriefResponse,
  type CaseDetailResponse,
  type JudgeResponse,
  type PipelineStepEvent,
  type WorkflowResponse,
  type InvestigationLogSummary,
  type EffortLevel,
  type PlannerResponse,
  type GatekeeperResult,
  type ResearchResponse,
  type EvidenceDocumentResponse,
} from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, useRef } from "react";

// ---------------------------------------------------------------------------
// Effort level config
// ---------------------------------------------------------------------------

const EFFORT_OPTIONS: {
  value: EffortLevel;
  label: string;
  desc: string;
}[] = [
  { value: "low", label: "LOW", desc: "Single pass" },
  { value: "medium", label: "MED", desc: "2× compare" },
  { value: "high", label: "HIGH", desc: "3× deep" },
];

// ---------------------------------------------------------------------------
// Verdict badge helper
// ---------------------------------------------------------------------------

function verdictColor(v?: string) {
  if (!v) return "bg-zinc-800 text-zinc-400 border-zinc-700";
  if (v === "true" || v === "likely_true")
    return "bg-success/10 text-success border-success/20";
  if (v === "false" || v === "likely_false")
    return "bg-danger/10 text-danger border-danger/20";
  return "bg-warning/10 text-warning border-warning/20";
}

function verdictLabel(v?: string) {
  return v?.toUpperCase().replace("_", " ") ?? "—";
}

// ---------------------------------------------------------------------------
// Skeleton placeholder
// ---------------------------------------------------------------------------

function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3 py-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="skeleton-line"
          style={{ width: `${70 + Math.random() * 30}%` }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline step wrapper
// ---------------------------------------------------------------------------

function PipelineCard({
  title,
  icon,
  status,
  children,
}: {
  title: string;
  icon: string;
  status: "pending" | "running" | "complete";
  children: React.ReactNode;
}) {
  return (
    <div className="pipeline-step" data-status={status}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">{icon}</span>
          <h4 className="text-xs font-mono font-bold text-zinc-300 uppercase tracking-widest">
            {title}
          </h4>
        </div>
        <span
          className={`text-[10px] font-mono font-semibold uppercase tracking-wider ${
            status === "complete"
              ? "text-success"
              : status === "running"
                ? "text-accent pulse-glow"
                : "text-zinc-600"
          }`}
        >
          {status === "complete" ? "✓ Done" : status === "running" ? "⟳ Running…" : "⏳ Waiting"}
        </span>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source Document Viewer (slide-over)
// ---------------------------------------------------------------------------

function SourceViewer({
  doc,
  onClose,
}: {
  doc: EvidenceDocumentResponse | null;
  onClose: () => void;
}) {
  if (!doc) return null;
  return (
    <>
      <div
        className="slide-over-backdrop"
        data-open="true"
        onClick={onClose}
      />
      <div className="slide-over-panel custom-scrollbar" data-open="true">
        <div className="sticky top-0 bg-[#0f172a] border-b border-zinc-800 px-6 py-4 flex justify-between items-center z-10">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">
              {doc.source_document}
            </h3>
            <p className="text-[10px] font-mono text-zinc-500 mt-0.5">
              SOURCE DOCUMENT
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <pre className="px-6 py-4 text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed font-mono">
          {doc.content}
        </pre>
      </div>
    </>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function CaseWorkspace() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState<CaseDetailResponse | null>(null);
  const [briefs, setBriefs] = useState<CaseBriefResponse[]>([]);
  const [selectedBriefId, setSelectedBriefId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Brief management
  const [showAddBrief, setShowAddBrief] = useState(false);
  const [newBriefText, setNewBriefText] = useState("");
  const [newBriefTitle, setNewBriefTitle] = useState("");
  const [isAddingBrief, setIsAddingBrief] = useState(false);
  const addBriefFileRef = useRef<HTMLInputElement>(null);
  const [isEditingBrief, setIsEditingBrief] = useState(false);
  const [editBriefText, setEditBriefText] = useState("");
  const [editBriefTitle, setEditBriefTitle] = useState("");
  const [isUpdatingBrief, setIsUpdatingBrief] = useState(false);

  // Analysis state
  const [effortLevel, setEffortLevel] = useState<EffortLevel>("low");
  const [currentClaim, setCurrentClaim] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [pipelineView, setPipelineView] = useState(false);

  // Pipeline streaming state
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStepEvent[]>([]);
  const [plannerData, setPlannerData] = useState<PlannerResponse | null>(null);
  const [gatekeeperData, setGatekeeperData] = useState<GatekeeperResult | null>(null);
  const [researchData, setResearchData] = useState<ResearchResponse | null>(null);
  const [judgeData, setJudgeData] = useState<JudgeResponse | null>(null);
  const [workflowResult, setWorkflowResult] = useState<WorkflowResponse | null>(null);
  const streamControllerRef = useRef<AbortController | null>(null);

  // Investigation history
  const [logs, setLogs] = useState<InvestigationLogSummary[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // Source viewer
  const [sourceDoc, setSourceDoc] = useState<EvidenceDocumentResponse | null>(null);

  // --- Data fetching ---

  const fetchCase = useCallback(async () => {
    if (!id || typeof id !== "string") return;
    setLoading(true);
    setError(null);
    try {
      setCaseData(await getCase(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load case");
      setCaseData(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const fetchBriefs = useCallback(async () => {
    if (!id || typeof id !== "string") return;
    try {
      const list = await listBriefs(id);
      setBriefs(list);
      setSelectedBriefId((prev) =>
        list.length > 0 && (prev === null || !list.some((b) => b.id === prev))
          ? list[0].id
          : prev
      );
    } catch (e) {
      console.error("Failed to list briefs:", e);
    }
  }, [id]);

  const fetchLogs = useCallback(async () => {
    if (!id || typeof id !== "string") return;
    try {
      setLogs(await listInvestigationLogs(id));
    } catch {
      /* silently ignore for history */
    }
  }, [id]);

  useEffect(() => { fetchCase(); }, [fetchCase]);
  useEffect(() => { if (caseData) fetchBriefs(); }, [caseData, fetchBriefs]);
  useEffect(() => { if (caseData) fetchLogs(); }, [caseData, fetchLogs]);

  // Restore verdict from session storage (legacy flow)
  useEffect(() => {
    if (!id || typeof id !== "string") return;
    const stored = sessionStorage.getItem(`tracepoint_verdict_${id}`);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as JudgeResponse;
        setJudgeData(parsed);
        setCurrentClaim(parsed.fact_to_check);
        sessionStorage.removeItem(`tracepoint_verdict_${id}`);
      } catch { /* ignore */ }
    }
  }, [id]);

  // --- Helpers for step status ---

  function stepStatus(stepName: string): "pending" | "running" | "complete" {
    const events = pipelineSteps.filter((e) => e.step === stepName);
    if (events.some((e) => e.status === "complete")) return "complete";
    if (events.some((e) => e.status === "running")) return "running";
    return "pending";
  }

  // --- Analysis handler (streaming) ---

  const handleAnalyze = async () => {
    if (!currentClaim || !id || typeof id !== "string") return;
    setIsAnalyzing(true);
    setError(null);
    setPipelineSteps([]);
    setPlannerData(null);
    setGatekeeperData(null);
    setResearchData(null);
    setJudgeData(null);
    setWorkflowResult(null);
    setPipelineView(true);

    streamControllerRef.current = runWorkflowStream(id, currentClaim, {
      briefId: selectedBriefId ?? undefined,
      effortLevel,
      onStep: (event) => {
        setPipelineSteps((prev) => [...prev, event]);
        if (event.status === "complete" && event.data) {
          switch (event.step) {
            case "planner":
              setPlannerData(event.data as unknown as PlannerResponse);
              break;
            case "gatekeeper":
              setGatekeeperData(event.data as unknown as GatekeeperResult);
              break;
            case "research":
              setResearchData(event.data as unknown as ResearchResponse);
              break;
            case "judge":
            case "synthesis":
              setJudgeData(event.data as unknown as JudgeResponse);
              break;
          }
        }
      },
      onDone: (payload) => {
        setWorkflowResult(payload.data);
        if (payload.data?.final_verdict) {
          setJudgeData(payload.data.final_verdict);
        }
        setIsAnalyzing(false);
        fetchLogs();
      },
      onError: (err) => {
        setError(err.message);
        setIsAnalyzing(false);
      },
    });
  };

  // --- Load historical investigation ---

  const loadLog = async (logId: number) => {
    if (!id || typeof id !== "string") return;
    try {
      const data = await getInvestigationLog(id, logId);
      const wf = data as unknown as WorkflowResponse;
      setWorkflowResult(wf);
      setJudgeData(wf.final_verdict);
      if (wf.iterations?.[0]) {
        setPlannerData(wf.iterations[0].planner);
        setGatekeeperData(wf.iterations[0].gatekeeper);
        setResearchData(wf.iterations[0].research);
      }
      setCurrentClaim(wf.final_verdict?.fact_to_check ?? "");
      setPipelineView(true);
      // Mark all steps as complete for display
      setPipelineSteps([
        { step: "planner", status: "complete", iteration: 1, total_iterations: 1 },
        { step: "gatekeeper", status: "complete", iteration: 1, total_iterations: 1 },
        { step: "research", status: "complete", iteration: 1, total_iterations: 1 },
        { step: "judge", status: "complete", iteration: 1, total_iterations: 1 },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load investigation");
    }
  };

  // --- Source document viewer ---

  const openSourceDoc = async (sourceDocument: string) => {
    if (!id || typeof id !== "string" || !sourceDocument) return;
    try {
      const doc = await getEvidenceDocument(id, sourceDocument);
      setSourceDoc(doc);
    } catch (e) {
      console.error("Failed to load source document:", e);
    }
  };

  // --- Brief handlers ---

  const handleAddBrief = async (file?: File) => {
    if (!id || typeof id !== "string") return;
    const hasText = newBriefText.trim().length > 0;
    const hasFile = file && file.size > 0;
    if (!hasText && !hasFile) return;
    setIsAddingBrief(true);
    try {
      if (file) {
        await addBrief(id, { file, title: newBriefTitle || file.name.replace(/\.[^/.]+$/, "") });
      } else {
        await addBrief(id, { briefText: newBriefText, title: newBriefTitle || "Case Summary" });
      }
      setNewBriefText(""); setNewBriefTitle(""); setShowAddBrief(false);
      await fetchBriefs();
    } catch (e) { console.error("Failed to add brief:", e); }
    finally { setIsAddingBrief(false); }
  };

  const handleUpdateBrief = async () => {
    if (!id || typeof id !== "string" || !selectedBriefId) return;
    setIsUpdatingBrief(true);
    try {
      await updateBrief(id, selectedBriefId, { title: editBriefTitle, brief_text: editBriefText });
      setIsEditingBrief(false);
      await fetchBriefs();
    } catch (e) { console.error("Failed to update brief:", e); }
    finally { setIsUpdatingBrief(false); }
  };

  const handleDeleteBrief = async () => {
    if (!id || typeof id !== "string" || !selectedBriefId) return;
    if (!confirm("Are you sure you want to delete this summary?")) return;
    try {
      await deleteBrief(id, selectedBriefId);
      setSelectedBriefId(null);
      await fetchBriefs();
    } catch (e) { console.error("Failed to delete brief:", e); }
  };

  const startEditing = () => {
    if (!selectedBrief) return;
    setEditBriefTitle(selectedBrief.title);
    setEditBriefText(selectedBrief.brief_text);
    setIsEditingBrief(true);
  };

  const handleAddBriefFile = (f: File) => {
    if (!/\.(md|txt|markdown)$/i.test(f.name)) return;
    handleAddBrief(f);
  };

  const selectedBrief = briefs.find((b) => b.id === selectedBriefId);
  const displayBrief = selectedBrief?.brief_text ?? caseData?.brief ?? "";
  const v = judgeData?.overall_verdict;

  // --- Loading / Error states ---

  if (loading) {
    return (
      <main className="min-h-screen p-6 forensic-grid flex items-center justify-center">
        <div className="w-12 h-12 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </main>
    );
  }

  if (error && !caseData) {
    return (
      <main className="min-h-screen p-20 forensic-grid">
        <div className="font-mono text-danger">ERROR: {error}</div>
        <Link href="/" className="mt-4 text-accent hover:underline">&lt; RETURN_TO_DATABASE</Link>
      </main>
    );
  }

  if (!caseData) {
    return (
      <main className="min-h-screen p-20 forensic-grid font-mono text-danger">ERROR: CASE_NOT_FOUND</main>
    );
  }

  // =========================================================================
  // Render
  // =========================================================================

  return (
    <main className="min-h-screen p-8 forensic-grid">
      <div className="max-w-7xl mx-auto grid grid-cols-12 gap-8 animate-fade-in">
        {/* ============ LEFT SIDEBAR ============ */}
        <aside className="col-span-12 lg:col-span-4 space-y-6">
          <Link
            href="/"
            className="inline-flex gap-2 text-[10px] font-mono text-accent hover:underline mb-4 uppercase tracking-widest"
          >
            &lt; Back to Dashboard
          </Link>

          {/* Case info */}
          <section className="glass-panel p-6 rounded-2xl space-y-6">
            <div className="flex justify-between items-start">
              <h2 className="text-xl font-bold text-white leading-tight">
                {caseData.title}
              </h2>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded border ${caseData.status === "active" ? "text-success border-success/20 bg-success/5" : "text-zinc-500 border-zinc-800 bg-zinc-900"}`}
              >
                {caseData.status.toUpperCase()}
              </span>
            </div>

            {/* Brief management — preserved from original */}
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                  Case Summary
                </h3>
                <button
                  onClick={() => setShowAddBrief(!showAddBrief)}
                  className="text-[10px] font-mono text-accent hover:underline"
                >
                  {showAddBrief ? "CANCEL" : "+ ADD SUMMARY"}
                </button>
              </div>

              {briefs.length > 0 && (
                <div className="flex gap-2">
                  <select
                    value={selectedBriefId ?? ""}
                    onChange={(e) => setSelectedBriefId(e.target.value ? Number(e.target.value) : null)}
                    className="flex-1 bg-black/20 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none focus:border-accent/40"
                  >
                    {briefs.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.title} {b.source_file ? `(${b.source_file})` : ""}
                      </option>
                    ))}
                  </select>
                  {!showAddBrief && !isEditingBrief && selectedBriefId && (
                    <div className="flex gap-1">
                      <button onClick={startEditing} className="p-2 text-zinc-500 hover:text-accent transition-colors" title="Edit Summary">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                      </button>
                      <button onClick={handleDeleteBrief} className="p-2 text-zinc-500 hover:text-danger transition-colors" title="Delete Summary">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                      </button>
                    </div>
                  )}
                </div>
              )}

              {showAddBrief ? (
                <div className="space-y-3 p-4 bg-black/20 rounded-xl border border-zinc-800">
                  <input type="text" value={newBriefTitle} onChange={(e) => setNewBriefTitle(e.target.value)} placeholder="Title (optional)" className="w-full bg-black/20 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none focus:border-accent/40" />
                  <div className="min-h-[120px] border-2 border-dashed border-zinc-800 rounded-lg p-3 flex flex-col gap-2" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) handleAddBriefFile(f); }}>
                    <textarea value={newBriefText} onChange={(e) => setNewBriefText(e.target.value)} placeholder="Paste summary or drop .md / .txt file" className="flex-1 min-h-[80px] bg-transparent text-xs text-zinc-300 outline-none resize-none" />
                    <div className="flex gap-2">
                      <input ref={addBriefFileRef} type="file" accept=".md,.txt,.markdown" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAddBriefFile(f); e.target.value = ""; }} />
                      <button onClick={() => addBriefFileRef.current?.click()} className="text-[10px] font-mono text-accent hover:underline">BROWSE FILE</button>
                    </div>
                  </div>
                  <button onClick={() => handleAddBrief()} disabled={!newBriefText.trim() || isAddingBrief} className="w-full py-2 bg-accent/20 text-accent text-xs font-semibold rounded-lg hover:bg-accent/30 disabled:opacity-50 disabled:cursor-not-allowed">
                    {isAddingBrief ? "Adding…" : "Add Summary"}
                  </button>
                </div>
              ) : isEditingBrief ? (
                <div className="space-y-3 p-4 bg-black/20 rounded-xl border border-accent/20">
                  <input type="text" value={editBriefTitle} onChange={(e) => setEditBriefTitle(e.target.value)} placeholder="Brief Title" className="w-full bg-black/20 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none focus:border-accent/40" />
                  <textarea value={editBriefText} onChange={(e) => setEditBriefText(e.target.value)} placeholder="Summary content" className="w-full min-h-[120px] bg-black/20 border border-zinc-800 rounded-lg p-3 text-xs text-zinc-300 outline-none focus:border-accent/40 resize-none" />
                  <div className="flex gap-2">
                    <button onClick={handleUpdateBrief} disabled={!editBriefText.trim() || isUpdatingBrief} className="flex-1 py-2 bg-accent/20 text-accent text-xs font-semibold rounded-lg hover:bg-accent/30 disabled:opacity-50">{isUpdatingBrief ? "Saving…" : "Save Changes"}</button>
                    <button onClick={() => setIsEditingBrief(false)} className="px-4 py-2 bg-zinc-800 text-zinc-400 text-xs font-semibold rounded-lg hover:bg-zinc-700">Cancel</button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-zinc-400 leading-relaxed max-h-[200px] overflow-y-auto custom-scrollbar pr-1">
                  {displayBrief || "No summary selected."}
                </p>
              )}
            </div>
          </section>

          {/* Evidence Inventory */}
          <section className="space-y-4">
            <h3 className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest px-2">
              Evidence Inventory ({caseData.evidence.length})
            </h3>
            <div className="space-y-3 max-h-[300px] overflow-y-auto custom-scrollbar pr-1">
              {caseData.evidence.map((ev, i) => (
                <div key={i} className="glass-panel p-4 rounded-xl border-l-4 border-l-accent/40 hover:border-l-accent transition-all">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-[10px] font-mono text-zinc-500 uppercase">{ev.label.replace("_", " ")}</span>
                    <span className={`text-[10px] font-mono ${ev.reliability > 0.9 ? "text-success" : "text-warning"}`}>REL:{(ev.reliability * 100).toFixed(0)}%</span>
                  </div>
                  <h4 className="text-sm font-semibold text-zinc-200 mb-1">{ev.source_document || "Document"}</h4>
                  <p className="text-xs text-zinc-500 line-clamp-2 leading-relaxed">{ev.summary}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Investigation History */}
          <section className="space-y-3">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-2 text-[10px] font-mono text-zinc-500 uppercase tracking-widest px-2 hover:text-zinc-300 transition-colors w-full text-left"
            >
              <svg
                className={`w-3 h-3 transition-transform ${showHistory ? "rotate-90" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              Investigation History ({logs.length})
            </button>
            {showHistory && (
              <div className="space-y-1 max-h-[300px] overflow-y-auto custom-scrollbar animate-fade-in">
                {logs.length === 0 ? (
                  <p className="text-xs text-zinc-600 px-3 py-2">No past investigations.</p>
                ) : (
                  logs.map((log) => (
                    <div
                      key={log.id}
                      className="history-item"
                      data-active={workflowResult?.log_id === log.id ? "true" : "false"}
                      onClick={() => loadLog(log.id)}
                    >
                      <div className="flex justify-between items-start mb-1">
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border ${verdictColor(log.verdict)}`}>
                          {verdictLabel(log.verdict)}
                        </span>
                        <span className="text-[9px] font-mono text-zinc-600">
                          {new Date(log.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-400 line-clamp-1 mt-1">
                        {log.claim}
                      </p>
                      <span className="text-[9px] font-mono text-zinc-600 mt-0.5 block">
                        {log.effort_level.toUpperCase()}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}
          </section>
        </aside>

        {/* ============ RIGHT PANEL ============ */}
        <div className="col-span-12 lg:col-span-8 space-y-6">
          {/* Claim input section */}
          <section className="glass-panel p-8 rounded-2xl relative overflow-hidden">
            {isAnalyzing && (
              <div className="absolute top-0 left-0 right-0 h-1 bg-accent/20 overflow-hidden">
                <div className="h-full bg-accent/60 animate-pulse" style={{ width: "100%" }} />
              </div>
            )}

            <div className="space-y-5">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
                  Verify Claim
                </h3>
                {selectedBrief && (
                  <span className="text-[10px] font-mono text-zinc-600">Using: {selectedBrief.title}</span>
                )}
              </div>

              {/* Effort Selector */}
              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                  Effort:
                </span>
                <div className="flex gap-2">
                  {EFFORT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      className="effort-btn"
                      data-active={effortLevel === opt.value ? "true" : "false"}
                      onClick={() => setEffortLevel(opt.value)}
                      disabled={isAnalyzing}
                    >
                      <span className="block">{opt.label}</span>
                      <span className="block text-[8px] opacity-60 font-normal mt-0.5">
                        {opt.desc}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                value={currentClaim}
                onChange={(e) => setCurrentClaim(e.target.value)}
                placeholder="Enter a claim to verify against evidence…"
                className="w-full h-28 bg-black/20 border border-zinc-800 rounded-xl p-4 text-sm text-zinc-300 outline-none focus:border-accent/40 placeholder:text-zinc-700 resize-none transition-all"
              />

              {error && (
                <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl text-danger text-xs font-medium">
                  {error}
                </div>
              )}

              <button
                onClick={handleAnalyze}
                disabled={!currentClaim || isAnalyzing}
                className="w-full py-4 bg-accent text-white font-bold text-sm uppercase tracking-widest rounded-xl hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-accent/10"
              >
                {isAnalyzing ? "Analyzing…" : "Run Fact-Check"}
              </button>
            </div>
          </section>

          {/* Pipeline View Toggle */}
          {(judgeData || isAnalyzing) && (
            <div className="flex items-center justify-between px-2">
              <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                Pipeline View
              </span>
              <button
                onClick={() => setPipelineView(!pipelineView)}
                className={`relative w-10 h-5 rounded-full transition-colors ${pipelineView ? "bg-accent" : "bg-zinc-700"}`}
              >
                <span
                  className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${pipelineView ? "left-5" : "left-0.5"}`}
                />
              </button>
            </div>
          )}

          {/* ---- Pipeline Panels ---- */}
          {pipelineView && (isAnalyzing || plannerData) && (
            <div className="space-y-3 animate-fade-in">
              {/* Planner Panel */}
              <PipelineCard title="Planner" icon="📋" status={stepStatus("planner")}>
                {plannerData ? (
                  <div className="space-y-2 max-h-[300px] overflow-y-auto custom-scrollbar">
                    {plannerData.friction_summary?.has_friction && (
                      <div className="text-[10px] font-mono text-warning bg-warning/5 border border-warning/20 rounded-lg px-3 py-2 mb-2">
                        ⚠ Friction: {plannerData.friction_summary.description}
                      </div>
                    )}
                    {plannerData.tasks?.map((task, i) => (
                      <div key={i} className="flex items-start gap-3 p-2 rounded-lg hover:bg-white/[0.02] transition-colors">
                        <span className="type-badge mt-0.5" data-type={task.type}>{task.type}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-zinc-300 leading-relaxed">{task.question_text}</p>
                          <p className="text-[10px] text-zinc-600 font-mono mt-1 truncate" title={task.vector_query}>
                            🔍 {task.vector_query}
                          </p>
                          {gatekeeperData && (
                            <span className={`inline-block mt-1 text-[9px] font-mono ${gatekeeperData.valid ? "text-success" : "text-danger"}`}>
                              {gatekeeperData.valid ? "✓ passed" : "✗ flagged"}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Skeleton lines={4} />
                )}
              </PipelineCard>

              <div className="flow-connector" data-active={stepStatus("research") !== "pending" ? "true" : "false"}>▼</div>

              {/* Research Panel */}
              <PipelineCard title="Research" icon="🔬" status={stepStatus("research")}>
                {researchData ? (
                  <div className="space-y-3 max-h-[350px] overflow-y-auto custom-scrollbar">
                    {researchData.tasks?.map((task, i) => (
                      <div key={i} className="border border-zinc-800/50 rounded-lg p-3 space-y-2">
                        <p className="text-xs text-zinc-400 font-medium">{task.question_text}</p>
                        {task.evidence?.length > 0 ? (
                          <div className="space-y-1.5">
                            {task.evidence.map((ev, j) => (
                              <div key={j} className="pl-3 border-l-2 border-accent/20 text-[11px] text-zinc-500 leading-relaxed">
                                <div className="flex justify-between items-start mb-0.5">
                                  {ev.source_document && (
                                    <button
                                      className="source-link"
                                      onClick={() => openSourceDoc(ev.source_document!)}
                                    >
                                      📄 {ev.source_document}
                                    </button>
                                  )}
                                  <span className="text-[9px] font-mono text-zinc-600 ml-2 shrink-0">
                                    {(ev.score * 100).toFixed(0)}%
                                  </span>
                                </div>
                                <p className="text-zinc-400 line-clamp-2">{ev.chunk}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[10px] text-zinc-600 italic">No evidence retrieved</p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <Skeleton lines={5} />
                )}
              </PipelineCard>

              <div className="flow-connector" data-active={stepStatus("judge") !== "pending" ? "true" : "false"}>▼</div>

              {/* Judge Panel */}
              <PipelineCard title="Judge" icon="⚖️" status={stepStatus("judge")}>
                {judgeData ? (
                  <div className="space-y-4 max-h-[400px] overflow-y-auto custom-scrollbar">
                    {judgeData.tasks?.map((task, i) => (
                      <div key={i} className="border border-zinc-800/50 rounded-lg p-3 space-y-2">
                        <p className="text-xs text-zinc-400 font-medium">{task.question_text}</p>
                        <p className="text-xs text-zinc-300 leading-relaxed">{task.answer}</p>
                        {task.confidence != null && (
                          <div className="flex items-center gap-2">
                            <span className="text-[9px] font-mono text-zinc-500">CONF</span>
                            <div className="confidence-bar flex-1">
                              <div
                                className="confidence-bar-fill"
                                style={{
                                  width: `${(task.confidence * 100).toFixed(0)}%`,
                                  background: task.confidence > 0.7
                                    ? "var(--success)"
                                    : task.confidence > 0.4
                                      ? "var(--warning)"
                                      : "var(--danger)",
                                }}
                              />
                            </div>
                            <span className="text-[9px] font-mono text-zinc-500 w-8 text-right">
                              {(task.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        )}
                        {task.key_facts?.length > 0 && (
                          <div className="space-y-1 mt-1">
                            {task.key_facts.map((f, j) => (
                              <div key={j} className="flex items-start gap-1.5 text-[10px]">
                                <span className={f.supports_claim ? "text-success" : "text-danger"}>
                                  {f.supports_claim ? "↑" : "↓"}
                                </span>
                                <span className="text-zinc-500">{f.description}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <Skeleton lines={4} />
                )}
              </PipelineCard>
            </div>
          )}

          {/* ---- Verdict Panel (always visible when we have a verdict) ---- */}
          <section className="glass-panel p-8 rounded-2xl space-y-8 min-h-[300px] flex flex-col">
            <div className="flex justify-between items-center border-b border-white/5 pb-4">
              <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
                Evidence Synthesis
              </h3>
              <div className="flex gap-6">
                <div className="flex items-center gap-2 text-[10px] font-mono text-success uppercase">
                  <div className="w-2 h-2 rounded-full bg-success" /> Consistent
                </div>
                <div className="flex items-center gap-2 text-[10px] font-mono text-danger uppercase">
                  <div className="w-2 h-2 rounded-full bg-danger" /> Contradiction
                </div>
              </div>
            </div>

            {!judgeData ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-30 space-y-4">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12">
                  <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-xs font-mono uppercase tracking-widest">Awaiting Analysis</p>
              </div>
            ) : (
              <div className="space-y-8 animate-fade-in">
                <div className="flex items-center gap-4">
                  <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Verdict</span>
                  <span className={`px-4 py-1.5 rounded-lg font-mono text-xs font-bold border ${verdictColor(v?.verdict)}`}>
                    {verdictLabel(v?.verdict)}
                  </span>
                  {workflowResult && (
                    <span className="text-[9px] font-mono text-zinc-600 ml-auto">
                      {workflowResult.effort_level.toUpperCase()} · {workflowResult.iterations?.length ?? 1} pass{(workflowResult.iterations?.length ?? 1) > 1 ? "es" : ""}
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  <h4 className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">Rationale</h4>
                  <p className="text-sm text-zinc-300 leading-relaxed">{v?.rationale}</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {(v?.supporting_facts?.length ?? 0) > 0 && (
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-mono text-success uppercase tracking-widest">Supporting Evidence</h4>
                      <ul className="space-y-3">
                        {v?.supporting_facts.map((f, i) => (
                          <li key={i} className="text-xs text-zinc-400 border-l-2 border-success/30 pl-3 leading-relaxed">{f.description}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(v?.contradicting_facts?.length ?? 0) > 0 && (
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-mono text-danger uppercase tracking-widest">Contradicting Evidence</h4>
                      <ul className="space-y-3">
                        {v?.contradicting_facts.map((f, i) => (
                          <li key={i} className="text-xs text-zinc-400 border-l-2 border-danger/30 pl-3 leading-relaxed">{f.description}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Source Document Viewer */}
      <SourceViewer doc={sourceDoc} onClose={() => setSourceDoc(null)} />
    </main>
  );
}
