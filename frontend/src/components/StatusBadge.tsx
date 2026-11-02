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
        return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-sm shadow-emerald-500/10";
      case "running":
      case "preprocessing":
      case "exporting":
        return "bg-cyan-500/10 text-cyan-400 border-cyan-500/30 animate-pulse shadow-sm shadow-cyan-500/10";
      case "queued":
        return "bg-amber-500/10 text-amber-400 border-amber-500/30";
      case "failed":
        return "bg-rose-500/10 text-rose-400 border-rose-500/30 shadow-sm shadow-rose-500/10";
      case "cancelled":
        return "bg-zinc-500/10 text-zinc-400 border-zinc-500/30";
      default:
        return "bg-zinc-500/10 text-zinc-400 border-zinc-500/30";
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider border ${getStyles()} ${className}`}
    >
      {status}
    </span>
  );
};
