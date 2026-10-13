import React from "react";
import { Camera, Sparkles, Radar } from "lucide-react";
import { ScanType } from "../api/types";

interface Props {
  selected: ScanType;
  onSelect: (type: ScanType) => void;
  lidarEnabled: boolean;
}

export const ScanTypeCards: React.FC<Props> = ({ selected, onSelect, lidarEnabled }) => {
  const options = [
    {
      id: "photo" as ScanType,
      title: "Photo Scan",
      desc: "High-precision photogrammetry (COLMAP + OpenMVS / Depth fusion) tailored for interior meshes.",
      icon: Camera,
      badge: "Primary",
      disabled: false,
    },
    {
      id: "gaussian_splat" as ScanType,
      title: "3DGS Scan",
      desc: "Fast, photorealistic 3D Gaussian Splats with optional extracted mesh.",
      icon: Sparkles,
      badge: "Core",
      disabled: false,
    },
    {
      id: "lidar" as ScanType,
      title: "LiDAR Scan",
      desc: "Direct RGB-D and Record3D integration with metric TSDF fusion.",
      icon: Radar,
      badge: lidarEnabled ? "Beta" : "Beta, needs RGB-D capture",
      disabled: !lidarEnabled,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {options.map((opt) => {
        const Icon = opt.icon;
        const isSelected = selected === opt.id;
        return (
          <div
            key={opt.id}
            onClick={() => !opt.disabled && onSelect(opt.id)}
            className={`relative p-4 rounded-2xl border transition-all ${
              opt.disabled
                ? "opacity-60 cursor-not-allowed border-dark-border bg-dark-card/40"
                : isSelected
                ? "cursor-pointer border-brand-500 bg-brand-500/10 shadow-lg shadow-brand-500/10 ring-1 ring-brand-500"
                : "cursor-pointer border-dark-border bg-dark-card hover:border-slate-600 hover:bg-dark-hover"
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div
                className={`w-9 h-9 rounded-xl flex items-center justify-center ${
                  isSelected ? "bg-brand-500 text-white" : "bg-dark-bg text-dark-muted border border-dark-border"
                }`}
              >
                <Icon className="w-4 h-4" />
              </div>
              <span
                className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full border ${
                  isSelected
                    ? "bg-brand-500/20 text-brand-300 border-brand-500/30 uppercase"
                    : opt.disabled
                    ? "bg-amber-500/10 text-amber-300/90 border-amber-500/20"
                    : "bg-dark-bg text-dark-muted border-dark-border uppercase"
                }`}
              >
                {opt.badge}
              </span>
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">{opt.title}</h3>
            <p className="text-xs text-dark-muted line-clamp-2 leading-relaxed">{opt.desc}</p>
          </div>
        );
      })}
    </div>
  );
};
