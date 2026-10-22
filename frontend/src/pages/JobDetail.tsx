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
  getDownloadAllUrl
} from "../api/client";
import { useJobEvents } from "../api/useJobEvents";
import { StatusBadge } from "../components/StatusBadge";
import { MeshViewer } from "../components/MeshViewer";
import { MeasureTool } from "../components/MeasureTool";
import { QualityReport } from "../components/QualityReport";
import { LogPanel } from "../components/LogPanel";
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
  XCircle
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

  // Measure points
  const [pointA, setPointA] = useState<[number, number, number] | null>(null);
  const [pointB, setPointB] = useState<[number, number, number] | null>(null);

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

        if (data.artifacts?.some(a => a.filename === "sfm_report.json")) {
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
      <div className="max-w-5xl mx-auto py-16 px-4 text-center text-dark-muted text-sm">
        Loading scan details...
      </div>
    );
  }

  if (!job) {
    return (
      <div className="max-w-5xl mx-auto py-16 px-4 text-center">
        <p className="text-rose-400 text-sm mb-4">Job not found</p>
        <button onClick={onBack} className="text-xs text-brand-400 hover:underline">
          Return to scans list
        </button>
      </div>
    );
  }

  const currentStatus = eventState.status || job.status;
  const currentProgress = eventState.isCompleted ? 100 : Math.max(job.progress, eventState.progress);
  const currentStage = eventState.currentStage || job.current_stage || "queued";
  const allLogs = eventState.logs.length > 0 ? eventState.logs : job.log_tail || [];

  const parseFailureDetails = (errorMessage?: string | null) => {
    if (!errorMessage) return null;
    const stageMatch = errorMessage.match(/at stage '([^']+)'/i);
    const ratioMatch = errorMessage.match(/(\d+\/\d+\s+frames\s+registered\s+\([0-9.]+%\)|[0-9.]+%\s+\(\d+\/\d+\s+frames\))/i);
    const thresholdMatch = errorMessage.match(/threshold of ([0-9.]+%)/i);
    const hintMatch = errorMessage.match(/Hint:\s*(.*)/i);

    return {
      stage: stageMatch ? stageMatch[1] : (job?.current_stage || "sfm"),
      ratio: ratioMatch ? ratioMatch[1] : (sfmReport ? `${sfmReport.registered_frames}/${sfmReport.total_frames} (${(sfmReport.registration_ratio * 100).toFixed(1)}%)` : "Low registration"),
      threshold: thresholdMatch ? thresholdMatch[1] : (sfmReport?.min_registration_ratio ? `${(sfmReport.min_registration_ratio * 100).toFixed(0)}%` : "60%"),
      hint: hintMatch ? hintMatch[1] : "Low feature count or rapid camera movement detected. Try moving slower or adjusting settings under Advanced Settings.",
      raw: errorMessage
    };
  };

  return (
    <div className="max-w-6xl mx-auto py-8 px-4 sm:px-6 space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-dark-border pb-5">
        <div className="flex items-center space-x-3">
          <button
            onClick={onBack}
            className="p-2 rounded-xl bg-dark-card border border-dark-border hover:bg-dark-hover text-dark-muted hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
                {job.original_filename || `Scan ${job.id.substring(0, 8)}`}
              </h1>
              <StatusBadge status={currentStatus} />
              {sfmReport && sfmReport.is_partial && (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" />
                  Partial Model ({(sfmReport.registration_ratio * 100).toFixed(1)}%)
                </span>
              )}
            </div>
            <div className="flex items-center space-x-3 text-xs text-dark-muted mt-1">
              <span className="capitalize">{job.scan_type.replace("_", " ")}</span>
              <span>•</span>
              <span className="capitalize">{job.quality} Preset</span>
              <span>•</span>
              <span className="font-mono">{job.id}</span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2">
          {["queued", "running", "preprocessing"].includes(currentStatus) && (
            <button
              onClick={handleCancel}
              className="px-3.5 py-1.5 rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 text-xs font-semibold flex items-center gap-1.5 transition-colors"
            >
              <Ban className="w-3.5 h-3.5" />
              <span>Cancel Job</span>
            </button>
          )}

          {currentStatus === "completed" && (
            <a
              href={getDownloadAllUrl(job.id)}
              download
              className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold flex items-center gap-2 shadow-lg shadow-brand-500/20 transition-all"
            >
              <Archive className="w-4 h-4" />
              <span>Download All (ZIP)</span>
            </a>
          )}
        </div>
      </div>

      {/* Failure Reason Banner */}
      {currentStatus === "failed" && (
        <div className="bg-rose-950/40 border border-rose-500/50 rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex items-center space-x-3 text-rose-400">
            <AlertTriangle className="w-5 h-5 flex-shrink-0" />
            <h3 className="text-base font-bold text-white tracking-tight">Reconstruction Failed Registration Check</h3>
          </div>

          {(() => {
            const details = parseFailureDetails(job.error);
            return (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="bg-dark-bg/80 border border-rose-500/30 rounded-xl p-3">
                    <span className="text-rose-300/70 block font-medium">Failed Stage</span>
                    <span className="text-white font-mono font-bold text-sm mt-0.5 uppercase block">{details?.stage || "SFM"}</span>
                  </div>
                  <div className="bg-dark-bg/80 border border-rose-500/30 rounded-xl p-3">
                    <span className="text-rose-300/70 block font-medium">Registration Ratio</span>
                    <span className="text-rose-400 font-mono font-bold text-sm mt-0.5 block">{details?.ratio || "N/A"}</span>
                  </div>
                  <div className="bg-dark-bg/80 border border-rose-500/30 rounded-xl p-3">
                    <span className="text-rose-300/70 block font-medium">Required Threshold</span>
                    <span className="text-amber-400 font-mono font-bold text-sm mt-0.5 block">{details?.threshold || "60%"}</span>
                  </div>
                </div>

                <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-200 flex items-start space-x-2.5">
                  <Info className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-rose-300">Suggestion: </span>
                    {details?.hint || "Video may have rapid pans, blur, or low texture. Try moving slower or lowering the threshold in Advanced Settings."}
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Progress & Live Stage Timeline */}
      {["queued", "running", "preprocessing"].includes(currentStatus) && (
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg space-y-4">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2">
              <span className="font-semibold text-white">Current Stage:</span>
              <span className="text-brand-400 font-mono capitalize">{currentStage.replace("_", " ")}</span>
            </div>
            <span className="font-mono text-white font-bold">{currentProgress}%</span>
          </div>

          <div className="w-full bg-dark-bg h-2 rounded-full overflow-hidden border border-dark-border">
            <div
              className="bg-gradient-to-r from-brand-600 to-indigo-500 h-full rounded-full transition-all duration-300"
              style={{ width: `${currentProgress}%` }}
            />
          </div>
        </div>
      )}

      {/* 3D Interactive Viewer when completed */}
      {currentStatus === "completed" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Interactive 3D Geometry Preview</h3>
            <span className="text-xs text-dark-muted">Click anywhere on geometry to pick scale points</span>
          </div>

          {(() => {
            const modelArtifact = job?.artifacts?.find(a => a.filename === "raw_mesh.glb" || a.filename === "scanforge_room.glb" || a.filename.endsWith(".glb"));
            const modelUrl = modelArtifact ? modelArtifact.download_url : undefined;
            return (
              <MeshViewer
                modelUrl={modelUrl}
                onPointSelected={handlePointClick}
                measureMode={true}
                pointA={pointA}
                pointB={pointB}
              />
            );
          })()}

          {/* Scale Calibration Tool */}
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

          {/* Room Quality & Metrics Report */}
          <QualityReport report={report} />
        </div>
      )}

      {/* Scene Cuts Inspection Section */}
      {cutsData && cutsData.length > 0 && (
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Scissors className="w-4 h-4 text-brand-400" />
              <h3 className="text-sm font-semibold text-white">Scene Cut & Pan Candidate Inspection</h3>
            </div>
            <span className="text-xs text-dark-muted font-mono">{cutsData.length} candidate(s) analyzed</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {cutsData.map((cut: any) => (
              <div key={cut.cut_id} className="border border-dark-border/80 rounded-xl p-3 bg-dark-bg/60 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-white">Cut #{cut.cut_id} (t={cut.timestamp_seconds}s)</span>
                  {cut.confirmed_cut ? (
                    <span className="px-2 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 font-medium text-[11px] flex items-center gap-1">
                      <XCircle className="w-3 h-3" /> Discontinuity
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-medium text-[11px] flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" /> Continuous Pan (Overlapping)
                    </span>
                  )}
                </div>

                <div className="text-[11px] text-dark-muted grid grid-cols-2 gap-2">
                  <div>Hist Corr: <span className="font-mono text-white">{cut.histogram_correlation}</span></div>
                  <div>RANSAC Inliers: <span className="font-mono text-white">{cut.verified_feature_matches} matches</span></div>
                </div>

                {cut.comparison_file && (
                  <div className="rounded-lg overflow-hidden border border-dark-border bg-black">
                    <img
                      src={getCutImageUrl(job.id, cut.comparison_file)}
                      alt={`Cut ${cut.cut_id} comparison`}
                      className="w-full h-auto object-contain"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SfM Metrics & Camera Path (Visible on completed, partial, or failed scans if generated) */}
      {(sfmReport || job.artifacts?.some(a => a.filename === "camera_path.png")) && (
        <div className="bg-dark-card border border-dark-border rounded-2xl p-6 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">SfM Camera Trajectory & Metrics</h3>
            {sfmReport && (
              <span className="text-xs text-brand-400 font-mono">
                {sfmReport.registered_frames} / {sfmReport.total_frames} registered ({(sfmReport.registration_ratio * 100).toFixed(1)}%)
              </span>
            )}
          </div>

          {sfmReport && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="bg-dark-bg border border-dark-border/60 rounded-xl p-3">
                <div className="text-dark-muted">Sparse 3D Points</div>
                <div className="text-white font-bold text-sm mt-0.5">{sfmReport.point_count?.toLocaleString()}</div>
              </div>
              <div className="bg-dark-bg border border-dark-border/60 rounded-xl p-3">
                <div className="text-dark-muted">Reprojection Error</div>
                <div className="text-white font-bold text-sm mt-0.5">{sfmReport.mean_reprojection_error} px</div>
              </div>
              <div className="bg-dark-bg border border-dark-border/60 rounded-xl p-3">
                <div className="text-dark-muted">Peak VRAM / RAM</div>
                <div className="text-white font-bold text-sm mt-0.5">{sfmReport.peak_vram_mb} MB / {sfmReport.peak_ram_mb} MB</div>
              </div>
              <div className="bg-dark-bg border border-dark-border/60 rounded-xl p-3">
                <div className="text-dark-muted">Matcher / Duration</div>
                <div className="text-white font-bold text-sm mt-0.5">{sfmReport.matcher_used} ({sfmReport.sfm_duration_seconds}s)</div>
              </div>
            </div>
          )}

          {job.artifacts?.some((a: Artifact) => a.filename === "camera_path.png") && (
            <div className="border border-dark-border rounded-xl overflow-hidden bg-black flex justify-center">
              <img
                src={getDownloadUrl(job.id, "png")}
                alt="Camera Trajectory"
                className="max-h-96 object-contain"
              />
            </div>
          )}
        </div>
      )}

      {/* Download Artifacts Bar */}
      {job.artifacts && job.artifacts.length > 0 && (
        <div className="bg-dark-card border border-dark-border rounded-2xl p-5 shadow-lg space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-dark-muted">
            Available Format Downloads
          </h4>
          <div className="flex flex-wrap gap-2">
            {job.artifacts.map((art: Artifact) => (
              <a
                key={art.id}
                href={getDownloadUrl(job.id, art.format)}
                download={art.filename}
                className="px-3.5 py-2 rounded-xl bg-dark-bg border border-dark-border hover:border-brand-500/50 hover:bg-dark-hover text-white text-xs font-semibold flex items-center space-x-2 transition-all shadow-sm"
              >
                <Download className="w-3.5 h-3.5 text-brand-400" />
                <span className="uppercase">{art.format}</span>
                <span className="text-[11px] text-dark-muted">
                  ({(art.size_bytes / 1024).toFixed(0)} KB)
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Live Log Terminal */}
      <LogPanel logs={allLogs} jobId={job.id} />
    </div>
  );
};
