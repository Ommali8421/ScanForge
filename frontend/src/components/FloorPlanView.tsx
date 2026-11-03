import React, { useState } from "react";
import { Compass, Download, Maximize2, CheckCircle2, AlertCircle } from "lucide-react";
import { JobReport } from "../api/types";

interface FloorPlanViewProps {
  jobId: string;
  report: JobReport | null;
  cumulativeScale?: number;
}

export const FloorPlanView: React.FC<FloorPlanViewProps> = ({
  jobId,
  report,
  cumulativeScale = 1.0,
}) => {
  const [viewMode, setViewMode] = useState<"svg" | "png">("svg");
  const [isFullscreen, setIsFullscreen] = useState(false);

  const svgUrl = `/api/jobs/${jobId}/artifacts/floor_plan.svg`;
  const pngUrl = `/api/jobs/${jobId}/artifacts/floor_plan.png`;

  const isCalibrated = report?.is_calibrated || cumulativeScale !== 1.0;
  const dims = report?.dimensions_meters || { length: 5.0, width: 4.0, height: 2.6 };
  const area = report?.floor_area_sqm || dims.length * dims.width * 0.65;
  const unitLabel = isCalibrated ? "m" : "units";
  const areaLabel = isCalibrated ? "m²" : "sq units";

  return (
    <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-2xl space-y-5">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <Compass className="w-5 h-5 text-cyan-400" />
            <h3 className="text-base font-bold text-white tracking-tight uppercase">
              2D Architectural Floor Plan
            </h3>
            {isCalibrated ? (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center gap-1 font-mono">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Metric Calibrated
              </span>
            ) : (
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center gap-1 font-mono">
                <AlertCircle className="w-3.5 h-3.5" />
                Arbitrary SfM Scale
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Horizontal cross-section sliced at eye level with wall boundary extraction and dimension callouts.
          </p>
        </div>

        {/* View Mode & Actions */}
        <div className="flex items-center space-x-2 self-start sm:self-auto">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-1 flex items-center space-x-1">
            <button
              onClick={() => setViewMode("svg")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                viewMode === "svg"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Vector (SVG)
            </button>
            <button
              onClick={() => setViewMode("png")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                viewMode === "png"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Raster (PNG)
            </button>
          </div>

          <a
            href={viewMode === "svg" ? svgUrl : pngUrl}
            download={`floor_plan_${jobId.substring(0, 8)}.${viewMode}`}
            className="p-2 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 hover:text-white transition-colors"
            title="Download Floor Plan"
          >
            <Download className="w-4 h-4" />
          </a>

          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-2 rounded-xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-300 hover:text-white transition-colors"
            title="Toggle Expanded View"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Dimension KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-3.5">
          <span className="text-[10px] uppercase font-bold text-zinc-500 block">Length (X)</span>
          <span className="text-sm sm:text-base font-black text-cyan-400 font-mono">
            {dims.length.toFixed(2)} {unitLabel}
          </span>
        </div>
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-3.5">
          <span className="text-[10px] uppercase font-bold text-zinc-500 block">Width (Z)</span>
          <span className="text-sm sm:text-base font-black text-indigo-400 font-mono">
            {dims.width.toFixed(2)} {unitLabel}
          </span>
        </div>
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-3.5">
          <span className="text-[10px] uppercase font-bold text-zinc-500 block">Height (Y)</span>
          <span className="text-sm sm:text-base font-black text-zinc-300 font-mono">
            {dims.height.toFixed(2)} {unitLabel}
          </span>
        </div>
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-3.5">
          <span className="text-[10px] uppercase font-bold text-zinc-500 block">Total Floor Area</span>
          <span className="text-sm sm:text-base font-black text-emerald-400 font-mono">
            ~{area.toFixed(2)} {areaLabel}
          </span>
        </div>
      </div>

      {/* Main Floor Plan Canvas */}
      <div
        className={`relative w-full rounded-2xl border border-zinc-800/80 bg-[#0A0D14] overflow-hidden flex items-center justify-center transition-all ${
          isFullscreen ? "h-[750px]" : "h-[480px]"
        }`}
      >
        {viewMode === "svg" ? (
          <object
            data={svgUrl}
            type="image/svg+xml"
            className="w-full h-full object-contain p-4 select-none"
          >
            <img src={pngUrl} alt="2D Architectural Floor Plan" className="w-full h-full object-contain p-4" />
          </object>
        ) : (
          <img
            src={pngUrl}
            alt="2D Architectural Floor Plan"
            className="w-full h-full object-contain p-4"
          />
        )}
      </div>
    </div>
  );
};
