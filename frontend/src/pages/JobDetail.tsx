import React, { useEffect, useState } from "react";
import { Job, JobReport } from "../api/types";
import { fetchJob, cancelJob, calibrateScale, fetchJobReport, getDownloadUrl, getDownloadAllUrl } from "../api/client";
import { useJobEvents } from "../api/useJobEvents";
import { StatusBadge } from "../components/StatusBadge";
import { MeshViewer } from "../components/MeshViewer";
import { MeasureTool } from "../components/MeasureTool";
import { QualityReport } from "../components/QualityReport";
import { LogPanel } from "../components/LogPanel";
import { ArrowLeft, Download, Ban, Archive } from "lucide-react";


interface Props {
  jobId: string;
  onBack: () => void;
}

export const JobDetail: React.FC<Props> = ({ jobId, onBack }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [report, setReport] = useState<JobReport | null>(null);
  const [sfmReport, setSfmReport] = useState<any | null>(null);
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
      if (data.status === "completed") {
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

      {/* Progress & Live Stage Timeline */}
      {currentStatus !== "completed" && (
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

          <MeshViewer
            onPointSelected={handlePointClick}
            measureMode={true}
          />

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

          {/* SfM Metrics & Camera Path */}
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

              {job.artifacts?.some(a => a.filename === "camera_path.png") && (
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
          <div className="bg-dark-card border border-dark-border rounded-2xl p-5 shadow-lg space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-dark-muted">
              Available Format Downloads
            </h4>
            <div className="flex flex-wrap gap-2">
              {job.artifacts && job.artifacts.length > 0 ? (
                job.artifacts.map((art) => (
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
                ))
              ) : (
                <div className="text-xs text-dark-muted">No artifact files registered yet.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Live Log Terminal */}
      <LogPanel logs={allLogs} />
    </div>
  );
};
