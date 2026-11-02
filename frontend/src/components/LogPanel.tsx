import React, { useEffect, useRef, useState } from "react";
import { Terminal, Copy, Check, Download, ArrowDown } from "lucide-react";

interface Props {
  logs: string[];
  jobId?: string;
}

export const LogPanel: React.FC<Props> = ({ logs, jobId }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleCopy = () => {
    navigator.clipboard.writeText(logs.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="border border-zinc-800 bg-[#07090e] rounded-3xl overflow-hidden font-mono text-xs shadow-2xl">
      <div className="bg-zinc-900/90 px-5 py-3 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <span className="font-bold text-white tracking-wide">Live Process Telemetry</span>
          <span className="text-[11px] text-zinc-400">({logs.length} lines)</span>
        </div>

        <div className="flex items-center space-x-2">
          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-xl border text-[11px] transition-colors ${
              autoScroll
                ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-300"
                : "bg-zinc-900 border-zinc-800 text-zinc-500 hover:text-zinc-300"
            }`}
            title={autoScroll ? "Auto-scroll is ON" : "Auto-scroll is paused"}
          >
            <ArrowDown className="w-3 h-3" />
            <span>Auto-Scroll</span>
          </button>

          {jobId && (
            <a
              href={`/api/jobs/${jobId}/log`}
              download={`scanforge_${jobId.slice(0, 8)}_full.log`}
              className="flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors text-[11px]"
              title="Download full process log"
            >
              <Download className="w-3.5 h-3.5 text-indigo-400" />
              <span className="hidden sm:inline">Full Log</span>
            </a>
          )}

          <button
            onClick={handleCopy}
            className="flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors text-[11px]"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="p-5 h-72 overflow-y-auto space-y-1 text-zinc-300 scroll-smooth leading-relaxed"
      >
        {logs.length === 0 ? (
          <div className="text-zinc-600 italic">Waiting for pipeline execution logs...</div>
        ) : (
          logs.map((log, idx) => (
            <div
              key={idx}
              className="hover:bg-white/[0.03] px-1.5 py-0.5 rounded flex gap-3 text-[11.5px]"
            >
              <span className="text-zinc-600 select-none opacity-50 w-7 text-right flex-shrink-0 tabular-nums">
                {idx + 1}
              </span>
              <span
                className={
                  log.includes("[Error]") || log.toLowerCase().includes("failed") || log.toLowerCase().includes("error")
                    ? "text-rose-400 font-semibold"
                    : log.includes("[System]") || log.toLowerCase().includes("stage")
                    ? "text-cyan-300 font-medium"
                    : log.toLowerCase().includes("completed") || log.toLowerCase().includes("success")
                    ? "text-emerald-300"
                    : "text-zinc-300"
                }
              >
                {log}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
