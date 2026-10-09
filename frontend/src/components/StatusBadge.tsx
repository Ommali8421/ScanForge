import React from "react";
import { JobStatus } from "../api/types";

interface Props {
  status: JobStatus;
  className?: string;
}

export const StatusBadge: React.FC<Props> = ({ status, className = "" }) => {
  const getStyles = () => {
    switch (status) {
      case "completed":
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
      case "running":
      case "preprocessing":
      case "exporting":
        return "bg-blue-500/10 text-blue-400 border-blue-500/30 animate-pulse";
      case "queued":
        return "bg-amber-500/10 text-amber-400 border-amber-500/30";
      case "failed":
        return "bg-rose-500/10 text-rose-400 border-rose-500/30";
      case "cancelled":
        return "bg-slate-500/10 text-slate-400 border-slate-500/30";
      default:
        return "bg-slate-500/10 text-slate-400 border-slate-500/30";
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider border ${getStyles()} ${className}`}
    >
      {status}
    </span>
  );
};
