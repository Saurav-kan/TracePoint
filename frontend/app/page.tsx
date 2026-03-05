import { MOCK_CASES } from "@/lib/mock-data";
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen p-8 forensic-grid">
      <div className="max-w-6xl mx-auto space-y-12">
        {/* Header Section */}
        <header className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-8 border-b border-panel-border">
          <div className="space-y-4">
            <div className="inline-block px-3 py-1 text-xs font-mono tracking-widest uppercase bg-accent-muted text-accent border border-accent/30 rounded">
              System Active // Neural Link Established
            </div>
            <h1 className="text-5xl font-bold tracking-tighter glow-text font-sans">
              TRACE<span className="text-accent underline decoration-accent/50 underline-offset-8">POINT</span>
            </h1>
            <p className="text-zinc-400 font-mono text-sm max-w-xl">
              ADVANCED INVESTIGATIVE FACT-CHECKING RAG (AF-RAG) 
              <br />
              VERIFYING CLAIMS AGAINST DISPARATE EVIDENCE MATRICES.
            </p>
          </div>
          
          <div className="flex gap-4">
            <button className="px-6 py-2 bg-accent/10 border border-accent/20 text-accent font-mono text-sm hover:bg-accent/20 transition-all rounded">
              NEW_INVESTIGATION.EXE
            </button>
          </div>
        </header>

        {/* Case Selection Grid */}
        <section className="space-y-6">
          <div className="flex items-center gap-4 text-xs font-mono text-zinc-500 uppercase tracking-widest">
            <span className="w-8 h-px bg-zinc-800"></span>
            Active Cases Database
            <span className="w-full h-px bg-zinc-800"></span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {MOCK_CASES.map((caseItem) => (
              <Link 
                key={caseItem.id} 
                href={`/case/${caseItem.id}`}
                className="group relative block p-px rounded-lg overflow-hidden transition-all hover:scale-[1.02]"
              >
                {/* Glow Backdrop */}
                <div className="absolute inset-0 bg-gradient-to-br from-accent/20 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                
                <div className="relative h-full glass-panel p-6 space-y-4">
                  <div className="flex justify-between items-start">
                    <span className="text-[10px] font-mono text-accent bg-accent/5 px-2 py-0.5 border border-accent/20 rounded">
                      ID_{caseItem.id.toUpperCase()}
                    </span>
                    <span className={`text-[10px] font-mono px-2 py-0.5 border rounded uppercase ${
                      caseItem.priority === 'high' ? 'text-danger border-danger/30 bg-danger/5' : 'text-warning border-warning/30 bg-warning/5'
                    }`}>
                      {caseItem.priority}_PRIORITY
                    </span>
                  </div>

                  <div>
                    <h3 className="text-xl font-bold text-white group-hover:text-accent transition-colors">
                      {caseItem.title}
                    </h3>
                    <p className="mt-2 text-sm text-zinc-400 leading-relaxed line-clamp-2">
                      {caseItem.brief}
                    </p>
                  </div>

                  <div className="pt-4 border-t border-panel-border flex justify-between items-center text-[10px] font-mono text-zinc-500">
                    <span>DATE: {caseItem.date}</span>
                    <span className="group-hover:text-accent transition-colors">INITIALIZE_LINK &gt;</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </section>

        {/* Bottom Status Bar */}
        <footer className="fixed bottom-0 left-0 right-0 h-10 glass-panel border-t border-panel-border flex items-center justify-between px-6 text-[10px] font-mono text-zinc-500 z-50">
          <div className="flex gap-6 items-center">
            <span className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-success crt-flicker"></span>
              SECURE_LINK: ENCRYPTED
            </span>
            <span>UPLINK_SPEED: 842.2 GB/S</span>
            <span className="text-accent/60">NODE: TRACE_PRIMARY_ALPHA</span>
          </div>
          <div className="hidden md:block">
            LATENCY: 12ms // PACKET_LOSS: 0.00%
          </div>
        </footer>
      </div>
    </main>
  );
}
