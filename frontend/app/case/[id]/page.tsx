"use client";

import {
  getCase,
  runWorkflow,
  listBriefs,
  addBrief,
  type CaseBriefResponse,
  type CaseDetailResponse,
  type JudgeResponse,
} from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, useRef } from "react";

export default function CaseWorkspace() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState<CaseDetailResponse | null>(null);
  const [briefs, setBriefs] = useState<CaseBriefResponse[]>([]);
  const [selectedBriefId, setSelectedBriefId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentClaim, setCurrentClaim] = useState("");
  const [verdict, setVerdict] = useState<JudgeResponse | null>(null);

  const [showAddBrief, setShowAddBrief] = useState(false);
  const [newBriefText, setNewBriefText] = useState("");
  const [newBriefTitle, setNewBriefTitle] = useState("");
  const [isAddingBrief, setIsAddingBrief] = useState(false);
  const addBriefFileRef = useRef<HTMLInputElement>(null);

  const fetchCase = useCallback(async () => {
    if (!id || typeof id !== "string") return;
    setLoading(true);
    setError(null);
    try {
      const data = await getCase(id);
      setCaseData(data);
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

  useEffect(() => {
    fetchCase();
  }, [fetchCase]);

  useEffect(() => {
    if (caseData) fetchBriefs();
  }, [caseData, fetchBriefs]);

  useEffect(() => {
    if (!id || typeof id !== "string") return;
    const stored = sessionStorage.getItem(`tracepoint_verdict_${id}`);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as JudgeResponse;
        setVerdict(parsed);
        setCurrentClaim(parsed.fact_to_check);
        sessionStorage.removeItem(`tracepoint_verdict_${id}`);
      } catch {
        /* ignore */
      }
    }
  }, [id]);

  const handleAnalyze = async () => {
    if (!currentClaim || !id || typeof id !== "string") return;
    setIsAnalyzing(true);
    setError(null);
    try {
      const result = await runWorkflow(
        id,
        currentClaim,
        selectedBriefId ?? undefined
      );
      setVerdict(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fact-check failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleAddBrief = async (file?: File) => {
    if (!id || typeof id !== "string") return;
    const hasText = newBriefText.trim().length > 0;
    const hasFile = file && file.size > 0;
    if (!hasText && !hasFile) return;

    setIsAddingBrief(true);
    try {
      if (file) {
        await addBrief(id, {
          file,
          title: newBriefTitle || file.name.replace(/\.[^/.]+$/, ""),
        });
      } else {
        await addBrief(id, {
          briefText: newBriefText,
          title: newBriefTitle || "Case Summary",
        });
      }
      setNewBriefText("");
      setNewBriefTitle("");
      setShowAddBrief(false);
      await fetchBriefs();
    } catch (e) {
      console.error("Failed to add brief:", e);
    } finally {
      setIsAddingBrief(false);
    }
  };

  const handleAddBriefFile = (f: File) => {
    if (!/\.(md|txt|markdown)$/i.test(f.name)) return;
    handleAddBrief(f);
  };

  const selectedBrief = briefs.find((b) => b.id === selectedBriefId);
  const displayBrief = selectedBrief?.brief_text ?? caseData?.brief ?? "";

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
        <Link href="/" className="mt-4 text-accent hover:underline">
          &lt; RETURN_TO_DATABASE
        </Link>
      </main>
    );
  }

  if (!caseData) {
    return (
      <main className="min-h-screen p-20 forensic-grid font-mono text-danger">
        ERROR: CASE_NOT_FOUND
      </main>
    );
  }

  const v = verdict?.overall_verdict;

  return (
    <main className="min-h-screen p-8 forensic-grid">
      <div className="max-w-7xl mx-auto grid grid-cols-12 gap-8 animate-fade-in">
        <aside className="col-span-12 lg:col-span-4 space-y-6">
          <Link
            href="/"
            className="inline-flex gap-2 text-[10px] font-mono text-accent hover:underline mb-4 uppercase tracking-widest"
          >
            &lt; Back to Dashboard
          </Link>

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
                <select
                  value={selectedBriefId ?? ""}
                  onChange={(e) =>
                    setSelectedBriefId(e.target.value ? Number(e.target.value) : null)
                  }
                  className="w-full bg-black/20 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none focus:border-accent/40"
                >
                  {briefs.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.title} {b.source_file ? `(${b.source_file})` : ""}
                    </option>
                  ))}
                </select>
              )}

              {showAddBrief ? (
                <div className="space-y-3 p-4 bg-black/20 rounded-xl border border-zinc-800">
                  <input
                    type="text"
                    value={newBriefTitle}
                    onChange={(e) => setNewBriefTitle(e.target.value)}
                    placeholder="Title (optional)"
                    className="w-full bg-black/20 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none focus:border-accent/40"
                  />
                  <div
                    className="min-h-[120px] border-2 border-dashed border-zinc-800 rounded-lg p-3 flex flex-col gap-2"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const f = e.dataTransfer.files?.[0];
                      if (f) handleAddBriefFile(f);
                    }}
                  >
                    <textarea
                      value={newBriefText}
                      onChange={(e) => setNewBriefText(e.target.value)}
                      placeholder="Paste summary or drop .md / .txt file"
                      className="flex-1 min-h-[80px] bg-transparent text-xs text-zinc-300 outline-none resize-none"
                    />
                    <div className="flex gap-2">
                      <input
                        ref={addBriefFileRef}
                        type="file"
                        accept=".md,.txt,.markdown"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) handleAddBriefFile(f);
                          e.target.value = "";
                        }}
                      />
                      <button
                        onClick={() => addBriefFileRef.current?.click()}
                        className="text-[10px] font-mono text-accent hover:underline"
                      >
                        BROWSE FILE
                      </button>
                    </div>
                  </div>
                  <button
                    onClick={() => handleAddBrief()}
                    disabled={
                      (!newBriefText.trim() && true) || isAddingBrief
                    }
                    className="w-full py-2 bg-accent/20 text-accent text-xs font-semibold rounded-lg hover:bg-accent/30 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isAddingBrief ? "Adding…" : "Add Summary"}
                  </button>
                </div>
              ) : (
                <p className="text-sm text-zinc-400 leading-relaxed max-h-[200px] overflow-y-auto custom-scrollbar pr-1">
                  {displayBrief || "No summary selected."}
                </p>
              )}
            </div>
          </section>

          <section className="space-y-4">
            <h3 className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest px-2">
              Evidence Inventory ({caseData.evidence.length})
            </h3>
            <div className="space-y-3 max-h-[400px] overflow-y-auto custom-scrollbar pr-1">
              {caseData.evidence.map((ev, i) => (
                <div
                  key={i}
                  className="glass-panel p-4 rounded-xl border-l-4 border-l-accent/40 hover:border-l-accent transition-all"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-[10px] font-mono text-zinc-500 uppercase">
                      {ev.label.replace("_", " ")}
                    </span>
                    <span
                      className={`text-[10px] font-mono ${ev.reliability > 0.9 ? "text-success" : "text-warning"}`}
                    >
                      REL:{(ev.reliability * 100).toFixed(0)}%
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-zinc-200 mb-1">
                    {ev.source_document || "Document"}
                  </h4>
                  <p className="text-xs text-zinc-500 line-clamp-2 leading-relaxed">
                    {ev.summary}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </aside>

        <div className="col-span-12 lg:col-span-8 space-y-8">
          <section className="glass-panel p-8 rounded-2xl relative overflow-hidden">
            {isAnalyzing && (
              <div className="absolute inset-0 bg-background/80 flex flex-col items-center justify-center backdrop-blur-sm z-10">
                <div className="w-12 h-12 border-4 border-accent/10 border-t-accent rounded-full animate-spin" />
                <span className="mt-4 font-mono text-accent text-xs animate-pulse tracking-widest uppercase">
                  Analyzing Evidence…
                </span>
              </div>
            )}

            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest">
                  Verify Claim
                </h3>
                {selectedBrief && (
                  <span className="text-[10px] font-mono text-zinc-600">
                    Using: {selectedBrief.title}
                  </span>
                )}
              </div>

              <textarea
                value={currentClaim}
                onChange={(e) => setCurrentClaim(e.target.value)}
                placeholder="Enter a claim to verify against evidence…"
                className="w-full h-32 bg-black/20 border border-zinc-800 rounded-xl p-4 text-sm text-zinc-300 outline-none focus:border-accent/40 placeholder:text-zinc-700 resize-none transition-all"
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
                Run Fact-Check
              </button>
            </div>
          </section>

          <section className="glass-panel p-8 rounded-2xl space-y-8 min-h-[450px] flex flex-col">
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

            {!verdict ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-30 space-y-4">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className="w-12 h-12"
                >
                  <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-xs font-mono uppercase tracking-widest">
                  Awaiting Analysis
                </p>
              </div>
            ) : (
              <div className="space-y-8 animate-fade-in">
                <div className="flex items-center gap-4">
                  <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                    Verdict
                  </span>
                  <span
                    className={`px-4 py-1.5 rounded-lg font-mono text-xs font-bold border ${
                      v?.verdict === "true" || v?.verdict === "likely_true"
                        ? "bg-success/10 text-success border-success/20"
                        : v?.verdict === "false" || v?.verdict === "likely_false"
                          ? "bg-danger/10 text-danger border-danger/20"
                          : "bg-warning/10 text-warning border-warning/20"
                    }`}
                  >
                    {v?.verdict.toUpperCase().replace("_", " ")}
                  </span>
                </div>

                <div className="space-y-3">
                  <h4 className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">
                    Rationale
                  </h4>
                  <p className="text-sm text-zinc-300 leading-relaxed">
                    {v?.rationale}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {(v?.supporting_facts?.length ?? 0) > 0 && (
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-mono text-success uppercase tracking-widest">
                        Supporting Evidence
                      </h4>
                      <ul className="space-y-3">
                        {v?.supporting_facts.map((f, i) => (
                          <li
                            key={i}
                            className="text-xs text-zinc-400 border-l-2 border-success/30 pl-3 leading-relaxed"
                          >
                            {f.description}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(v?.contradicting_facts?.length ?? 0) > 0 && (
                    <div className="space-y-4">
                      <h4 className="text-[10px] font-mono text-danger uppercase tracking-widest">
                        Contradicting Evidence
                      </h4>
                      <ul className="space-y-3">
                        {v?.contradicting_facts.map((f, i) => (
                          <li
                            key={i}
                            className="text-xs text-zinc-400 border-l-2 border-danger/30 pl-3 leading-relaxed"
                          >
                            {f.description}
                          </li>
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
    </main>
  );
}
