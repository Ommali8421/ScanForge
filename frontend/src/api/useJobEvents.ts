import { useEffect, useState, useRef } from "react";
import { JobStatus } from "./types";

interface JobEventsState {
  currentStage: string;
  progress: number;
  status: JobStatus;
  logs: string[];
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
}

export function useJobEvents(jobId: string | null) {
  const [state, setState] = useState<JobEventsState>({
    currentStage: "queued",
    progress: 0,
    status: "queued",
    logs: [],
    isConnected: false,
    isCompleted: false,
    error: null,
  });

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`/api/jobs/${jobId}/events`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setState((prev) => ({ ...prev, isConnected: true }));
    };

    es.addEventListener("stage", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setState((prev) => ({
          ...prev,
          currentStage: data.stage || prev.currentStage,
          progress: typeof data.progress === "number" ? data.progress : prev.progress,
          status: data.status || prev.status,
        }));
      } catch {}
    });

    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.line) {
          setState((prev) => ({
            ...prev,
            logs: [...prev.logs, data.line],
          }));
        }
      } catch {}
    });

    es.addEventListener("completed", () => {
      setState((prev) => ({
        ...prev,
        status: "completed",
        progress: 100,
        isCompleted: true,
      }));
      es.close();
    });

    es.addEventListener("error", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setState((prev) => ({
          ...prev,
          status: "failed",
          error: data.error || "Execution failed",
        }));
      } catch {}
    });

    es.addEventListener("cancelled", () => {
      setState((prev) => ({ ...prev, status: "cancelled" }));
      es.close();
    });

    es.onerror = () => {
      setState((prev) => ({ ...prev, isConnected: false }));
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [jobId]);

  return state;
}
