import React from "react";
import { PlusCircle, List, BookOpen, Sun, Moon } from "lucide-react";
import { Capabilities } from "../api/types";
import { useTheme } from "../context/ThemeContext";
import { useGuide } from "../context/GuideContext";

interface Props {
  activeTab: "new" | "jobs";
  setActiveTab: (tab: "new" | "jobs") => void;
  capabilities: Capabilities | null;
}

export const Header: React.FC<Props> = ({ activeTab, setActiveTab, capabilities }) => {
  const { theme, toggleTheme } = useTheme();
  const { guideEnabled, toggleGuide, openGuideModal } = useGuide();
  const isMock = capabilities?.engine === "mock";

  return (
    <header className="border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-40 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand Logo & Name */}
        <div
          className="flex items-center space-x-3 cursor-pointer select-none group"
          onClick={() => setActiveTab("jobs")}
        >
          {/* Custom Geometric 3D SVG Logo */}
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform">
            <svg
              className="w-5 h-5 text-white"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {/* Geometric 3D spatial cube / forge polyhedron */}
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-black tracking-tight text-white flex items-center gap-1.5 font-sans">
                ScanForge
              </span>
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Studio
              </span>
            </div>
            <p className="text-[11px] text-zinc-400 hidden sm:block">
              Spatial 3D Reconstruction Platform
            </p>
          </div>
        </div>

        {/* Center / Navigation Tabs */}
        <nav className="flex space-x-1 bg-zinc-900/80 p-1 rounded-2xl border border-zinc-800">
          <button
            onClick={() => setActiveTab("new")}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              activeTab === "new"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
          >
            <PlusCircle className="w-4 h-4" />
            <span>New Scan</span>
          </button>
          <button
            onClick={() => setActiveTab("jobs")}
            className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all ${
              activeTab === "jobs"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
          >
            <List className="w-4 h-4" />
            <span>Jobs Library</span>
          </button>
        </nav>

        {/* Right Controls: Engine Badge, Guide Toggle, How It Works, Theme */}
        <div className="flex items-center space-x-2.5">
          {/* Engine Status Badge */}
          <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-xl border border-zinc-800 bg-zinc-900/60 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                isMock ? "bg-amber-400 animate-pulse" : "bg-emerald-400 shadow-sm shadow-emerald-400/50"
              }`}
            />
            <span className="text-zinc-400">Engine:</span>
            <span
              className={`font-semibold font-mono text-[11px] ${
                isMock ? "text-amber-400" : "text-emerald-400"
              }`}
            >
              {isMock ? "Mock Mode" : "GPU Engine Ready"}
            </span>
          </div>

          {/* Interactive Guide Toggle */}
          <button
            onClick={toggleGuide}
            className={`flex items-center space-x-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
              guideEnabled
                ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-300 shadow-sm shadow-emerald-500/10"
                : "bg-zinc-900/60 border-zinc-800 text-zinc-400 hover:text-zinc-200"
            }`}
            title={guideEnabled ? "Guide Mode is Active (Click to hide hints)" : "Guide Mode is OFF (Click to enable hints)"}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                guideEnabled ? "bg-emerald-400 animate-pulse" : "bg-zinc-500"
              }`}
            />
            <span>Guide: {guideEnabled ? "ON" : "OFF"}</span>
          </button>

          {/* How It Works Modal Trigger */}
          <button
            onClick={() => openGuideModal()}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800/80 text-zinc-300 hover:text-white transition-colors"
            title="Open Interactive User Guide"
          >
            <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">How It Works</span>
          </button>

          {/* Dark / Light Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-xl border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800/80 text-zinc-400 hover:text-white transition-colors"
            title={theme === "dark" ? "Switch to light app shell" : "Switch to dark app shell"}
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-indigo-400" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
};
