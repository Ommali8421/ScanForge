import React, { useEffect, useRef, useState } from "react";
import { Terminal, Copy, Check } from "lucide-react";

interface Props {
  logs: string[];
}

export const LogPanel: React.FC<Props> = ({ logs }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  const handleCopy = () => {
    navigator.clipboard.writeText(logs.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="border border-dark-border bg-[#070a10] rounded-2xl overflow-hidden font-mono text-xs shadow-inner">
      <div className="bg-dark-card/90 px-4 py-2.5 border-b border-dark-border flex items-center justify-between">
        <div className="flex items-center space-x-2 text-dark-muted">
          <Terminal className="w-4 h-4 text-brand-400" />
          <span className="font-semibold text-white tracking-wide">Live Process Output</span>
          <span className="text-[11px] text-dark-muted">({logs.length} lines)</span>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center space-x-1.5 px-2 py-1 rounded bg-dark-bg border border-dark-border hover:bg-dark-hover text-dark-muted hover:text-white transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          <span className="text-[11px]">{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>

      <div
        ref={containerRef}
        className="p-4 h-64 overflow-y-auto space-y-1 text-slate-300 scroll-smooth"
      >
        {logs.length === 0 ? (
          <div className="text-dark-muted italic">Waiting for process logs...</div>
        ) : (
          logs.map((log, idx) => (
            <div key={idx} className="leading-relaxed hover:bg-white/[0.02] px-1 rounded flex gap-2">
              <span className="text-dark-muted select-none opacity-40">{idx + 1}</span>
              <span className={log.includes("[Error]") ? "text-rose-400" : log.includes("[System]") ? "text-brand-300" : ""}>
                {log}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
