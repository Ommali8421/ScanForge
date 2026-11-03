import React, { useEffect, useState } from "react";
import { Job, JobReport, Artifact } from "../api/types";
import {
  fetchJob,
  cancelJob,
  resumeJob,
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
import { SplatViewer } from "../components/SplatViewer";
import { MeasureTool } from "../components/MeasureTool";
import { QualityReport } from "../components/QualityReport";
import { FloorPlanView } from "../components/FloorPlanView";
import { LogPanel } from "../components/LogPanel";
import { StageTimeline } from "../components/StageTimeline";
import {
  ArrowLeft,
  Download,
  Ban,
  Archive,
  AlertTriangle,
  AlertCircle,
  Scissors,
  CheckCircle,
  XCircle,
  RotateCcw,
} from "lucide-react";

interface Props {
  jobId: string;
  onBack: () => void;
}

export const JobDetail: React.FC<Props> = ({ jobId, onBack }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [report, setReport] = useState<JobReport | null>(null);
  const [sfmReport, setSfmReport] = useState<any | null>(null);
  const [routeDecision, setRouteDecision] = useState<any | null>(null);
  const [cutsData, setCutsData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [resuming, setResuming] = useState(false);

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
            const res = await fetch(`/api/jobs/${jobId}/artifacts/sfm_report.json`);
            if (res.ok) {
              const sfm = await res.json();
              setSfmReport(sfm);
            }
          } catch (e) {
            console.error("Failed to load sfm_report.json:", e);
          }
        }

        if (data.artifacts?.some((a) => a.filename === "mesh_route_decision.json")) {
          try {
            const rRes = await fetch(`/api/jobs/${jobId}/artifacts/mesh_route_decision.json`);
            if (rRes.ok) {
              const rDec = await rRes.json();
              setRouteDecision(rDec);
            }
          } catch (e) {
            console.error("Failed to load mesh_route_decision.json:", e);
          }
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

  const handleResume = async () => {
    if (!jobId) return;
    setResuming(true);
    try {
      const updated = await resumeJob(jobId);
      setJob(updated);
      await loadJobData();
    } catch (e: any) {
      alert("Failed resuming job: " + e.message);
    } finally {
      setResuming(false);
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
              {routeDecision && (
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border flex items-center gap-1 font-mono cursor-help ${
                    routeDecision.decision === "depth_fusion"
                      ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                      : "bg-cyan-500/10 border-cyan-500/30 text-cyan-400"
                  }`}
                  title={routeDecision.explanation}
                >
                  {routeDecision.decision === "depth_fusion" ? "Route B (Depth Fusion)" : "Route A (Photogrammetry)"}
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

          {(currentStatus === "failed" || currentStatus === "cancelled") && (
            <button
              onClick={handleResume}
              disabled={resuming}
              className="px-4 py-2 rounded-2xl border border-indigo-500/40 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-sm disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resuming ? "animate-spin" : ""}`} />
              <span>{resuming ? "Resuming..." : "Resume Job"}</span>
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

      {/* Failure Reason Banner with Actionable Remediation (Milestone P5 Hardening) */}
      {currentStatus === "failed" && (
        <div className="bg-rose-950/40 border border-rose-500/50 rounded-3xl p-6 shadow-2xl space-y-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center space-x-3 text-rose-400">
              <AlertTriangle className="w-6 h-6 flex-shrink-0" />
              <div>
                <div className="flex items-center space-x-2">
                  <h3 className="text-base font-bold text-white tracking-tight">
                    {job.error_details?.title || "Reconstruction Failed"}
                  </h3>
                  {job.error_code && (
                    <span className="px-2 py-0.5 rounded-lg bg-rose-500/20 text-rose-300 font-mono text-[11px] font-bold border border-rose-500/30">
                      {job.error_code}
                    </span>
                  )}
                </div>
                <p className="text-xs text-rose-300/80 mt-1">
                  {job.error_details?.summary || job.error || "An error occurred during pipeline execution."}
                </p>
              </div>
            </div>

            <button
              onClick={handleResume}
              disabled={resuming}
              className="px-4 py-2 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-2 shadow-lg transition-all disabled:opacity-50 flex-shrink-0"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resuming ? "animate-spin" : ""}`} />
              <span>{resuming ? "Resuming..." : "Resume Job"}</span>
            </button>
          </div>

          {job.error_details?.remediation && job.error_details.remediation.length > 0 && (
            <div className="bg-zinc-950/80 border border-rose-500/30 rounded-2xl p-4 space-y-2">
              <span className="text-xs font-bold text-rose-300 uppercase tracking-wider block">
                Actionable Remediation Steps:
              </span>
              <ul className="space-y-1.5 text-xs text-zinc-300">
                {job.error_details.remediation.map((step, idx) => (
                  <li key={idx} className="flex items-start space-x-2">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Cancelled Banner */}
      {currentStatus === "cancelled" && (
        <div className="bg-zinc-900/60 border border-zinc-700/50 rounded-3xl p-6 shadow-2xl flex items-center justify-between">
          <div className="flex items-center space-x-3 text-zinc-400">
            <Ban className="w-6 h-6 flex-shrink-0 text-amber-400" />
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">Job Cancelled</h3>
              <p className="text-xs text-zinc-400 mt-0.5">Execution was cancelled by user request. Completed upstream stages remain cached.</p>
            </div>
          </div>
          <button
            onClick={handleResume}
            disabled={resuming}
            className="px-4 py-2 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-2 shadow-lg transition-all disabled:opacity-50 flex-shrink-0"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${resuming ? "animate-spin" : ""}`} />
            <span>{resuming ? "Resuming..." : "Resume Job"}</span>
          </button>
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
            if (job?.scan_type === "gaussian_splat") {
              const splatArtifact =
                job.artifacts?.find((a) => a.filename === "model.splat") ||
                job.artifacts?.find((a) => a.filename === "cleaned_splat.splat") ||
                job.artifacts?.find((a) => a.filename.endsWith(".splat")) ||
                job.artifacts?.find((a) => a.filename === "model.ply") ||
                job.artifacts?.find((a) => a.filename === "cleaned_splat.ply") ||
                job.artifacts?.find((a) => a.filename.endsWith(".ply")) ||
                job.artifacts?.find((a) => a.filename.endsWith(".spz"));
              const splatUrl = splatArtifact
                ? `/api/jobs/${job.id}/artifacts/${splatArtifact.filename}`
                : `/api/jobs/${job.id}/download/splat/model.splat`;

              return (
                <SplatViewer
                  splatUrl={splatUrl}
                  jobId={job.id}
                  splatCount={report?.gaussian_count}
                  bounds={report?.bounds}
                  onDownload={(fmt) => window.open(getDownloadUrl(job.id, fmt), "_blank")}
                  availableFormats={job.output_formats || ["splat", "ply", "zip"]}
                />
              );
            }

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

          {/* 2D Architectural Floor Plan */}
          {(job.artifacts?.some((a) => a.filename === "floor_plan.svg" || a.filename === "floor_plan.png")) && (
            <FloorPlanView
              jobId={job.id}
              report={report}
              cumulativeScale={job.cumulative_scale || 1.0}
            />
          )}

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
                {(() => {
                  const all = job.artifacts || [];
                  const hasModelSplat = all.some((a) => a.filename === "model.splat");
                  const hasModelPly = all.some((a) => a.filename === "model.ply");
                  const hasModelGlb = all.some((a) => a.filename === "model.glb" || a.filename === "mesh.glb");

                  const deliverables = all.filter((art) => {
                    const fn = art.filename.toLowerCase();
                    // Exclude non-deliverable files
                    if (
                      fn.endsWith(".json") ||
                      fn.endsWith(".png") ||
                      fn.endsWith(".jpg") ||
                      fn.endsWith(".mp4") ||
                      fn.endsWith(".mov") ||
                      fn.endsWith(".avi") ||
                      fn.endsWith(".log") ||
                      fn.endsWith(".yml") ||
                      fn.endsWith(".yaml") ||
                      fn === "frames" ||
                      fn === "sparse.ply" ||
                      fn === "splat.ply"
                    ) {
                      return false;
                    }
                    // Deduplicate cleaned vs model
                    if (hasModelSplat && fn === "cleaned_splat.splat") return false;
                    if (hasModelPly && fn === "cleaned_splat.ply") return false;
                    if (hasModelGlb && (fn.startsWith("preview_") || fn.startsWith("scene_"))) return false;

                    const validExts = [".splat", ".ply", ".spz", ".glb", ".gltf", ".zip", ".fbx", ".usdz", ".stl", ".xyz"];
                    return validExts.some((ext) => fn.endsWith(ext));
                  });

                  return deliverables.map((art: Artifact) => (
                    <a
                      key={art.id}
                      href={art.download_url || `/api/jobs/${job.id}/artifacts/${art.filename}`}
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
                  ));
                })()}
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
      {(() => {
        const activeSfm = sfmReport || job.options?.sfm_telemetry;
        if (!activeSfm && !job.artifacts?.some((a) => a.filename === "camera_path.png")) {
          return null;
        }

        return (
          <div className="bg-zinc-950/80 border border-zinc-800 rounded-3xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white tracking-tight">
                SfM Camera Trajectory & Convergence Metrics
              </h3>
              {activeSfm && (
                <span className="text-xs text-cyan-400 font-mono font-bold">
                  {activeSfm.registered_frames} / {activeSfm.total_frames} frames registered (
                  {(activeSfm.registration_ratio * 100).toFixed(1)}%)
                </span>
              )}
            </div>

            {activeSfm && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                  <div className="text-zinc-400 font-medium">Sparse 3D Points</div>
                  <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                    {activeSfm.point_count?.toLocaleString()}
                  </div>
                </div>
                <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                  <div className="text-zinc-400 font-medium">Reprojection Error</div>
                  <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                    {activeSfm.mean_reprojection_error} px
                  </div>
                </div>
                <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                  <div className="text-zinc-400 font-medium">Peak VRAM / RAM</div>
                  <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                    {activeSfm.peak_vram_mb} MB / {activeSfm.peak_ram_mb} MB
                  </div>
                </div>
                <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-3.5">
                  <div className="text-zinc-400 font-medium">Matcher / Duration</div>
                  <div className="text-white font-bold text-base font-mono mt-0.5 tabular-nums">
                    {activeSfm.matcher_used} ({activeSfm.sfm_duration_seconds}s)
                  </div>
                </div>
              </div>
            )}

            {job.artifacts?.some((a: Artifact) => a.filename === "camera_path.png") && (
              <div className="border border-zinc-800 rounded-2xl overflow-hidden bg-black flex justify-center p-2">
                <img
                  src={`/api/jobs/${job.id}/artifacts/camera_path.png`}
                  alt="Camera Trajectory"
                  className="max-h-96 object-contain"
                />
              </div>
            )}
          </div>
        );
      })()}

      {/* Terminal Log Console */}
      <LogPanel logs={allLogs} jobId={job.id} />
    </div>
  );
};
