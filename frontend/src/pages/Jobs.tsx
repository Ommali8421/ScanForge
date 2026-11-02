import React, { useEffect, useState, useMemo } from "react";
import { Job, Capabilities } from "../api/types";
import { fetchJobs, deleteJob } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import {
  Box,
  Sparkles,
  Radar,
  Trash2,
  ArrowUpRight,
  Clock,
  RefreshCw,
  Search,
  CheckCircle2,
  Activity,
  Layers,
  Cpu,
  PlusCircle,
} from "lucide-react";

interface Props {
  onSelectJob: (jobId: string) => void;
  onNewScan: () => void;
  capabilities?: Capabilities | null;
}

export const Jobs: React.FC<Props> = ({ onSelectJob, onNewScan, capabilities }) => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<"all" | "running" | "completed" | "failed">("all");
  const [page, setPage] = useState(1);
  const itemsPerPage = 20;

  const loadJobs = async () => {
    try {
      const data = await fetchJobs(100, 0);
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
    if (!confirm("Permanently delete this reconstruction and all 3D assets?")) return;
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
        return <Sparkles className="w-5 h-5 text-amber-400" />;
      case "lidar":
        return <Radar className="w-5 h-5 text-purple-400" />;
      default:
        return <Box className="w-5 h-5 text-cyan-400" />;
    }
  };

  // KPI calculations
  const totalCount = jobs.length;
  const runningCount = jobs.filter((j) =>
    ["queued", "running", "preprocessing", "exporting"].includes(j.status)
  ).length;
  const completedCount = jobs.filter((j) => j.status === "completed").length;
  const failedCount = jobs.filter((j) =>
    !["queued", "running", "preprocessing", "exporting", "completed"].includes(j.status)
  ).length;
  const isMock = capabilities?.engine === "mock";

  // Filtered jobs list
  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      // Status filter
      if (filterStatus === "running") {
        if (!["queued", "running", "preprocessing", "exporting"].includes(job.status)) {
          return false;
        }
      } else if (filterStatus === "completed") {
        if (job.status !== "completed") return false;
      } else if (filterStatus === "failed") {
        if (["queued", "running", "preprocessing", "exporting", "completed"].includes(job.status)) {
          return false;
        }
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesId = job.id.toLowerCase().includes(q);
        const matchesFilename = (job.original_filename || "").toLowerCase().includes(q);
        const matchesType = job.scan_type.toLowerCase().includes(q);
        const matchesQuality = job.quality.toLowerCase().includes(q);
        return matchesId || matchesFilename || matchesType || matchesQuality;
      }

      return true;
    });
  }, [jobs, filterStatus, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / itemsPerPage));
  const paginatedJobs = filteredJobs.slice((page - 1) * itemsPerPage, page * itemsPerPage);

  const formatRelativeTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return "Just now";
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHrs = Math.floor(diffMin / 60);
      if (diffHrs < 24) return `${diffHrs}h ago`;
      const diffDays = Math.floor(diffHrs / 24);
      return `${diffDays}d ago`;
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-mono font-bold uppercase tracking-widest text-cyan-400 bg-cyan-500/10 px-2.5 py-0.5 rounded-full border border-cyan-500/20">
              Workspace Queue
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
            Reconstruction Library
          </h1>
          <p className="text-zinc-400 text-sm mt-1">
            Track active GPU reconstructions, review quality metrics, and download 3D deliverables.
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <button
            onClick={loadJobs}
            className="p-2.5 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-800/80 transition-colors shadow-sm"
            title="Refresh scan queue"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={onNewScan}
            className="px-4 py-2.5 rounded-2xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/20 transition-all flex items-center gap-1.5"
          >
            <PlusCircle className="w-4 h-4" />
            <span>New Scan</span>
          </button>
        </div>
      </div>

      {/* Top KPI Summary Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="p-4 rounded-3xl border border-zinc-800 bg-zinc-950/70 shadow-lg">
          <div className="flex items-center justify-between text-zinc-400 mb-2">
            <span className="text-xs font-semibold">Total Scans</span>
            <Layers className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-black text-white font-mono tabular-nums">
            {totalCount}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5">In database catalog</div>
        </div>

        <div className="p-4 rounded-3xl border border-zinc-800 bg-zinc-950/70 shadow-lg">
          <div className="flex items-center justify-between text-zinc-400 mb-2">
            <span className="text-xs font-semibold">Active Jobs</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-black text-cyan-400 font-mono tabular-nums flex items-center gap-2">
            <span>{runningCount}</span>
            {runningCount > 0 && (
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
            )}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5">
            {runningCount > 0 ? "Consuming worker queue" : "Worker idle / ready"}
          </div>
        </div>

        <div className="p-4 rounded-3xl border border-zinc-800 bg-zinc-950/70 shadow-lg">
          <div className="flex items-center justify-between text-zinc-400 mb-2">
            <span className="text-xs font-semibold">Completed</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-emerald-400 font-mono tabular-nums">
            {completedCount}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5">Available for download</div>
        </div>

        <div className="p-4 rounded-3xl border border-zinc-800 bg-zinc-950/70 shadow-lg">
          <div className="flex items-center justify-between text-zinc-400 mb-2">
            <span className="text-xs font-semibold">System Status</span>
            <Cpu className="w-4 h-4 text-brand-400" />
          </div>
          <div className={`text-sm font-bold mt-1 font-mono ${isMock ? "text-amber-400" : "text-emerald-400"}`}>
            {isMock ? "Mock Engine (Simulation)" : "GPU Engine (CUDA sm_89)"}
          </div>
          <div className="text-[11px] text-zinc-500 mt-1">1 GPU concurrency lock</div>
        </div>
      </div>

      {/* Search Bar & Filter Strip */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-zinc-950/60 p-2 rounded-2xl border border-zinc-800">
        {/* Filter Pills */}
        <div className="flex items-center space-x-1 overflow-x-auto no-scrollbar p-1">
          <button
            onClick={() => setFilterStatus("all")}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              filterStatus === "all"
                ? "bg-zinc-800 text-white shadow-sm"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            All ({totalCount})
          </button>
          <button
            onClick={() => setFilterStatus("running")}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              filterStatus === "running"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
            <span>Running ({runningCount})</span>
          </button>
          <button
            onClick={() => setFilterStatus("completed")}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              filterStatus === "completed"
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>Completed ({completedCount})</span>
          </button>
          <button
            onClick={() => setFilterStatus("failed")}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              filterStatus === "failed"
                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
            <span>Failed ({failedCount})</span>
          </button>
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search by ID, name, or scan type..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="text-center py-20 text-zinc-500 text-xs font-mono">
          Loading library items...
        </div>
      ) : filteredJobs.length === 0 ? (
        /* Rich Illustrated Empty State */
        <div className="border border-zinc-800/80 bg-zinc-950/60 rounded-3xl p-12 text-center space-y-4 shadow-xl max-w-xl mx-auto my-12">
          <div className="w-16 h-16 rounded-3xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center mx-auto shadow-lg shadow-indigo-500/10">
            <Box className="w-8 h-8 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-tight">
              {searchQuery || filterStatus !== "all"
                ? "No matching reconstructions found"
                : "No scans in your library yet"}
            </h3>
            <p className="text-xs text-zinc-400 mt-1 max-w-sm mx-auto leading-relaxed">
              {searchQuery || filterStatus !== "all"
                ? "Try adjusting your search query or clear the active filter pills."
                : "Upload an interior video walkthrough or photo archive to launch your first high-precision 3D reconstruction."}
            </p>
          </div>
          <div>
            {searchQuery || filterStatus !== "all" ? (
              <button
                onClick={() => {
                  setSearchQuery("");
                  setFilterStatus("all");
                }}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-xl text-xs font-semibold transition-colors"
              >
                Clear Filters
              </button>
            ) : (
              <button
                onClick={onNewScan}
                className="px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white rounded-2xl text-xs font-bold transition-all shadow-lg shadow-indigo-600/25"
              >
                Start First Scan
              </button>
            )}
          </div>
        </div>
      ) : (
        /* List of Polished Glassmorphic Cards */
        <div className="space-y-3">
          {paginatedJobs.map((job) => {
            const isJobRunning = ["queued", "running", "preprocessing", "exporting"].includes(
              job.status
            );
            return (
              <div
                key={job.id}
                onClick={() => onSelectJob(job.id)}
                className="border border-zinc-800/80 bg-zinc-950/70 hover:border-zinc-700 hover:bg-zinc-900/60 rounded-3xl p-5 transition-all cursor-pointer shadow-lg hover:shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 group"
              >
                {/* Left Info */}
                <div className="flex items-start sm:items-center space-x-3.5 min-w-0">
                  <div className="w-12 h-12 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center flex-shrink-0 group-hover:scale-105 transition-transform shadow-inner">
                    {getScanIcon(job.scan_type)}
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center space-x-2.5 flex-wrap">
                      <h3 className="text-sm font-bold text-white truncate tracking-tight group-hover:text-cyan-300 transition-colors">
                        {job.original_filename || `Scan ${job.id.substring(0, 8)}`}
                      </h3>
                      <StatusBadge status={job.status} />
                    </div>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-400 mt-1 font-mono">
                      <span className="capitalize text-zinc-300 font-semibold">
                        {job.scan_type.replace("_", " ")}
                      </span>
                      <span>•</span>
                      <span className="capitalize">{job.quality} Quality</span>
                      <span>•</span>
                      <span className="text-zinc-500 truncate max-w-[140px]">
                        ID: {job.id.slice(0, 8)}
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1 text-zinc-400">
                        <Clock className="w-3 h-3" />
                        {formatRelativeTime(job.created_at)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right Progress & Quick Actions */}
                <div className="flex items-center space-x-4 self-end sm:self-auto flex-shrink-0">
                  {isJobRunning && (
                    <div className="w-32 text-right">
                      <div className="flex justify-between items-center text-[11px] font-mono mb-1">
                        <span className="text-zinc-400 capitalize truncate max-w-[80px]">
                          {job.current_stage || "Queued"}
                        </span>
                        <span className="text-cyan-400 font-bold tabular-nums">
                          {job.progress}%
                        </span>
                      </div>
                      <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden border border-zinc-800">
                        <div
                          className="bg-gradient-to-r from-indigo-500 to-cyan-400 h-full rounded-full transition-all duration-300"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Artifacts count pill */}
                  {job.status === "completed" && job.artifacts && (
                    <div className="hidden md:flex items-center gap-1 text-[11px] font-mono text-zinc-400 bg-zinc-900/80 px-2.5 py-1 rounded-xl border border-zinc-800">
                      <span>{job.artifacts.length} deliverable(s)</span>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={(e) => handleDelete(e, job.id)}
                    className="p-2 rounded-xl text-zinc-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                    title="Delete scan"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>

                  <div className="w-9 h-9 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 group-hover:text-white group-hover:border-zinc-700 transition-colors">
                    <ArrowUpRight className="w-4 h-4" />
                  </div>
                </div>
              </div>
            );
          })}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-4 text-xs font-mono text-zinc-400 border-t border-zinc-800/80">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3.5 py-1.5 rounded-xl border border-zinc-800 bg-zinc-900 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                Previous Page
              </button>
              <span className="tabular-nums">Page {page} of {totalPages}</span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="px-3.5 py-1.5 rounded-xl border border-zinc-800 bg-zinc-900 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                Next Page
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
