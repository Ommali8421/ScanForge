import React from "react";
import { QualityPreset } from "../api/types";
import { Zap, ShieldCheck, Flame, Check } from "lucide-react";
import { SmartHint } from "./SmartHint";

interface Props {
  selected: QualityPreset;
  onSelect: (preset: QualityPreset) => void;
}

export const QualitySelect: React.FC<Props> = ({ selected, onSelect }) => {
  const presets: {
    id: QualityPreset;
    label: string;
    sublabel: string;
    specs: string;
    icon: React.ComponentType<{ className?: string }>;
    tag?: string;
  }[] = [
    {
      id: "draft",
      label: "Draft",
      sublabel: "Fast Sanity Check",
      specs: "1200 px • ~50k faces • ~2 min",
      icon: Zap,
    },
    {
      id: "standard",
      label: "Standard",
      sublabel: "8 GB VRAM Sweet Spot",
      specs: "1600 px • ~200k faces • Balanced",
      icon: ShieldCheck,
      tag: "Recommended",
    },
    {
      id: "high",
      label: "High",
      sublabel: "Maximum Fidelity",
      specs: "2000 px • ~500k+ faces • Full Mesh",
      icon: Flame,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 p-1.5 rounded-2xl bg-zinc-950/80 border border-zinc-800">
        {presets.map((p) => {
          const Icon = p.icon;
          const isSelected = selected === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onSelect(p.id)}
              className={`p-3.5 rounded-xl text-left transition-all relative flex flex-col justify-between ${
                isSelected
                  ? "bg-gradient-to-br from-indigo-950/60 to-zinc-900 border border-indigo-500/60 shadow-lg shadow-indigo-500/10 text-white"
                  : "hover:bg-zinc-900/60 text-zinc-400 hover:text-zinc-200 border border-transparent"
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <Icon
                      className={`w-4 h-4 ${
                        isSelected ? "text-cyan-400" : "text-zinc-500"
                      }`}
                    />
                    <span className="text-xs font-bold text-white tracking-tight">
                      {p.label}
                    </span>
                  </div>

                  {p.tag && (
                    <span className="text-[9px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      {p.tag}
                    </span>
                  )}
                  {isSelected && !p.tag && (
                    <div className="w-4 h-4 rounded-full bg-indigo-500 text-white flex items-center justify-center">
                      <Check className="w-2.5 h-2.5 stroke-[3]" />
                    </div>
                  )}
                </div>

                <div className="text-[11px] text-zinc-400 font-medium">{p.sublabel}</div>
              </div>

              <div className="text-[10px] font-mono text-zinc-500 mt-2.5 pt-2 border-t border-zinc-800/60 tabular-nums">
                {p.specs}
              </div>
            </button>
          );
        })}
      </div>

      <SmartHint
        topic="Quality Preset Guidance"
        hint="Standard is tuned specifically for 8 GB VRAM (RTX 4060) to prevent CUDA out-of-memory errors while preserving sub-millimeter interior sharpness."
        guideTab={3}
      />
    </div>
  );
};
