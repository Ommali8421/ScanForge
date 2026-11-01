import React from "react";
import { JobReport } from "../api/types";
import { Home, CheckCircle, AlertTriangle } from "lucide-react";


interface Props {
  report: JobReport | null;
}

export const QualityReport: React.FC<Props> = ({ report }) => {
  if (!report) return null;

  const isCalibrated = report.is_calibrated || report.cumulative_scale !== 1.0;
  const unitLabel = isCalibrated ? "m" : " units";
  const areaUnit = isCalibrated ? "m²" : " units²";

  return (
    <div className="bg-dark-card border border-dark-border rounded-2xl p-5 shadow-lg space-y-4">
      <div className="flex flex-wrap items-center justify-between border-b border-dark-border pb-3 gap-2">
        <div className="flex items-center space-x-2">
          <Home className="w-5 h-5 text-brand-400" />
          <h3 className="text-sm font-semibold text-white">Interior Metrics & Quality Report</h3>
        </div>

        <div className="flex items-center space-x-2">
          {isCalibrated ? (
            <span className="text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 px-2 py-0.5 rounded-full flex items-center gap-1 font-medium">
              <CheckCircle className="w-3.5 h-3.5" />
              Metric Calibrated
            </span>
          ) : (
            <span className="text-xs text-amber-400 bg-amber-950/40 border border-amber-800/50 px-2.5 py-0.5 rounded-full flex items-center gap-1 font-medium">
              <AlertTriangle className="w-3.5 h-3.5" />
              Arbitrary SfM units — calibrate scale for meters
            </span>
          )}

          {report.quality_grade && (
            <span className="text-xs text-brand-300 bg-brand-950/40 border border-brand-800/50 px-2 py-0.5 rounded-full font-mono font-semibold">
              Grade {report.quality_grade}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Room Dimensions (L × W × H)</span>
          <span className="text-sm font-bold text-white font-mono">
            {report.dimensions_meters.length}{unitLabel} × {report.dimensions_meters.width}{unitLabel} × {report.dimensions_meters.height}{unitLabel}
          </span>
        </div>

        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Estimated Floor Area</span>
          <span className="text-sm font-bold text-emerald-400 font-mono">
            {report.floor_area_sqm} {areaUnit}
          </span>
        </div>

        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Mesh Density</span>
          <span className="text-sm font-bold text-white font-mono">
            {report.face_count.toLocaleString()} faces
          </span>
          <span className="text-[10px] text-dark-muted block mt-0.5">
            {report.vertex_count.toLocaleString()} vertices
          </span>
        </div>

        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Scale & Topology</span>
          <span className="text-sm font-bold text-brand-400 font-mono">
            {report.cumulative_scale.toFixed(3)}x
          </span>
          <span className="text-[10px] text-dark-muted block mt-0.5">
            {report.is_watertight ? "Watertight Manifold" : "Planar Open Boundaries"}
          </span>
        </div>
      </div>
    </div>
  );
};
