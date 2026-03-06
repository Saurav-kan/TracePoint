"use client";

import {
  createCase,
  ingestFile,
  LABELS,
  runWorkflow,
  toBackendLabel,
  listCases,
  type CaseSummaryResponse,
} from "@/lib/api";
import { useRouter } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import Link from "next/link";

type Step = "upload" | "labeling" | "context" | "processing";

interface FileEntry {
  file: File;
  name: string;
  size: number;
  label: string;
  type: string;
}

const PROCESS_STAGES = [
  "Creating case...",
  "Ingesting evidence...",
  "Running planner...",
  "Running research...",
  "Running judge...",
];

export default function Home() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("upload");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [caseSummary, setCaseSummary] = useState("");
  const [question, setQuestion] = useState("");
  const [processingStage, setProcessingStage] = useState(0);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recentCases, setRecentCases] = useState<CaseSummaryResponse[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listCases()
      .then(setRecentCases)
      .catch((err) => console.error("Failed to list cases:", err));
  }, []);

  const handleFiles = (newFiles: FileList | null) => {
    if (!newFiles) return;
    const entries: FileEntry[] = Array.from(newFiles).map((f) => ({
      file: f,
      name: f.name,
      size: f.size,
      label: "Forensic Log",
      type: f.type,
    }));
    setFiles((prev) => [...prev, ...entries]);
  };

  const updateLabel = (index: number, label: string) => {
    const newFiles = [...files];
    newFiles[index].label = label;
    setFiles(newFiles);
  };

  const handleCaseSummaryFile = (file: File) => {
    if (!/\.(md|txt|markdown)$/i.test(file.name)) return;
    const reader = new FileReader();
    reader.onload = () => setCaseSummary(String(reader.result ?? ""));
    reader.readAsText(file);
  };

  const handleInitialize = async () => {
    if (!caseSummary.trim() || !question.trim() || files.length === 0) return;
    setIsProcessing(true);
    setProcessingError(null);
    setStep("processing");
    setProcessingStage(0);

    try {
      const title = caseSummary.split("\n")[0].slice(0, 80) || "New Investigation";
      const { case_id } = await createCase(title, caseSummary);
      setProcessingStage(1);

      for (const entry of files) {
        await ingestFile(entry.file, toBackendLabel(entry.label), case_id);
      }
      setProcessingStage(2);

      const verdict = await runWorkflow(case_id, question);
      setProcessingStage(4);

      if (typeof window !== "undefined") {
        sessionStorage.setItem(
          `tracepoint_verdict_${case_id}`,
          JSON.stringify(verdict)
        );
      }
      router.push(`/case/${case_id}`);
    } catch (err) {
      setProcessingError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <main className="min-h-screen p-8 forensic-grid flex flex-col items-center">
      <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-12 gap-8 animate-fade-in">
        
        {/* Left: Main Flow */}
        <div className="lg:col-span-8 space-y-8">
          <div className="flex justify-between items-center px-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">TracePoint</h1>
            <div className="flex gap-4">
              {["Upload", "Labels", "Context", "Process"].map((l, i) => {
                const steps: Step[] = ["upload", "labeling", "context", "processing"];
                const isActive = steps[i] === step;
                const isDone = steps.indexOf(step) > i;
                return (
                  <div key={l} className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isActive ? "bg-accent shadow-[0_0_8px_var(--accent)]" : isDone ? "bg-accent/40" : "bg-zinc-800"}`} />
                    <span className={`text-[10px] font-mono uppercase tracking-widest ${isActive ? "text-accent" : "text-zinc-500"}`}>{l}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="glass-panel p-8 min-h-[500px] flex flex-col rounded-2xl relative overflow-hidden">
            {step === "upload" && (
              <div className="flex-1 flex flex-col gap-8">
                <div 
                  className="flex-1 border-2 border-dashed border-zinc-800 rounded-2xl flex flex-col items-center justify-center gap-6 group hover:border-accent/40 transition-all cursor-pointer bg-black/20"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleFiles(e.dataTransfer.files);
                  }}
                >
                  <input type="file" multiple ref={fileInputRef} className="hidden" onChange={(e) => handleFiles(e.target.files)} />
                  <div className="w-16 h-16 rounded-full bg-accent/5 flex items-center justify-center border border-accent/20 group-hover:scale-105 transition-transform">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-8 h-8 text-accent">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                    </svg>
                  </div>
                  <div className="text-center space-y-2">
                    <h2 className="text-xl font-semibold text-white">Ingest Evidence</h2>
                    <p className="text-zinc-500 text-sm">Drag and drop files or click to browse</p>
                  </div>
                </div>

                {files.length > 0 && (
                  <div className="space-y-4 animate-fade-in">
                    <div className="flex justify-between items-center text-xs font-mono text-zinc-500 uppercase tracking-widest">
                      <span>Queue ({files.length})</span>
                    </div>
                    <div className="max-h-[160px] overflow-y-auto custom-scrollbar space-y-2">
                      {files.map((f, i) => (
                        <div key={i} className="flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/5">
                          <span className="text-sm text-zinc-300 truncate max-w-[400px]">{f.name}</span>
                          <span className="text-[10px] font-mono text-zinc-500">{(f.size / 1024).toFixed(1)}KB</span>
                        </div>
                      ))}
                    </div>
                    <button 
                      onClick={() => setStep("labeling")}
                      className="w-full py-4 bg-accent text-white font-bold text-sm tracking-widest uppercase rounded-xl hover:bg-accent/90 transition-all shadow-lg shadow-accent/10"
                    >
                      Continue to Classification &gt;
                    </button>
                  </div>
                )}
              </div>
            )}

            {step === "labeling" && (
              <div className="flex-1 flex flex-col space-y-6 animate-slide-in">
                <div className="flex justify-between items-center border-b border-white/5 pb-4">
                  <h2 className="text-lg font-semibold text-white">Classify Evidence</h2>
                  <span className="text-xs text-zinc-500">{files.length} objects detected</span>
                </div>
                <div className="flex-1 overflow-y-auto max-h-[350px] pr-2 custom-scrollbar space-y-3">
                  {files.map((file, i) => (
                    <div key={i} className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-accent/20 transition-colors">
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-zinc-200 truncate max-w-[300px]">{file.name}</span>
                        <span className="text-[10px] font-mono text-zinc-500 uppercase">{(file.size / 1024).toFixed(1)}KB</span>
                      </div>
                      <select 
                        value={file.label}
                        onChange={(e) => updateLabel(i, e.target.value)}
                        className="bg-zinc-900 text-xs border border-zinc-800 rounded-lg px-3 py-2 text-accent outline-none focus:border-accent/50 cursor-pointer"
                      >
                        {LABELS.map(l => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
                <button 
                  onClick={() => setStep("context")}
                  className="w-full py-4 bg-accent text-white font-bold text-sm tracking-widest uppercase rounded-xl hover:bg-accent/90 transition-all"
                >
                  Confirm Labels &gt;
                </button>
              </div>
            )}

            {step === "context" && (
              <div className="flex-1 flex flex-col space-y-8 animate-slide-in">
                <div className="space-y-6">
                  <div className="space-y-3">
                    <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Case Summary</label>
                    <div
                      className="w-full h-44 border-2 border-dashed border-zinc-800 rounded-xl overflow-hidden flex flex-col hover:border-accent/40 transition-all"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const f = e.dataTransfer.files?.[0];
                        if (f) handleCaseSummaryFile(f);
                      }}
                    >
                      <textarea
                        value={caseSummary}
                        onChange={(e) => setCaseSummary(e.target.value)}
                        placeholder="Paste or type your case summary… or drop a .md / .txt file here"
                        className="flex-1 w-full min-h-[140px] bg-black/20 p-4 text-sm text-zinc-300 outline-none focus:border-accent/40 placeholder:text-zinc-700 resize-none"
                      />
                      <div className="px-4 py-2 border-t border-white/5 text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                        .md / .txt file drop supported
                      </div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Investigative Question</label>
                    <input 
                      type="text"
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="What claim are we verifying?"
                      className="w-full bg-black/20 border border-zinc-800 rounded-xl px-4 py-4 text-sm text-zinc-300 outline-none focus:border-accent/40 placeholder:text-zinc-700 transition-all"
                    />
                  </div>
                </div>
                <button 
                  onClick={handleInitialize}
                  disabled={!caseSummary.trim() || !question.trim() || files.length === 0 || isProcessing}
                  className="w-full py-5 bg-accent text-white font-bold text-sm tracking-widest uppercase rounded-xl hover:bg-accent/90 transition-all mt-auto disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Start Analysis
                </button>
              </div>
            )}

            {step === "processing" && (
              <div className="flex-1 flex flex-col items-center justify-center p-8 animate-fade-in">
                <div className="space-y-12 w-full max-w-sm">
                  <div className="flex flex-col items-center gap-6">
                    <div className="w-16 h-16 border-4 border-accent/10 border-t-accent rounded-full animate-spin"></div>
                    <h2 className="text-xl font-semibold text-white">System Processing</h2>
                  </div>

                  {processingError ? (
                    <div className="space-y-4">
                      <p className="text-danger text-sm text-center font-medium bg-danger/10 p-4 rounded-xl border border-danger/20">{processingError}</p>
                      <button onClick={() => { setProcessingError(null); setStep("context"); }} className="w-full py-3 text-accent text-sm font-semibold hover:underline">Return to Context</button>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {PROCESS_STAGES.map((s, i) => (
                        <div key={s} className="flex items-center gap-4">
                          <div className={`w-2 h-2 rounded-full transition-all duration-300 ${i < processingStage ? "bg-success" : i === processingStage ? "bg-accent animate-pulse" : "bg-zinc-800"}`} />
                          <span className={`text-xs font-medium ${i < processingStage ? "text-success" : i === processingStage ? "text-accent" : "text-zinc-600"}`}>{s}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Case History */}
        <aside className="lg:col-span-4 space-y-6">
          <div className="flex items-center justify-between px-2">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Recent Investigations</h2>
          </div>
          <div className="glass-panel rounded-2xl p-4 min-h-[500px] flex flex-col gap-3 overflow-hidden">
            {recentCases.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-8 opacity-40">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mb-4">
                  <path d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                <p className="text-xs">No previous cases found</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto custom-scrollbar pr-1 space-y-3">
                {recentCases.map((c) => (
                  <Link key={c.case_id} href={`/case/${c.case_id}`} className="block p-4 bg-white/5 rounded-xl border border-white/5 hover:border-accent/30 hover:bg-white/10 transition-all group">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-[10px] font-mono text-zinc-500 uppercase">{new Date(c.created_at).toLocaleDateString()}</span>
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${c.status === 'active' ? 'text-success border-success/20 bg-success/5' : 'text-zinc-500 border-zinc-800 bg-zinc-900'}`}>{c.status}</span>
                    </div>
                    <h3 className="text-sm font-semibold text-zinc-200 group-hover:text-accent transition-colors line-clamp-1">{c.title}</h3>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>

      <footer className="mt-12 text-[10px] font-mono text-zinc-600 flex gap-8">
        <span>ID_294-X8</span>
        <span>NODE: PRIMARY_ALPHA</span>
        <span>{new Date().toLocaleTimeString()}</span>
      </footer>
    </main>
  );
}
