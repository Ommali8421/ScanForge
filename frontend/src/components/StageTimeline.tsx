import React from "react";
import { CheckCircle2, Loader2, Circle, Ban } from "lucide-react";

interface Props {
  currentStage: string;
  progress: number;
  status: string;
  onCancel?: () => void;
}

interface StageStep {
  id: string;
  label: string;
  sublabel: string;
}

const STAGES: StageStep[] = [
  { id: "ingest", label: "Ingest", sublabel: "Validation & Crop" },
  { id: "frame_extraction", label: "Frames", sublabel: "Sharpness & Flow" },
  { id: "sfm", label: "SfM Alignment", sublabel: "SIFT & Bundle Adj." },
  { id: "dense", label: "Dense Cloud", sublabel: "MVS Triangulation" },
  { id: "mesh", label: "Surface Mesh", sublabel: "Delaunay Carving" },
  { id: "floor_align", label: "Floor Leveling", sublabel: "Y=0 Grounding" },
  { id: "texture", label: "UV Texturing", sublabel: "4K Atlas Baking" },
  { id: "export", label: "Deliverables", sublabel: "Multi-Format Vault" },
];

export const StageTimeline: React.FC<Props> = ({
  currentStage,
  progress,
  status,
  onCancel,
}) => {
  const normStage = (currentStage || "").toLowerCase().replace(/[^a-z0-9_]/g, "_");

  // Determine stage index
  const getStageIndex = (stage: string) => {
    if (stage.includes("ingest")) return 0;
    if (stage.includes("frame") || stage.includes("extract")) return 1;
    if (stage.includes("sfm") || stage.includes("colmap") || stage.includes("match")) return 2;
    if (stage.includes("dense") || stage.includes("mvs_dense") || stage.includes("cloud")) return 3;
    if (stage.includes("mesh") || stage.includes("reconstruct") || stage.includes("clean") || stage.includes("decimate")) return 4;
    if (stage.includes("floor") || stage.includes("align") || stage.includes("plane") || stage.includes("room")) return 5;
    if (stage.includes("texture") || stage.includes("bake")) return 6;
    if (stage.includes("export") || stage.includes("deliverable")) return 7;
    return 1;
  };

  const currentIndex = getStageIndex(normStage);
  const isRunning = ["queued", "running", "preprocessing", "exporting"].includes(status);

  return (
    <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-6">
      {/* Header with Title and Cancel */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-white tracking-tight uppercase">
              Reconstruction Pipeline Telemetry
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-semibold uppercase animate-pulse">
              Live GPU Session
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5">
            Stage {Math.min(currentIndex + 1, STAGES.length)} of {STAGES.length} • Running strictly on 8 GB VRAM budget
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="text-right">
            <span className="text-xs text-zinc-400">Total Progress: </span>
            <span className="font-mono text-cyan-400 font-extrabold text-base tabular-nums">
              {progress}%
            </span>
          </div>

          {isRunning && onCancel && (
            <button
              onClick={onCancel}
              className="px-3.5 py-1.5 rounded-xl border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Cancel</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Progress Bar */}
      <div className="w-full bg-zinc-900 h-2.5 rounded-full overflow-hidden border border-zinc-800 relative">
        <div
          className="bg-gradient-to-r from-indigo-600 via-cyan-500 to-emerald-400 h-full rounded-full transition-all duration-300 shadow-lg shadow-cyan-500/20"
          style={{ width: `${Math.max(progress, 3)}%` }}
        />
      </div>

      {/* Visual Pipeline Stages */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 pt-1">
        {STAGES.map((stg, idx) => {
          const isDone = idx < currentIndex || status === "completed";
          const isCurrent = idx === currentIndex && status !== "completed" && status !== "failed";

          return (
            <div
              key={stg.id}
              className={`p-3 rounded-2xl border transition-all flex flex-col justify-between ${
                isCurrent
                  ? "border-cyan-500/60 bg-cyan-950/20 shadow-md shadow-cyan-500/10 ring-1 ring-cyan-500/30"
                  : isDone
                  ? "border-emerald-500/30 bg-emerald-950/10 text-zinc-300"
                  : "border-zinc-800/80 bg-zinc-900/30 text-zinc-500"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono text-zinc-400 font-bold">
                  0{idx + 1}
                </span>
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                ) : isCurrent ? (
                  <Loader2 className="w-4 h-4 text-cyan-400 animate-spin flex-shrink-0" />
                ) : (
                  <Circle className="w-3.5 h-3.5 text-zinc-600 flex-shrink-0" />
                )}
              </div>
              <div>
                <div
                  className={`text-xs font-bold truncate ${
                    isCurrent ? "text-white" : isDone ? "text-zinc-200" : "text-zinc-500"
                  }`}
                >
                  {stg.label}
                </div>
                <div className="text-[10px] text-zinc-400 truncate mt-0.5">
                  {stg.sublabel}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
