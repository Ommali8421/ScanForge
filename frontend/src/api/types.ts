export type ScanType = "photo" | "gaussian_splat" | "lidar";
export type QualityPreset = "draft" | "standard" | "high";
export type JobStatus = "queued" | "preprocessing" | "running" | "exporting" | "completed" | "failed" | "cancelled";

export interface JobOptions {
  include_mesh?: boolean;
  mesh_route?: "auto" | "photogrammetry" | "depth_fusion";
  poly_target?: number | null;
  texture_size?: number;
  up_axis?: "y" | "z";
  units?: "m" | "cm" | "mm";
  mask_background?: boolean;
  min_registration_ratio?: number;
}

export interface Artifact {
  id: string;
  job_id: string;
  kind: string;
  format: string;
  filename: string;
  size_bytes: number;
  download_url: string;
}

export interface Job {
  id: string;
  status: JobStatus;
  scan_type: ScanType;
  quality: QualityPreset;
  current_stage: string | null;
  progress: number;
  cumulative_scale: number;
  error: string | null;
  log_tail: string[];
  options: JobOptions;
  output_formats: string[];
  original_filename?: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  artifacts?: Artifact[];
}

export interface Capabilities {
  engine: "mock" | "real";
  gpu_available: boolean;
  scan_types: ScanType[];
  lidar_enabled: boolean;
  quality_presets: QualityPreset[];
  mesh_routes: string[];
  format_matrix: Record<string, string[]>;
  runtime_converters: {
    blender: boolean;
    fbx_supported: boolean;
    usdz_supported: boolean;
  };
  limits: {
    max_upload_mb: number;
    max_video_seconds: number;
    max_frames_photo: number;
    max_frames_3dgs: number;
  };
}

export interface Health {
  status: string;
  engine: string;
  db: string;
  redis: string;
  disk_free_gb: number;
  version: string;
}

export interface JobReport {
  vertex_count: number;
  face_count: number;
  hole_count: number;
  dimensions_meters: {
    length: number;
    width: number;
    height: number;
  };
  floor_area_sqm: number;
  cumulative_scale: number;
  up_axis: string;
}
