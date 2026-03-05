"use client";

import { getCase, runWorkflow, type CaseDetailResponse, type JudgeResponse } from "@/lib/api";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

export default function CaseWorkspace() {
  const { id } = useParams();
  const [caseData, setCaseData] = useState<CaseDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentClaim, setCurrentClaim] = useState("");
  const [verdict, setVerdict] = useState<JudgeResponse | null>(null);

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

  useEffect(() => {
    fetchCase();
  }, [fetchCase]);

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
      const result = await runWorkflow(id, currentClaim);
      setVerdict(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fact-check failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

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
    <main className="min-h-screen p-6 forensic-grid pb-20">
      <div className="max-w-7xl mx-auto grid grid-cols-12 gap-6">
        {/* Left Sidebar: Case Info & Evidence */}
        <aside className="col-span-12 lg:col-span-4 space-y-6">
          <Link
            href="/"
            className="inline-flex gap-2 text-[10px] font-mono text-accent hover:underline mb-4"
          >
            &lt; RETURN_TO_DATABASE
          </Link>

          <section className="glass-panel p-6 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold glow-text tracking-tight">
                {caseData.title}
              </h2>
              <span className="text-[10px] font-mono text-success border border-success/30 px-2 py-0.5 rounded uppercase">
                {caseData.status}
              </span>
            </div>
            <p className="text-sm text-zinc-400 font-mono leading-relaxed">
              {caseData.brief}
            </p>
          </section>

          <section className="space-y-4">
            <h3 className="text-xs font-mono text-zinc-500 uppercase tracking-widest border-l-2 border-accent pl-2">
              Evidence_Inventory [{caseData.evidence.length}]
            </h3>
            <div className="space-y-3">
              {caseData.evidence.map((ev, i) => (
                <div
                  key={i}
                  className="glass-panel p-4 border-l-4 border-l-accent/50 hover:border-l-accent transition-all cursor-crosshair"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-[10px] font-mono text-zinc-400 capitalize">
                      {ev.label}
                    </span>
                    <span
                      className={`text-[10px] font-mono ${ev.reliability > 0.9 ? "text-success" : "text-warning"}`}
                    >
                      REL:{(ev.reliability * 100).toFixed(0)}%
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-zinc-200">
                    {ev.source_document || "Document"}
                  </h4>
                  <p className="text-[10px] text-zinc-500 mt-1 line-clamp-2">
                    {ev.summary}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </aside>

        {/* Main Workspace: Fact-Check & Verdict */}
        <div className="col-span-12 lg:col-span-8 space-y-6">
          <section className="glass-panel p-8 relative overflow-hidden">
            {isAnalyzing && (
              <div className="absolute inset-0 bg-accent/5 flex flex-col items-center justify-center backdrop-blur-sm z-10">
                <div className="w-12 h-12 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                <span className="mt-4 font-mono text-accent text-xs animate-pulse">
                  RUNNING_PLANNER_AGENT...
                </span>
              </div>
            )}

            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-mono text-accent uppercase tracking-widest">
                  SUBMIT_CLAIM_FOR_VERIFICATION
                </h3>
                <span className="text-[10px] font-mono text-zinc-500">
                  ENGINE: GEMINI_PRO_STATE_V1.2
                </span>
              </div>

              <div className="relative">
                <textarea
                  value={currentClaim}
                  onChange={(e) => setCurrentClaim(e.target.value)}
                  placeholder="Example: The suspect was at the Harbor Pier at 11:30 PM..."
                  className="w-full h-32 bg-background/50 border border-panel-border rounded-lg p-4 font-mono text-sm text-accent focus:border-accent/50 outline-none transition-all resize-none"
                />
                <div className="absolute bottom-4 right-4 text-[10px] font-mono text-zinc-600">
                  INPUT_BUFFER.AUTO_SAVE: ON
                </div>
              </div>

              {error && (
                <p className="text-danger text-sm font-mono">{error}</p>
              )}

              <button
                onClick={handleAnalyze}
                disabled={!currentClaim || isAnalyzing}
                className="w-full py-4 bg-accent/10 border border-accent/30 text-accent font-mono text-sm uppercase tracking-tighter hover:bg-accent/20 disabled:opacity-30 disabled:pointer-events-none transition-all rounded-lg group"
              >
                EXECUTE_FACT_CHECK_PROTOCOL{" "}
                <span className="group-hover:translate-x-1 inline-block transition-transform">
                  -&gt;
                </span>
              </button>
            </div>
          </section>

          {/* Verdict / Evidence Synthesis */}
          <section className="glass-panel p-8 space-y-6 min-h-[400px]">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-mono text-zinc-400 uppercase tracking-widest">
                EVIDENCE_SYNTHESIS_MATRIX
              </h3>
              <div className="flex gap-4">
                <div className="flex items-center gap-2 text-[10px] font-mono text-success">
                  <div className="w-2 h-2 rounded-full bg-success" /> CONSISTENT
                </div>
                <div className="flex items-center gap-2 text-[10px] font-mono text-danger">
                  <div className="w-2 h-2 rounded-full bg-danger" /> CONTRADICTION
                </div>
              </div>
            </div>

            <div className="relative min-h-[300px] border border-panel-border/30 rounded bg-background/40 flex flex-col p-6">
              <div className="absolute inset-0 forensic-grid opacity-20 rounded pointer-events-none" />

              {!verdict ? (
                <div className="text-center space-y-2 opacity-40 relative z-10">
                  <div className="text-4xl font-mono text-zinc-600">[!]</div>
                  <p className="text-[10px] font-mono text-zinc-500">
                    AWAITING_INPUT_FOR_SPATIAL_MAPPING
                  </p>
                </div>
              ) : (
                <div className="space-y-6 relative z-10">
                  <div className="flex items-center gap-4">
                    <span className="text-[10px] font-mono text-zinc-500">
                      CLAIM:
                    </span>
                    <span className="text-sm text-zinc-300 font-mono">
                      {verdict.fact_to_check}
                    </span>
                  </div>

                  {v && (
                    <>
                      <div className="flex items-center gap-4">
                        <span className="text-[10px] font-mono text-accent uppercase">
                          VERDICT
                        </span>
                        <span
                          className={`px-3 py-1 rounded font-mono text-sm font-bold ${
                            v.verdict === "true" || v.verdict === "likely_true"
                              ? "bg-success/20 text-success border border-success/50"
                              : v.verdict === "false" || v.verdict === "likely_false"
                                ? "bg-danger/20 text-danger border border-danger/50"
                                : "bg-warning/20 text-warning border border-warning/50"
                          }`}
                        >
                          {v.verdict.toUpperCase().replace("_", " ")}
                        </span>
                      </div>
                      <p className="text-sm text-zinc-300 font-mono leading-relaxed">
                        {v.rationale}
                      </p>
                      {v.supporting_facts.length > 0 && (
                        <div>
                          <h4 className="text-[10px] font-mono text-success uppercase mb-2">
                            Supporting
                          </h4>
                          <ul className="space-y-1 text-xs text-zinc-400 font-mono">
                            {v.supporting_facts.map((f, i) => (
                              <li key={i} className="border-l-2 border-success/50 pl-2">
                                {f.description}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {v.contradicting_facts.length > 0 && (
                        <div>
                          <h4 className="text-[10px] font-mono text-danger uppercase mb-2">
                            Contradicting
                          </h4>
                          <ul className="space-y-1 text-xs text-zinc-400 font-mono">
                            {v.contradicting_facts.map((f, i) => (
                              <li key={i} className="border-l-2 border-danger/50 pl-2">
                                {f.description}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
