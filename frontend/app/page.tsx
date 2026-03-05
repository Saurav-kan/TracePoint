"use client";

import {
  createCase,
  ingestFile,
  LABELS,
  runWorkflow,
  toBackendLabel,
} from "@/lib/api";
import { useRouter } from "next/navigation";
import { useState, useRef } from "react";

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
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    // Stay on upload step; user clicks Next to advance
  };

  const updateLabel = (index: number, label: string) => {
    const newFiles = [...files];
    newFiles[index].label = label;
    setFiles(newFiles);
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
    <main className="min-h-screen p-8 forensic-grid flex items-center justify-center">
      <div className="w-full max-w-3xl space-y-8 animate-fade-in">
        {/* Progress Header */}
        <div className="flex justify-between items-center px-4 relative step-indicator">
          {["UPLOAD", "LABELS", "CONTEXT", "PROCESS"].map((label, i) => {
            const steps: Step[] = ["upload", "labeling", "context", "processing"];
            const isActive = steps[i] === step;
            const isDone = steps.indexOf(step) > i;
            return (
              <div key={label} className="relative z-10 flex flex-col items-center gap-2">
                <div
                  className={`w-3 h-3 rounded-full transition-all duration-500 ${
                    isActive
                      ? "bg-accent pulse-accent scale-125"
                      : isDone
                        ? "bg-accent/40"
                        : "bg-zinc-800"
                  }`}
                />
                <span
                  className={`text-[10px] font-mono tracking-widest ${isActive ? "text-accent" : "text-zinc-500"}`}
                >
                  {label}
                </span>
              </div>
            );
          })}
        </div>

        <div className="glass-panel p-8 min-h-[400px] flex flex-col relative overflow-hidden">
          {/* Step 1: Upload */}
          {step === "upload" && (
            <div className="flex-1 flex flex-col gap-6">
              {files.length === 0 ? (
                <div
                  className="flex-1 border-2 border-dashed border-zinc-800 rounded-xl flex flex-col items-center justify-center gap-6 group hover:border-accent/40 transition-all cursor-pointer min-h-[300px]"
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleFiles(e.dataTransfer.files);
                  }}
                >
                  <input
                    type="file"
                    multiple
                    ref={fileInputRef}
                    className="hidden"
                    onChange={(e) => handleFiles(e.target.files)}
                  />
                  <div className="w-16 h-16 rounded-full bg-accent/5 flex items-center justify-center border border-accent/20 group-hover:scale-110 transition-transform">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      className="w-8 h-8 text-accent"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                    </svg>
                  </div>
                  <div className="text-center space-y-2">
                    <h2 className="text-2xl font-bold tracking-tight text-white glow-text">
                      INITIALIZE DATA INGESTION
                    </h2>
                    <p className="text-zinc-500 font-mono text-xs">
                      DRAG_AND_DROP_FOLDER // OR_CLICK_TO_SCAN
                    </p>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex justify-between items-center border-b border-white/5 pb-4">
                    <h2 className="text-lg font-bold text-white tracking-tight">
                      FILES_QUEUED
                    </h2>
                    <span className="text-[10px] font-mono text-zinc-500">
                      {files.length}_OBJECTS
                    </span>
                  </div>
                  <div className="flex-1 overflow-y-auto max-h-[200px] pr-2 custom-scrollbar space-y-2">
                    {files.map((f, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2 bg-white/5 rounded border border-white/5"
                      >
                        <span className="text-sm text-zinc-300 truncate max-w-[240px]">
                          {f.name}
                        </span>
                        <span className="text-[10px] font-mono text-zinc-500">
                          {(f.size / 1024).toFixed(1)}KB
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="flex-1 py-3 border border-zinc-700 text-zinc-300 font-mono text-xs tracking-widest uppercase rounded-lg hover:border-accent/50 hover:text-accent transition-all"
                    >
                      ADD MORE
                    </button>
                    <button
                      onClick={() => setStep("labeling")}
                      className="flex-1 py-3 bg-accent text-black font-bold text-xs tracking-widest uppercase rounded-lg hover:bg-accent/80 transition-all shadow-[0_0_15px_rgba(0,242,255,0.1)]"
                    >
                      NEXT &gt;
                    </button>
                  </div>
                  <input
                    type="file"
                    multiple
                    ref={fileInputRef}
                    className="hidden"
                    onChange={(e) => handleFiles(e.target.files)}
                  />
                </>
              )}
            </div>
          )}

          {/* Step 2: Labeling */}
          {step === "labeling" && (
            <div className="flex-1 flex flex-col space-y-6 animate-slide-in">
              <div className="flex justify-between items-center border-b border-white/5 pb-4">
                <h2 className="text-lg font-bold text-white tracking-tight">
                  CLASSIFY_EVIDENCE
                </h2>
                <span className="text-[10px] font-mono text-zinc-500">
                  {files.length}_OBJECTS_DETECTED
                </span>
              </div>
              <div className="flex-1 overflow-y-auto max-h-[300px] pr-2 custom-scrollbar space-y-3">
                {files.map((file, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/5 group hover:border-accent/30 transition-colors"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-zinc-200 truncate max-w-[200px]">
                        {file.name}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-500 uppercase">
                        {(file.size / 1024).toFixed(1)}KB
                      </span>
                    </div>
                    <select
                      value={file.label}
                      onChange={(e) => updateLabel(i, e.target.value)}
                      className="bg-black/40 text-[10px] font-mono border border-zinc-800 rounded px-2 py-1 text-accent outline-none hover:border-accent/50 cursor-pointer"
                    >
                      {LABELS.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <button
                onClick={() => setStep("context")}
                className="w-full py-3 bg-accent text-black font-bold text-xs tracking-widest uppercase rounded-lg hover:bg-accent/80 transition-all hover:scale-[1.01] active:translate-y-0.5 shadow-[0_0_15px_rgba(0,242,255,0.1)]"
              >
                COMMIT_LABELS &gt;
              </button>
            </div>
          )}

          {/* Step 3: Context */}
          {step === "context" && (
            <div className="flex-1 flex flex-col space-y-6 animate-slide-in">
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-mono text-accent uppercase tracking-widest">
                    Case_Summary_Brief
                  </label>
                  <textarea
                    value={caseSummary}
                    onChange={(e) => setCaseSummary(e.target.value)}
                    placeholder="PROVIDE_NARRATIVE_CONTEXT..."
                    className="w-full h-32 bg-black/40 border border-zinc-800 rounded-lg p-4 text-sm text-zinc-300 outline-none focus:border-accent/40 placeholder:text-zinc-700 resize-none transition-all"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-mono text-accent uppercase tracking-widest">
                    Investigative_Question
                  </label>
                  <input
                    type="text"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="ENTER_CLAIM_TO_VERIFY..."
                    className="w-full bg-black/40 border border-zinc-800 rounded-lg px-4 py-3 text-sm text-zinc-300 outline-none focus:border-accent/40 placeholder:text-zinc-700 transition-all"
                  />
                </div>
              </div>
              <button
                onClick={handleInitialize}
                disabled={
                  !caseSummary.trim() ||
                  !question.trim() ||
                  files.length === 0 ||
                  isProcessing
                }
                className="w-full py-4 bg-accent text-black font-bold text-xs tracking-widest uppercase rounded-lg hover:bg-accent/80 transition-all hover:scale-[1.01] active:translate-y-0.5 mt-auto shadow-[0_0_20px_rgba(0,242,255,0.2)] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                INITIALIZE_JUDGEMENT_PROCESSOR &gt;
              </button>
            </div>
          )}

          {/* Step 4: Processing */}
          {step === "processing" && (
            <div className="flex-1 flex flex-col items-center justify-center p-8 animate-fade-in relative">
              <div className="space-y-8 w-full max-w-md">
                <div className="flex flex-col items-center gap-4">
                  <div className="w-12 h-12 border-2 border-accent/20 border-t-accent rounded-full animate-spin"></div>
                  <h2 className="text-xl font-bold tracking-tighter glow-text text-white text-center">
                    SYSTEM_PROCESSING
                  </h2>
                </div>

                {processingError ? (
                  <div className="space-y-4">
                    <p className="text-danger text-sm font-mono text-center">
                      {processingError}
                    </p>
                    <button
                      onClick={() => {
                        setProcessingError(null);
                        setStep("context");
                      }}
                      className="w-full py-3 border border-accent/20 text-accent font-mono text-xs tracking-widest bg-accent/5 rounded hover:bg-accent/10 transition-all"
                    >
                      &lt; BACK_TO_CONTEXT
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="space-y-4">
                      {PROCESS_STAGES.map((s, i) => (
                        <div key={s} className="flex items-center gap-4">
                          <div
                            className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                              i < processingStage
                                ? "bg-success shadow-[0_0_8px_var(--success)]"
                                : i === processingStage
                                  ? "bg-accent animate-pulse"
                                  : "bg-zinc-800"
                            }`}
                          />
                          <span
                            className={`text-[10px] font-mono tracking-wider ${
                              i < processingStage
                                ? "text-success"
                                : i === processingStage
                                  ? "text-accent"
                                  : "text-zinc-600"
                            }`}
                          >
                            {s}
                          </span>
                        </div>
                      ))}
                    </div>

                    {processingStage >= 4 && !processingError && (
                      <p className="text-success text-[10px] font-mono text-center animate-pulse">
                        REDIRECTING_TO_REPORT...
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Info */}
        <div className="flex justify-between items-center text-[10px] font-mono text-zinc-600 px-4">
          <span>SECURE_SESSION: ID_294-X8</span>
          <span className="flex gap-4">
            <span>LOCAL_TIME: {new Date().toLocaleTimeString()}</span>
            <span className="text-accent/60">NODE: PRIMARY_ALPHA</span>
          </span>
        </div>
      </div>
    </main>
  );
}
