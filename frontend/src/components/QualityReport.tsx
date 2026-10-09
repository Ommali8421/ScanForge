import React from "react";
import { JobReport } from "../api/types";
import { Home, CheckCircle } from "lucide-react";


interface Props {
  report: JobReport | null;
}

export const QualityReport: React.FC<Props> = ({ report }) => {
  if (!report) return null;

  return (
    <div className="bg-dark-card border border-dark-border rounded-2xl p-5 shadow-lg space-y-4">
      <div className="flex items-center justify-between border-b border-dark-border pb-3">
        <div className="flex items-center space-x-2">
          <Home className="w-5 h-5 text-brand-400" />
          <h3 className="text-sm font-semibold text-white">Interior Metrics & Quality Report</h3>
        </div>
        <span className="text-xs text-emerald-400 flex items-center gap-1 font-medium">
          <CheckCircle className="w-3.5 h-3.5" />
          Planar Watertight
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Estimated Dimensions</span>
          <span className="text-sm font-bold text-white font-mono">
            {report.dimensions_meters.length}m × {report.dimensions_meters.width}m × {report.dimensions_meters.height}m
          </span>
        </div>

        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Floor Area</span>
          <span className="text-sm font-bold text-emerald-400 font-mono">
            {report.floor_area_sqm} m²
          </span>
        </div>

        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Polycount</span>
          <span className="text-sm font-bold text-white font-mono">
            {report.face_count.toLocaleString()} faces
          </span>
        </div>

        <div className="bg-dark-bg p-3 rounded-xl border border-dark-border">
          <span className="text-[11px] text-dark-muted block mb-1">Metric Scale</span>
          <span className="text-sm font-bold text-brand-400 font-mono">
            {report.cumulative_scale.toFixed(3)}x
          </span>
        </div>
      </div>
    </div>
  );
};
