import React from "react";
import { JobReport } from "../api/types";
import { Home, CheckCircle, AlertTriangle, Ruler } from "lucide-react";

interface Props {
  report: JobReport | null;
  onActivateMeasure?: () => void;
}

export const QualityReport: React.FC<Props> = ({ report, onActivateMeasure }) => {
  if (!report) return null;

  const isCalibrated = report.is_calibrated || report.cumulative_scale !== 1.0;
  const unitLabel = isCalibrated ? "m" : " units";
  const areaUnit = isCalibrated ? "m²" : " units²";

  return (
    <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-5">
      {/* Header with Title and Calibrated Badge */}
      <div className="flex flex-wrap items-center justify-between border-b border-zinc-800/80 pb-4 gap-3">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-600 to-indigo-600 text-white flex items-center justify-center shadow-lg shadow-cyan-600/20">
            <Home className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">
              Architectural Quality & Spatial Telemetry
            </h3>
            <p className="text-xs text-zinc-400">
              Planar bounding volume, floor area, and manifold topology metrics
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {isCalibrated ? (
            <span className="text-xs text-emerald-300 bg-emerald-950/50 border border-emerald-500/40 px-3 py-1 rounded-full flex items-center gap-1.5 font-bold shadow-sm">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              <span>Metric Calibrated</span>
            </span>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs text-amber-300 bg-amber-950/40 border border-amber-500/40 px-3 py-1 rounded-full flex items-center gap-1.5 font-medium">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                <span>Arbitrary SfM Units</span>
              </span>
              {onActivateMeasure && (
                <button
                  onClick={onActivateMeasure}
                  className="text-xs text-cyan-400 hover:text-cyan-300 bg-cyan-950/30 border border-cyan-500/30 px-2.5 py-1 rounded-full flex items-center gap-1 font-semibold hover:bg-cyan-950/50 transition-colors"
                >
                  <Ruler className="w-3 h-3" />
                  <span>Calibrate Scale</span>
                </button>
              )}
            </div>
          )}

          {report.quality_grade && (
            <span
              className={`text-xs px-2.5 py-1 rounded-full font-mono font-bold border shadow-sm ${
                report.quality_grade === "A"
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                  : report.quality_grade === "B"
                  ? "bg-cyan-500/10 text-cyan-400 border-cyan-500/30"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/30"
              }`}
            >
              Grade {report.quality_grade}
            </span>
          )}
        </div>
      </div>

      {/* 4-Column Architectural Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 text-center">
        {/* Room Dimensions */}
        <div className="bg-zinc-900/60 p-4 rounded-2xl border border-zinc-800/80 shadow-inner flex flex-col justify-between">
          <span className="text-[11px] text-zinc-400 font-medium block mb-1">
            Room Dimensions (L × W × H)
          </span>
          <div className="text-base font-extrabold text-white font-mono tracking-tight tabular-nums my-1">
            {report.dimensions_meters.length.toFixed(2)}{unitLabel} ×{" "}
            {report.dimensions_meters.width.toFixed(2)}{unitLabel} ×{" "}
            {report.dimensions_meters.height.toFixed(2)}{unitLabel}
          </div>
          <span className="text-[10px] text-zinc-500 block">
            Axis: {report.up_axis.toUpperCase()}-Up Aligned
          </span>
        </div>

        {/* Floor Area */}
        <div className="bg-zinc-900/60 p-4 rounded-2xl border border-zinc-800/80 shadow-inner flex flex-col justify-between">
          <span className="text-[11px] text-zinc-400 font-medium block mb-1">
            Estimated Floor Area
          </span>
          <div className="text-xl font-black text-cyan-400 font-mono tracking-tight tabular-nums my-1">
            {report.floor_area_sqm.toFixed(2)} {areaUnit}
          </div>
          <span className="text-[10px] text-zinc-500 block">
            RANSAC planar floor projection
          </span>
        </div>

        {/* Mesh Density or Splat Density */}
        {report.gaussian_count != null ? (
          <div className="bg-zinc-900/60 p-4 rounded-2xl border border-zinc-800/80 shadow-inner flex flex-col justify-between">
            <span className="text-[11px] text-zinc-400 font-medium block mb-1">
              Splat Density
            </span>
            <div className="text-base font-bold text-white font-mono tabular-nums my-1">
              {report.gaussian_count.toLocaleString()} splats
            </div>
            <span className="text-[10px] text-zinc-400 font-mono block">
              {report.raw_gaussian_count
                ? `${report.raw_gaussian_count.toLocaleString()} raw (${report.retention_pct ?? 100}% kept)`
                : "Cleaned Gaussians"}
            </span>
          </div>
        ) : (
          <div className="bg-zinc-900/60 p-4 rounded-2xl border border-zinc-800/80 shadow-inner flex flex-col justify-between">
            <span className="text-[11px] text-zinc-400 font-medium block mb-1">
              Mesh Topology
            </span>
            <div className="text-base font-bold text-white font-mono tabular-nums my-1">
              {report.face_count.toLocaleString()} faces
            </div>
            <span className="text-[10px] text-zinc-400 font-mono block">
              {report.vertex_count.toLocaleString()} vertices
            </span>
          </div>
        )}

        {/* Scale & Manifold Integrity or Splat Envelope */}
        {report.gaussian_count != null ? (
          <div className="bg-zinc-900/60 p-4 rounded-2xl border border-zinc-800/80 shadow-inner flex flex-col justify-between">
            <span className="text-[11px] text-zinc-400 font-medium block mb-1">
              Spatial Envelope
            </span>
            <div className="text-base font-bold text-indigo-300 font-mono tabular-nums my-1">
              {report.cumulative_scale.toFixed(3)}x Scale
            </div>
            <span className="text-[10px] text-emerald-400 font-medium block">
              Upright Y=0 Floor Aligned
            </span>
          </div>
        ) : (
          <div className="bg-zinc-900/60 p-4 rounded-2xl border border-zinc-800/80 shadow-inner flex flex-col justify-between">
            <span className="text-[11px] text-zinc-400 font-medium block mb-1">
              Manifold Integrity
            </span>
            <div className="text-base font-bold text-indigo-300 font-mono tabular-nums my-1">
              {report.cumulative_scale.toFixed(3)}x Scale
            </div>
            <span className="text-[10px] text-emerald-400 font-medium block">
              {report.is_watertight ? "Watertight Manifold" : "Planar Open Boundaries"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
