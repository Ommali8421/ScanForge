import React from "react";
import { QualityPreset } from "../api/types";

interface Props {
  selected: QualityPreset;
  onSelect: (preset: QualityPreset) => void;
}

export const QualitySelect: React.FC<Props> = ({ selected, onSelect }) => {
  const presets: { id: QualityPreset; label: string; desc: string }[] = [
    { id: "draft", label: "Draft", desc: "Fast (1200px, 50k faces)" },
    { id: "standard", label: "Standard", desc: "Balanced (1600px, 200k faces)" },
    { id: "high", label: "High", desc: "Maximum detail (2000px, 1M faces)" },
  ];

  return (
    <div className="grid grid-cols-3 gap-2 bg-dark-bg p-1.5 rounded-xl border border-dark-border">
      {presets.map((p) => {
        const isSelected = selected === p.id;
        return (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            className={`py-2 px-3 rounded-lg text-left transition-all ${
              isSelected
                ? "bg-dark-card border border-brand-500/50 shadow-sm text-white"
                : "text-dark-muted hover:text-dark-text hover:bg-dark-hover"
            }`}
          >
            <div className="text-xs font-semibold">{p.label}</div>
            <div className="text-[10px] text-dark-muted truncate hidden sm:block">{p.desc}</div>
          </button>
        );
      })}
    </div>
  );
};
