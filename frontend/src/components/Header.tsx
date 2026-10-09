import React from "react";
import { Box, PlusCircle, List, Cpu } from "lucide-react";
import { Capabilities } from "../api/types";

interface Props {
  activeTab: "new" | "jobs";
  setActiveTab: (tab: "new" | "jobs") => void;
  capabilities: Capabilities | null;
}

export const Header: React.FC<Props> = ({ activeTab, setActiveTab, capabilities }) => {
  const isMock = capabilities?.engine === "mock";

  return (
    <header className="border-b border-dark-border bg-dark-bg/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setActiveTab("jobs")}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-brand-500/20">
            <Box className="w-6 h-6 text-white" />
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              ScanForge
              <span className="text-[10px] font-semibold uppercase tracking-widest px-2 py-0.5 rounded bg-brand-500/10 text-brand-400 border border-brand-500/20">
                v0.1
              </span>
            </span>
            <p className="text-xs text-dark-muted hidden sm:block">Interior 3D Reconstruction Platform</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <nav className="flex space-x-1 bg-dark-card p-1 rounded-xl border border-dark-border">
            <button
              onClick={() => setActiveTab("new")}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === "new"
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-dark-muted hover:text-dark-text hover:bg-dark-hover"
              }`}
            >
              <PlusCircle className="w-4 h-4" />
              <span>New Scan</span>
            </button>
            <button
              onClick={() => setActiveTab("jobs")}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === "jobs"
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-dark-muted hover:text-dark-text hover:bg-dark-hover"
              }`}
            >
              <List className="w-4 h-4" />
              <span>Scans List</span>
            </button>
          </nav>

          <div className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-dark-border bg-dark-card text-xs text-dark-muted">
            <Cpu className="w-3.5 h-3.5 text-brand-400" />
            <span>Engine:</span>
            <span className={`font-semibold ${isMock ? "text-amber-400" : "text-emerald-400"}`}>
              {isMock ? "Mock Engine" : "NVIDIA GPU"}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};
