import { Job, Capabilities, Health, JobReport } from "./types";

const API_BASE = "/api";

export async function fetchHealth(): Promise<Health> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function fetchCapabilities(): Promise<Capabilities> {
  const res = await fetch(`${API_BASE}/capabilities`);
  if (!res.ok) throw new Error("Failed fetching capabilities");
  return res.json();
}

export async function fetchJobs(limit = 50, offset = 0): Promise<{ total: number; items: Job[] }> {
  const res = await fetch(`${API_BASE}/jobs?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error("Failed fetching jobs list");
  return res.json();
}

export async function fetchJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(`Failed fetching job ${id}`);
  return res.json();
}

export async function createJob(
  file: File,
  scanType: string,
  quality: string,
  outputFormats: string[],
  options: Record<string, any>,
  onProgress?: (percent: number) => void
): Promise<{ job_id: string; status: string; message: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("scan_type", scanType);
  formData.append("quality", quality);
  formData.append("output_formats", JSON.stringify(outputFormats));
  formData.append("options", JSON.stringify(options));

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/jobs`);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const pct = Math.round((event.loaded / event.total) * 100);
          onProgress(pct);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Invalid response format"));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || "Upload failed"));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(formData);
  });
}

export async function cancelJob(id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/jobs/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error("Failed cancelling job");
  return res.json();
}

export async function deleteJob(id: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed deleting job");
  return res.json();
}

export async function calibrateScale(
  id: string,
  pointA: [number, number, number],
  pointB: [number, number, number],
  realDistance: number
): Promise<{ status: string; measured_distance: number; applied_factor: number; cumulative_scale: number }> {
  const res = await fetch(`${API_BASE}/jobs/${id}/calibrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      point_a: pointA,
      point_b: pointB,
      real_distance: realDistance,
    }),
  });
  if (!res.ok) throw new Error("Failed submitting calibration");
  return res.json();
}

export async function fetchJobReport(id: string): Promise<JobReport> {
  const res = await fetch(`${API_BASE}/jobs/${id}/report`);
  if (!res.ok) throw new Error("Failed fetching job report");
  return res.json();
}

export function getDownloadUrl(jobId: string, format: string): string {
  return `${API_BASE}/jobs/${jobId}/download/${format}`;
}

export function getDownloadAllUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/download-all`;
}

export function getDownloadLogUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/log`;
}

export async function fetchJobCuts(jobId: string): Promise<{ cuts?: any[]; files?: string[] }> {
  try {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/cuts`);
    if (!res.ok) return { cuts: [] };
    return res.json();
  } catch {
    return { cuts: [] };
  }
}

export function getCutImageUrl(jobId: string, filename: string): string {
  return `${API_BASE}/jobs/${jobId}/cuts/${filename}`;
}

