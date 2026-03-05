"use client";

import { MOCK_CASES, MOCK_EVIDENCE, Evidence } from "@/lib/mock-data";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useState, useEffect } from "react";

export default function CaseWorkspace() {
  const { id } = useParams();
  const caseData = MOCK_CASES.find((c) => c.id === id);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentClaim, setCurrentClaim] = useState("");

  if (!caseData) return <div className="p-20 font-mono text-danger">ERROR: CASE_NOT_FOUND</div>;

  const handleAnalize = () => {
    if (!currentClaim) return;
    setIsAnalyzing(true);
    setTimeout(() => setIsAnalyzing(false), 3000);
  };

  return (
    <main className="min-h-screen p-6 forensic-grid pb-20">
      <div className="max-w-7xl mx-auto grid grid-cols-12 gap-6">
        
        {/* Left Sidebar: Case Info & Evidence */}
        <aside className="col-span-12 lg:col-span-4 space-y-6">
          <Link href="/" className="inline-flex items-center gap-2 text-[10px] font-mono text-accent hover:underline mb-4">
            &lt; RETURN_TO_DATABASE
          </Link>

          <section className="glass-panel p-6 space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold glow-text tracking-tight">{caseData.title}</h2>
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
              Evidence_Inventory [{MOCK_EVIDENCE.length}]
            </h3>
            <div className="space-y-3">
              {MOCK_EVIDENCE.map((ev) => (
                <div key={ev.id} className="glass-panel p-4 border-l-4 border-l-accent/50 hover:border-l-accent transition-all cursor-crosshair">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-[10px] font-mono text-zinc-400 capitalize">{ev.type}</span>
                    <span className={`text-[10px] font-mono ${ev.reliability > 0.9 ? 'text-success' : 'text-warning'}`}>
                      REL:{(ev.reliability * 100).toFixed(0)}%
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-zinc-200">{ev.label}</h4>
                  <p className="text-[10px] text-zinc-500 mt-1 truncate">{ev.summary}</p>
                </div>
              ))}
            </div>
          </section>
        </aside>

        {/* Main Workspace: Fact-Check & Conflict Map */}
        <div className="col-span-12 lg:col-span-8 space-y-6">
          
          {/* Fact-Check Input */}
          <section className="glass-panel p-8 relative overflow-hidden">
            {isAnalyzing && (
              <div className="absolute inset-0 bg-accent/5 flex flex-col items-center justify-center backdrop-blur-sm z-10">
                <div className="w-12 h-12 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
                <span className="mt-4 font-mono text-accent text-xs animate-pulse">RUNNING_PLANNER_AGENT...</span>
              </div>
            )}
            
            <div className="space-y-6">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-mono text-accent uppercase tracking-widest">SUBMIT_CLAIM_FOR_VERIFICATION</h3>
                <span className="text-[10px] font-mono text-zinc-500">ENGINE: GEMINI_PRO_STATE_V1.2</span>
              </div>

              <div className="relative">
                <textarea 
                  value={currentClaim}
                  onChange={(e) => setCurrentClaim(e.target.value)}
                  placeholder="Example: The suspect was at the Harbor Pier at 11:30 PM..."
                  className="w-full h-32 bg-background/50 border border-panel-border rounded-lg p-4 font-mono text-sm text-accent focus:border-accent/50 outline-none transition-all resize-none"
                />
                <div className="absolute bottom-4 right-4 text-[10px] font-mono text-zinc-600">INPUT_BUFFER.AUTO_SAVE: ON</div>
              </div>

              <button 
                onClick={handleAnalize}
                disabled={!currentClaim || isAnalyzing}
                className="w-full py-4 bg-accent/10 border border-accent/30 text-accent font-mono text-sm uppercase tracking-tighter hover:bg-accent/20 disabled:opacity-30 disabled:pointer-events-none transition-all rounded-lg group"
              >
                EXECUTE_FACT_CHECK_PROTOCOL <span className="group-hover:translate-x-1 inline-block transition-transform">-&gt;</span>
              </button>
            </div>
          </section>

          {/* Conflict Map / Timeline visualization */}
          <section className="glass-panel p-8 space-y-6 min-h-[400px]">
             <div className="flex justify-between items-center">
                <h3 className="text-xs font-mono text-zinc-400 uppercase tracking-widest">EVIDENCE_SYNTHESIS_MATRIX</h3>
                <div className="flex gap-4">
                   <div className="flex items-center gap-2 text-[10px] font-mono text-success">
                      <div className="w-2 h-2 rounded-full bg-success"></div> CONSISTENT
                    </div>
                    <div className="flex items-center gap-2 text-[10px] font-mono text-danger">
                      <div className="w-2 h-2 rounded-full bg-danger"></div> CONTRADICTION
                    </div>
                </div>
             </div>

             {/* Placeholder for Conflict Map */}
             <div className="relative h-[300px] border border-panel-border/30 rounded bg-background/40 flex items-center justify-center">
                <div className="absolute inset-0 forensic-grid opacity-20"></div>
                
                {!isAnalyzing && !currentClaim ? (
                   <div className="text-center space-y-2 opacity-40">
                      <div className="text-4xl font-mono text-zinc-600">[!]</div>
                      <p className="text-[10px] font-mono text-zinc-500">AWAITING_INPUT_FOR_SPATIAL_MAPPING</p>
                   </div>
                ) : (
                  <div className="w-full px-8 space-y-8">
                     {/* Mocked visualization of a "Conflict" */}
                     <div className="flex items-center gap-4">
                        <div className="w-24 text-[10px] font-mono text-zinc-500">TIMELINE: 23:30</div>
                        <div className="flex-1 h-px bg-panel-border"></div>
                        <div className="px-3 py-1 bg-danger/10 border border-danger/30 text-danger text-[10px] font-mono rounded">
                           MAJOR_CONFLICT: GPS vs TESTIMONY
                        </div>
                     </div>
                     
                     <div className="grid grid-cols-2 gap-4">
                        <div className="glass-panel p-3 border-l-2 border-success">
                           <p className="text-[10px] font-mono text-success mb-1">DATA_POINT_01 (GPS)</p>
                           <p className="text-xs text-zinc-300">Subject remained at Primary Residence until 02:00.</p>
                        </div>
                        <div className="glass-panel p-3 border-l-2 border-danger">
                           <p className="text-[10px] font-mono text-danger mb-1">TESTIMONY_04 (HUMAN)</p>
                           <p className="text-xs text-zinc-300">"I saw him leave at midnight."</p>
                        </div>
                     </div>

                     <div className="text-center font-mono text-[10px] text-accent animate-pulse">
                        &gt; JUDGE_AGENT: "Testimony reliability (0.60) downgraded due to high-precision GPS (0.95)"
                     </div>
                  </div>
                )}
             </div>
          </section>
        </div>
      </div>
    </main>
  );
}
