import React, { useEffect, useState } from "react";
import { Job } from "../api/types";
import { fetchJobs, deleteJob } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import { Box, Sparkles, Radar, Trash2, ArrowUpRight, Clock, RefreshCw } from "lucide-react";

interface Props {
  onSelectJob: (jobId: string) => void;
  onNewScan: () => void;
}

export const Jobs: React.FC<Props> = ({ onSelectJob, onNewScan }) => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  const loadJobs = async () => {
    try {
      const data = await fetchJobs(50, 0);
      setJobs(data.items);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("Delete this scan and all associated 3D models?")) return;
    try {
      await deleteJob(id);
      setJobs((prev) => prev.filter((j) => j.id !== id));
    } catch (err) {
      alert("Failed to delete scan");
    }
  };

  const getScanIcon = (type: string) => {
    switch (type) {
      case "gaussian_splat":
        return <Sparkles className="w-4 h-4 text-amber-400" />;
      case "lidar":
        return <Radar className="w-4 h-4 text-purple-400" />;
      default:
        return <Box className="w-4 h-4 text-brand-400" />;
    }
  };

  return (
    <div className="max-w-5xl mx-auto py-8 px-4 sm:px-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Scan History
          </h1>
          <p className="text-dark-muted text-sm mt-1">
            Monitor background reconstructions, download exports, and inspect geometry metrics.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={loadJobs}
            className="p-2 rounded-xl bg-dark-card border border-dark-border text-dark-muted hover:text-white hover:bg-dark-hover transition-colors"
            title="Refresh scan list"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={onNewScan}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs transition-colors shadow-sm"
          >
            New Scan
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-16 text-dark-muted text-sm">Loading scans...</div>
      ) : jobs.length === 0 ? (
        <div className="border border-dark-border bg-dark-card rounded-2xl p-12 text-center space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-2xl bg-brand-500/10 text-brand-400 flex items-center justify-center mx-auto">
            <Box className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">No scans found</h3>
            <p className="text-dark-muted text-xs mt-1">
              Upload a walkthrough video or photo archive to initiate your first reconstruction.
            </p>
          </div>
          <button
            onClick={onNewScan}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-xs font-semibold"
          >
            Start Scan
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <div
              key={job.id}
              onClick={() => onSelectJob(job.id)}
              className="border border-dark-border bg-dark-card hover:border-slate-600 hover:bg-dark-hover rounded-2xl p-4 transition-all cursor-pointer shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="flex items-start sm:items-center space-x-3 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-dark-bg border border-dark-border flex items-center justify-center flex-shrink-0">
                  {getScanIcon(job.scan_type)}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center space-x-2">
                    <h3 className="text-sm font-semibold text-white truncate">
                      {job.original_filename || `Scan ${job.id.substring(0, 8)}`}
                    </h3>
                    <StatusBadge status={job.status} />
                  </div>
                  <div className="flex items-center space-x-3 text-xs text-dark-muted mt-1">
                    <span className="capitalize">{job.scan_type.replace("_", " ")}</span>
                    <span>•</span>
                    <span className="capitalize">{job.quality} Quality</span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(job.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                </div>
              </div>

              {/* Progress & Actions */}
              <div className="flex items-center space-x-4 self-end sm:self-auto flex-shrink-0">
                {job.status === "running" && (
                  <div className="w-28 text-right">
                    <div className="text-[11px] font-mono text-brand-400 font-semibold mb-1">
                      {job.progress}%
                    </div>
                    <div className="w-full bg-dark-bg h-1.5 rounded-full overflow-hidden border border-dark-border">
                      <div
                        className="bg-brand-500 h-full rounded-full transition-all duration-300"
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                  </div>
                )}

                <button
                  onClick={(e) => handleDelete(e, job.id)}
                  className="p-2 rounded-lg text-dark-muted hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                  title="Delete scan"
                >
                  <Trash2 className="w-4 h-4" />
                </button>

                <div className="w-8 h-8 rounded-lg bg-dark-bg border border-dark-border flex items-center justify-center text-dark-muted group-hover:text-white">
                  <ArrowUpRight className="w-4 h-4" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
