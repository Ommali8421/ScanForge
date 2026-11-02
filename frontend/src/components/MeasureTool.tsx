import React, { useState } from "react";
import { Ruler, CheckCircle2, RotateCcw, ArrowRight, Zap, Target } from "lucide-react";
import { SmartHint } from "./SmartHint";

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
  const [statusMsg, setStatusMsg] = useState<{ text: string; isError?: boolean } | null>(null);

  const getDistance = () => {
    if (!pointA || !pointB) return null;
    const dx = pointA[0] - pointB[0];
    const dy = pointA[1] - pointB[1];
    const dz = pointA[2] - pointB[2];
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  };

  const dist = getDistance();

  const handleApply = async () => {
    if (dist === null || dist < 1e-4) {
      setStatusMsg({ text: "Selected points are too close together to calibrate.", isError: true });
      return;
    }
    const val = parseFloat(realDist);
    if (isNaN(val) || val <= 0) {
      setStatusMsg({ text: "Please enter a valid positive distance in meters.", isError: true });
      return;
    }
    setLoading(true);
    setStatusMsg(null);
    const startTime = performance.now();
    try {
      await onCalibrate(val);
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);
      setStatusMsg({
        text: `Metric scale calibrated successfully in ${elapsed}s! All dimensions and 3D deliverables updated.`,
      });
    } catch (e: any) {
      setStatusMsg({ text: `Calibration failed: ${e.message}`, isError: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-5 shadow-xl space-y-4">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white flex items-center justify-center shadow-md shadow-indigo-600/20">
            <Ruler className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-white tracking-tight">
              Interactive Metric Scale Calibration
            </h4>
            <p className="text-[11px] text-zinc-400">
              Measure any reference object in the 3D scene to ground arbitrary SfM units into real-world meters.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-400">
            Cumulative Scale:{" "}
            <strong className="text-cyan-400 font-bold tabular-nums">
              {cumulativeScale.toFixed(3)}x
            </strong>
          </span>
          {(pointA || pointB) && (
            <button
              onClick={onClear}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors text-xs flex items-center gap-1"
              title="Reset picked points"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* 3-Step Guided Workflow Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        {/* Step 1: Point A */}
        <div
          className={`p-3.5 rounded-2xl border transition-all ${
            pointA
              ? "border-rose-500/40 bg-rose-950/20 shadow-sm"
              : "border-zinc-800 bg-zinc-900/40 text-zinc-400"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold flex items-center gap-1.5 text-white">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
              Point A (Reference Origin)
            </span>
            {pointA && <CheckCircle2 className="w-3.5 h-3.5 text-rose-400" />}
          </div>
          <div className="font-mono text-[11px] text-zinc-300 tabular-nums">
            {pointA ? `(${pointA[0].toFixed(3)}, ${pointA[1].toFixed(3)}, ${pointA[2].toFixed(3)})` : "Click geometry in viewer..."}
          </div>
        </div>

        {/* Step 2: Point B */}
        <div
          className={`p-3.5 rounded-2xl border transition-all ${
            pointB
              ? "border-blue-500/40 bg-blue-950/20 shadow-sm"
              : pointA
              ? "border-cyan-500/40 bg-cyan-950/20 animate-pulse text-cyan-200"
              : "border-zinc-800 bg-zinc-900/40 text-zinc-500"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold flex items-center gap-1.5 text-white">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
              Point B (Reference End)
            </span>
            {pointB && <CheckCircle2 className="w-3.5 h-3.5 text-blue-400" />}
          </div>
          <div className="font-mono text-[11px] text-zinc-300 tabular-nums">
            {pointB
              ? `(${pointB[0].toFixed(3)}, ${pointB[1].toFixed(3)}, ${pointB[2].toFixed(3)})`
              : pointA
              ? "Click opposite end in viewer..."
              : "Waiting for Point A..."}
          </div>
        </div>

        {/* Step 3: Measured Virtual Distance */}
        <div
          className={`p-3.5 rounded-2xl border transition-all ${
            dist !== null
              ? "border-emerald-500/40 bg-emerald-950/20 shadow-sm"
              : "border-zinc-800 bg-zinc-900/40 text-zinc-500"
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold text-white">Virtual Distance</span>
            <Target className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="font-mono font-extrabold text-sm text-emerald-400 tabular-nums">
            {dist !== null ? `${dist.toFixed(3)} m (uncalibrated)` : "--"}
          </div>
        </div>
      </div>

      {/* Real Distance Input & Quick Apply Action */}
      {dist !== null && (
        <div className="p-4 rounded-2xl bg-zinc-900/80 border border-zinc-800 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 animate-in fade-in duration-150">
          <div className="space-y-0.5">
            <div className="text-xs font-bold text-white flex items-center gap-1.5">
              <Zap className="w-4 h-4 text-amber-400" />
              <span>Step 3: Enter Known Real-World Dimension</span>
            </div>
            <p className="text-[11px] text-zinc-400">
              e.g. Standard interior door width = 0.90 m, ceiling height = 2.40 m
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="relative">
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={realDist}
                onChange={(e) => setRealDist(e.target.value)}
                className="w-28 bg-zinc-950 border border-zinc-700 rounded-xl px-3 py-2 text-xs text-white font-mono font-bold focus:outline-none focus:border-cyan-500 text-right pr-7"
                placeholder="2.00"
              />
              <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs font-mono text-zinc-500">
                m
              </span>
            </div>

            <button
              onClick={handleApply}
              disabled={loading}
              className="px-4 py-2 bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-emerald-600/20 flex items-center gap-1.5 transition-all disabled:opacity-50"
            >
              <span>{loading ? "Calibrating..." : "Apply Metric Scale"}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Feedback status message */}
      {statusMsg && (
        <div
          className={`text-xs p-3 rounded-2xl border flex items-center gap-2 ${
            statusMsg.isError
              ? "bg-rose-950/40 border-rose-500/40 text-rose-300"
              : "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
          }`}
        >
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
          <span>{statusMsg.text}</span>
        </div>
      )}

      <SmartHint
        topic="How Scale Calibration Works"
        hint="Scale calibration applies an instantaneous (< 0.15s) non-compounding rigid similarity transform directly to vertex coordinates, preserving UV texture atlases bitwise identical."
        guideTab={5}
      />
    </div>
  );
};
