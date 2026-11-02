import React, { useEffect, useState } from "react";
import { Job, JobReport, Artifact } from "../api/types";
import {
  fetchJob,
  cancelJob,
  calibrateScale,
  fetchJobReport,
  fetchJobCuts,
  getCutImageUrl,
  getDownloadUrl,
  getDownloadAllUrl,
} from "../api/client";
import { useJobEvents } from "../api/useJobEvents";
import { StatusBadge } from "../components/StatusBadge";
import { MeshViewer } from "../components/MeshViewer";
import { MeasureTool } from "../components/MeasureTool";
import { QualityReport } from "../components/QualityReport";
import { LogPanel } from "../components/LogPanel";
import { StageTimeline } from "../components/StageTimeline";
import {
  ArrowLeft,
  Download,
  Ban,
  Archive,
  AlertTriangle,
  AlertCircle,
  Info,
  Scissors,
  CheckCircle,
  XCircle,
} from "lucide-react";

interface Props {
  jobId: string;
  onBack: () => void;
}

export const JobDetail: React.FC<Props> = ({ jobId, onBack }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [report, setReport] = useState<JobReport | null>(null);
  const [sfmReport, setSfmReport] = useState<any | null>(null);
  const [cutsData, setCutsData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Measure mode state & points
  const [measureActive, setMeasureActive] = useState(false);
  const [pointA, setPointA] = useState<[number, number, number] | null>(null);
  const [pointB, setPointB] = useState<[number, number, number] | null>(null);

  // Active 3D preview selection
  const [previewTab, setPreviewTab] = useState<"textured" | "dense" | "mesh">("textured");

  // SSE event stream
  const eventState = useJobEvents(jobId);

  const loadJobData = async () => {
    try {
      const data = await fetchJob(jobId);
      setJob(data);
      if (data.status === "completed" || data.status === "failed") {
        try {
          const rep = await fetchJobReport(jobId);
          setReport(rep);
        } catch {}

        if (data.artifacts?.some((a) => a.filename === "sfm_report.json")) {
          try {
            const res = await fetch(getDownloadUrl(jobId, "json"));
            if (res.ok) {
              const sfm = await res.json();
              setSfmReport(sfm);
            }
          } catch {}
        }

        try {
          const cutsRes = await fetchJobCuts(jobId);
          if (cutsRes?.cuts) {
            setCutsData(cutsRes.cuts);
          }
        } catch {}
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJobData();
    const interval = setInterval(() => {
      if (job?.status !== "completed" && job?.status !== "failed" && job?.status !== "cancelled") {
        loadJobData();
      }
    }, 2500);
    return () => clearInterval(interval);
  }, [jobId, job?.status]);

  // Sync SSE updates into job state
  useEffect(() => {
    if (eventState.status === "completed" && job?.status !== "completed") {
      loadJobData();
    }
  }, [eventState.status]);

  const handleCancel = async () => {
    if (!confirm("Are you sure you want to cancel this reconstruction?")) return;
    try {
      await cancelJob(jobId);
      await loadJobData();
    } catch (e: any) {
      alert("Failed cancelling job: " + e.message);
    }
  };

  const handlePointClick = (pt: [number, number, number]) => {
    if (!pointA) {
      setPointA(pt);
    } else if (!pointB) {
      setPointB(pt);
    } else {
      setPointA(pt);
      setPointB(null);
    }
  };

  const handleCalibrate = async (realDistance: number) => {
    if (!pointA || !pointB) return;
    await calibrateScale(jobId, pointA, pointB, realDistance);
    await loadJobData();
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto py-24 px-4 text-center text-zinc-500 font-mono text-xs">
        Loading spatial telemetry...
      </div>
    );
  }

  if (!job) {
    return (
      <div className="max-w-6xl mx-auto py-24 px-4 text-center">
        <p className="text-rose-400 text-sm mb-4 font-semibold">Job not found</p>
        <button
          onClick={onBack}
          className="text-xs text-indigo-400 hover:text-cyan-300 transition-colors underline font-mono"
        >
          Return to scans library
        </button>
      </div>
    );
  }

  const currentStatus = eventState.status || job.status;
  const currentProgress = eventState.isCompleted
    ? 100
    : Math.max(job.progress, eventState.progress);
  const currentStage = eventState.currentStage || job.current_stage || "queued";
  const allLogs = eventState.logs.length > 0 ? eventState.logs : job.log_tail || [];
  const isRunning = ["queued", "running", "preprocessing", "exporting"].includes(currentStatus);

  const parseFailureDetails = (errorMessage?: string | null) => {
    if (!errorMessage) return null;
    const stageMatch = errorMessage.match(/at stage '([^']+)'/i);
    const ratioMatch = errorMessage.match(
      /(\d+\/\d+\s+frames\s+registered\s+\([0-9.]+%\)|[0-9.]+%\s+\(\d+\/\d+\s+frames\))/i
    );
    const thresholdMatch = errorMessage.match(/threshold of ([0-9.]+%)/i);
    const hintMatch = errorMessage.match(/Hint:\s*(.*)/i);

    return {
      stage: stageMatch ? stageMatch[1] : job?.current_stage || "sfm",
      ratio: ratioMatch
        ? ratioMatch[1]
        : sfmReport
        ? `${sfmReport.registered_frames}/${sfmReport.total_frames} (${(
            sfmReport.registration_ratio * 100
          ).toFixed(1)}%)`
        : "Low registration",
      threshold: thresholdMatch
        ? thresholdMatch[1]
        : sfmReport?.min_registration_ratio
        ? `${(sfmReport.min_registration_ratio * 100).toFixed(0)}%`
        : "60%",
      hint:
        hintMatch
          ? hintMatch[1]
          : "Rapid camera movements or blank walls detected. Lower threshold or move slower.",
      raw: errorMessage,
    };
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-zinc-800/80 pb-5">
        <div className="flex items-center space-x-3.5">
          <button
            onClick={onBack}
            className="p-2.5 rounded-2xl bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-zinc-400 hover:text-white transition-colors shadow-sm"
            title="Back to Jobs"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center space-x-2.5 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight">
                {job.original_filename || `Scan ${job.id.substring(0, 8)}`}
              </h1>
              <StatusBadge status={currentStatus} />
              {sfmReport && sfmReport.is_partial && (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center gap-1 font-mono">
                  <AlertCircle className="w-3.5 h-3.5" />
                  Partial ({(sfmReport.registration_ratio * 100).toFixed(1)}%)
                </span>
              )}
            </div>
            <div className="flex items-center space-x-3 text-xs text-zinc-400 mt-1 font-mono">
              <span className="capitalize text-zinc-300 font-semibold">
                {job.scan_type.replace("_", " ")}
              </span>
              <span>•</span>
              <span className="capitalize">{job.quality} Quality</span>
              <span>•</span>
              <span className="text-zinc-500 truncate max-w-[200px]">ID: {job.id}</span>
            </div>
          </div>
        </div>

        {/* Top Actions */}
        <div className="flex items-center space-x-2.5">
          {isRunning && (
            <button
              onClick={handleCancel}
              className="px-4 py-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Cancel Job</span>
            </button>
          )}

          {currentStatus === "completed" && (
            <a
              href={getDownloadAllUrl(job.id)}
              download
              className="px-4 py-2.5 rounded-2xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white text-xs font-bold flex items-center gap-2 shadow-xl shadow-indigo-600/20 transition-all select-none"
            >
              <Archive className="w-4 h-4" />
              <span>Download All Deliverables (.ZIP)</span>
            </a>
          )}
        </div>
      </div>

      {/* Failure Reason Banner */}
      {currentStatus === "failed" && (
        <div className="bg-rose-950/40 border border-rose-500/50 rounded-3xl p-6 shadow-2xl space-y-4">
          <div className="flex items-center space-x-3 text-rose-400">
            <AlertTriangle className="w-6 h-6 flex-shrink-0" />
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">
                Reconstruction Stopped: Verification Threshold Unmet
              </h3>
              <p className="text-xs text-rose-300/80 mt-0.5">
                The capture did not produce enough confident 3D camera tracks to generate a high-fidelity model.
              </p>
            </div>
          </div>

          {(() => {
            const details = parseFailureDetails(job.error);
            return (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="bg-zinc-950/80 border border-rose-500/30 rounded-2xl p-3.5">
                    <span className="text-rose-300/70 block font-medium">Failed Stage</span>
                    <span className="text-white font-mono font-bold text-sm mt-0.5 uppercase block">
                      {details?.stage || "SFM"}
                    </span>
                  </div>
                  <div className="bg-zinc-950/80 border border-rose-500/30 rounded-2xl p-3.5">
                    <span className="text-rose-300/70 block font-medium">Registered Frames</span>
                    <span className="text-rose-400 font-mono font-bold text-sm mt-0.5 block">
                      {details?.ratio || "N/A"}
                    </span>
                  </div>
                  <div className="bg-zinc-950/80 border border-rose-500/30 rounded-2xl p-3.5">
                    <span className="text-rose-300/70 block font-medium">Required Threshold</span>
                    <span className="text-amber-400 font-mono font-bold text-sm mt-0.5 block">
                      {details?.threshold || "60%"}
                    </span>
                  </div>
                </div>

                <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-2xl text-xs text-rose-200 flex items-start space-x-2.5">
                  <Info className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-rose-300">Diagnostic Suggestion: </span>
                    {details?.hint || "Video may have rapid pans, blur, or blank walls. Move slower or accept partial models in Advanced Settings."}
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* While running / queued: StageTimeline */}
      {isRunning && (
        <StageTimeline
          currentStage={currentStage}
          progress={currentProgress}
          status={currentStatus}
          onCancel={handleCancel}
        />
      )}

      {/* When completed: Full Studio Viewport & Tool HUDs */}
      {currentStatus === "completed" && (
        <div className="space-y-6">
          {/* 3D Viewport with HUD overlays */}
          {(() => {
            let targetArtifact: Artifact | undefined;
            let displayLabel = "Textured Mesh (Metric / SfM)";

            if (previewTab === "textured") {
              targetArtifact = job?.artifacts?.find(
                (a) =>
                  a.filename === "preview_textured.glb" ||
                  a.filename === "scene_textured.glb" ||
                  a.filename === "scene_dense_mesh_texture.glb"
              );
              displayLabel = "Textured Mesh (PBR DoubleSide)";
            } else if (previewTab === "dense") {
              targetArtifact = job?.artifacts?.find(
                (a) =>
                  a.filename === "preview_cloud.ply" ||
                  a.filename === "dense_cloud.ply" ||
                  a.filename === "scene_dense.ply"
              );
              displayLabel = "Dense Point Cloud (PLY)";
            } else {
              targetArtifact = job?.artifacts?.find(
                (a) =>
                  a.filename === "preview_mesh.glb" ||
                  a.filename === "raw_mesh.glb" ||
                  a.filename === "scene_dense_mesh.ply"
              );
              displayLabel = "Raw Delaunay Geometry";
            }

            // Fallback if specific tab artifact not found
            if (!targetArtifact) {
              targetArtifact = job?.artifacts?.find(
                (a) => a.filename.endsWith(".glb") || a.filename.endsWith(".ply")
              );
            }

            const modelUrl = targetArtifact ? targetArtifact.download_url : undefined;

            return (
              <MeshViewer
                modelUrl={modelUrl}
                onPointSelected={handlePointClick}
                measureMode={measureActive}
                onToggleMeasureMode={() => setMeasureActive(!measureActive)}
                pointA={pointA}
                pointB={pointB}
                label={displayLabel}
                activeTab={previewTab}
                onTabChange={setPreviewTab}
                jobMetadata={{
                  id: job.id,
                  scanType: job.scan_type,
                  quality: job.quality,
                }}
              />
            );
          })()}

          {/* Interactive Scale Calibration HUD (always visible or toggleable) */}
          <MeasureTool
            pointA={pointA}
            pointB={pointB}
            onClear={() => {
              setPointA(null);
              setPointB(null);
            }}
            onCalibrate={handleCalibrate}
            cumulativeScale={job.cumulative_scale || 1.0}
          />

          {/* Architectural Quality & Dimension Report */}
          <QualityReport
            report={report}
            onActivateMeasure={() => setMeasureActive(true)}
          />

          {/* Deliverables Export Vault */}
          {job.artifacts && job.artifacts.length > 0 && (
            <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
                <div>
                  <h3 className="text-sm font-bold text-white tracking-tight uppercase flex items-center gap-2">
                    <Archive className="w-4 h-4 text-cyan-400" />
                    Deliverables Export Vault
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Exported multi-format assets calibrated to real metric units and upright Y=0 floor leveling.
                  </p>
                </div>
                <a
                  href={getDownloadAllUrl(job.id)}
                  download
                  className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs flex items-center gap-1.5 shadow-md shadow-indigo-600/20 transition-all self-start sm:self-auto"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download All (.ZIP)</span>
                </a>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
                {job.artifacts
                  .filter((art) => !art.filename.endsWith(".json") && !art.filename.endsWith(".png"))
                  .map((art: Artifact) => (
                    <a
                      key={art.id}
                      href={getDownloadUrl(job.id, art.format)}
                      download={art.filename}
                      className="p-3.5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 hover:border-cyan-500/50 hover:bg-zinc-900 text-white text-xs font-semibold flex items-center justify-between group transition-all shadow-sm"
                    >
                      <div className="flex items-center space-x-2.5 truncate">
                        <Download className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
                        <div className="truncate">
                          <span className="uppercase font-bold block">{art.format}</span>
                          <span className="text-[10px] font-mono text-zinc-400 block truncate">
                            {art.filename}
                          </span>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500 tabular-nums ml-2 flex-shrink-0">
                        {(art.size_bytes / 1024).toFixed(0)} KB
                      </span>
                    </a>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Scene Cuts Inspection Section */}
      {cutsData && cutsData.length > 0 && (
        <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Scissors className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white">Scene Cut & Pan Candidate Inspection</h3>
            </div>
            <span className="text-xs text-zinc-400 font-mono">{cutsData.length} candidate(s)</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cutsData.map((cut: any) => (
              <div
                key={cut.cut_id}
                className="border border-zinc-800 rounded-2xl p-4 bg-zinc-900/50 space-y-2.5"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white">
                    Candidate #{cut.cut_id} (t={cut.timestamp_seconds}s)
                  </span>
                  {cut.confirmed_cut ? (
                    <span className="px-2.5 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 font-bold text-[10px] flex items-center gap-1">
                      <XCircle className="w-3 h-3" /> Discontinuity
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold text-[10px] flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" /> Continuous Pan
                    </span>
                  )}
                </div>

                <div className="text-[11px] text-zinc-400 grid grid-cols-2 gap-2 font-mono">
                  <div>Hist Corr: <span className="text-white">{cut.histogram_correlation}</span></div>
                  <div>RANSAC Inliers: <span className="text-white">{cut.verified_feature_matches}</span></div>
                </div>

                {cut.comparison_file && (
                  <div className="rounded-xl overflow-hidden border border-zinc-800 bg-black">
                    <img
                      src={getCutImageUrl(job.id, cut.comparison_file)}
                      alt={`Cut ${cut.cut_id}`}
                      className="w-full h-auto object-contain max-h-48"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SfM Metrics & Trajectory Plot */}
      {(sfmReport || job.artifacts?.some((a) => a.filename === "camera_path.png")) && (
        <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white tracking-tight">
              SfM Camera Trajectory & Convergence Metrics
            </h3>
            {sfmReport && (
              <span className="text-xs text-cyan-400 font-mono font-bold">
                {sfmReport.registered_frames} / {sfmReport.total_frames} frames registered (
                {(sfmReport.registration_ratio * 100).toFixed(1)}%)
              </span>
            )}
          </div>

          {sfmReport && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                <div className="text-zinc-400 font-medium">Sparse 3D Points</div>
                <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                  {sfmReport.point_count?.toLocaleString()}
                </div>
              </div>
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                <div className="text-zinc-400 font-medium">Reprojection Error</div>
                <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                  {sfmReport.mean_reprojection_error} px
                </div>
              </div>
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                <div className="text-zinc-400 font-medium">Peak VRAM / RAM</div>
                <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                  {sfmReport.peak_vram_mb} MB / {sfmReport.peak_ram_mb} MB
                </div>
              </div>
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                <div className="text-zinc-400 font-medium">Matcher / Duration</div>
                <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                  {sfmReport.matcher_used} ({sfmReport.sfm_duration_seconds}s)
                </div>
              </div>
            </div>
          )}

          {job.artifacts?.some((a: Artifact) => a.filename === "camera_path.png") && (
            <div className="border border-zinc-800 rounded-2xl overflow-hidden bg-black flex justify-center p-2">
              <img
                src={getDownloadUrl(job.id, "png")}
                alt="Camera Trajectory"
                className="max-h-96 object-contain"
              />
            </div>
          )}
        </div>
      )}

      {/* Terminal Log Console */}
      <LogPanel logs={allLogs} jobId={job.id} />
    </div>
  );
};
