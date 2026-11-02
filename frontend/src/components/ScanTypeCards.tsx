import React from "react";
import { Camera, Sparkles, Radar, Check } from "lucide-react";
import { ScanType } from "../api/types";
import { SmartHint } from "./SmartHint";

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
      subtitle: "Textured 3D Mesh",
      desc: "SfM + MVS pipeline optimized for interior spaces. Produces flat walls, leveled floor, and clean PBR materials.",
      icon: Camera,
      badge: "Primary",
      deliverables: "GLB, OBJ, FBX, USDZ",
      disabled: false,
    },
    {
      id: "gaussian_splat" as ScanType,
      title: "3DGS Scan",
      subtitle: "Gaussian Radiance Field",
      desc: "Photorealistic 3D Gaussian Splats capturing lighting, mirror reflections, and fine clutter at 60 fps.",
      icon: Sparkles,
      badge: "Core",
      deliverables: ".splat, SPZ, PLY",
      disabled: false,
    },
    {
      id: "lidar" as ScanType,
      title: "LiDAR Scan",
      subtitle: "Direct RGB-D Sensor",
      desc: "Instant TSDF fusion from iOS Record3D .r3d or RGB-D archives with hardware metric depth.",
      icon: Radar,
      badge: lidarEnabled ? "Active" : "Beta · Needs RGB-D",
      deliverables: "Metric GLB, PLY",
      disabled: !lidarEnabled,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {options.map((opt) => {
          const Icon = opt.icon;
          const isSelected = selected === opt.id;
          return (
            <div
              key={opt.id}
              onClick={() => !opt.disabled && onSelect(opt.id)}
              className={`relative p-5 rounded-3xl border transition-all duration-200 flex flex-col justify-between ${
                opt.disabled
                  ? "opacity-50 cursor-not-allowed border-zinc-800 bg-zinc-950/40"
                  : isSelected
                  ? "cursor-pointer border-indigo-500/80 bg-indigo-950/20 shadow-xl shadow-indigo-500/10 ring-1 ring-indigo-500/50"
                  : "cursor-pointer border-zinc-800/80 bg-zinc-950/60 hover:border-zinc-700 hover:bg-zinc-900/60"
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div
                    className={`w-10 h-10 rounded-2xl flex items-center justify-center transition-colors ${
                      isSelected
                        ? "bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white shadow-md shadow-indigo-500/20"
                        : "bg-zinc-900 text-zinc-400 border border-zinc-800"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span
                      className={`text-[10px] font-mono font-bold tracking-wider px-2.5 py-0.5 rounded-full border ${
                        isSelected
                          ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/30 uppercase"
                          : opt.disabled
                          ? "bg-amber-500/10 text-amber-300/80 border-amber-500/20"
                          : "bg-zinc-900 text-zinc-400 border-zinc-800 uppercase"
                      }`}
                    >
                      {opt.badge}
                    </span>
                    {isSelected && (
                      <div className="w-5 h-5 rounded-full bg-indigo-500 text-white flex items-center justify-center">
                        <Check className="w-3 h-3 stroke-[3]" />
                      </div>
                    )}
                  </div>
                </div>

                <h4 className="text-sm font-bold text-white tracking-tight">{opt.title}</h4>
                <div className="text-[11px] font-medium text-indigo-400 dark:text-cyan-400 mb-2">
                  {opt.subtitle}
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed line-clamp-3">
                  {opt.desc}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-zinc-800/60 text-[11px] font-mono text-zinc-500 flex items-center justify-between">
                <span>Outputs:</span>
                <span className="text-zinc-300">{opt.deliverables}</span>
              </div>
            </div>
          );
        })}
      </div>

      <SmartHint
        topic="Scan Mode Guidance"
        hint="Photo Scan produces flat-walled meshes for Blender, CAD, and 3D printing. 3DGS produces photorealistic visual walkthroughs with real-time reflections."
        guideTab={1}
      />
    </div>
  );
};
