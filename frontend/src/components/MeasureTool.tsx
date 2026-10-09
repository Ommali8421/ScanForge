import React, { useState } from "react";
import { Ruler, AlertCircle } from "lucide-react";


interface Props {
  pointA: [number, number, number] | null;
  pointB: [number, number, number] | null;
  onClear: () => void;
  onCalibrate: (realDistance: number) => Promise<void>;
  cumulativeScale: number;
}

export const MeasureTool: React.FC<Props> = ({
  pointA,
  pointB,
  onClear,
  onCalibrate,
  cumulativeScale,
}) => {
  const [realDist, setRealDist] = useState<string>("2.0");
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const getDistance = () => {
    if (!pointA || !pointB) return null;
    const dx = pointA[0] - pointB[0];
    const dy = pointA[1] - pointB[1];
    const dz = pointA[2] - pointB[2];
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  };

  const dist = getDistance();

  const handleApply = async () => {
    const val = parseFloat(realDist);
    if (isNaN(val) || val <= 0) return;
    setLoading(true);
    setStatusMsg(null);
    try {
      await onCalibrate(val);
      setStatusMsg("Calibration submitted. Re-scaling geometry...");
    } catch (e: any) {
      setStatusMsg(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-dark-card border border-dark-border rounded-2xl p-4 shadow-lg space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Ruler className="w-4 h-4 text-brand-400" />
          <h4 className="text-sm font-semibold text-white">Scale Calibration & Measurement</h4>
        </div>
        <span className="text-[11px] text-dark-muted">
          Current Scale: <strong className="text-brand-300 font-mono">{cumulativeScale.toFixed(3)}x</strong>
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-dark-bg p-2.5 rounded-xl border border-dark-border">
          <span className="text-dark-muted block mb-0.5">Point A:</span>
          <span className="font-mono text-white">
            {pointA ? `(${pointA.join(", ")})` : "Click mesh..."}
          </span>
        </div>
        <div className="bg-dark-bg p-2.5 rounded-xl border border-dark-border">
          <span className="text-dark-muted block mb-0.5">Point B:</span>
          <span className="font-mono text-white">
            {pointB ? `(${pointB.join(", ")})` : "Click mesh..."}
          </span>
        </div>
      </div>

      {dist !== null && (
        <div className="bg-dark-bg/60 p-3 rounded-xl border border-dark-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <span className="text-xs text-dark-muted">Virtual Distance: </span>
            <strong className="text-sm font-mono text-emerald-400">{dist.toFixed(3)} m</strong>
          </div>

          <div className="flex items-center space-x-2 w-full sm:w-auto">
            <span className="text-xs text-dark-muted whitespace-nowrap">Real Distance (m):</span>
            <input
              type="number"
              step="0.01"
              value={realDist}
              onChange={(e) => setRealDist(e.target.value)}
              className="w-20 bg-dark-bg border border-dark-border rounded-lg px-2 py-1 text-xs text-white focus:outline-none focus:border-brand-500 font-mono"
            />
            <button
              onClick={handleApply}
              disabled={loading}
              className="px-3 py-1 bg-brand-600 hover:bg-brand-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1 transition-colors disabled:opacity-50"
            >
              {loading ? "Calibrating..." : "Apply Scale"}
            </button>
            <button
              onClick={onClear}
              className="text-xs text-dark-muted hover:text-white px-2 py-1"
            >
              Reset
            </button>
          </div>
        </div>
      )}

      {statusMsg && (
        <div className="text-xs text-brand-300 flex items-center gap-1.5 bg-brand-500/10 p-2 rounded-lg border border-brand-500/20">
          <AlertCircle className="w-3.5 h-3.5" />
          <span>{statusMsg}</span>
        </div>
      )}
    </div>
  );
};
