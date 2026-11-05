# ScanForge API Specification (docs/API.md)

Authoritative OpenAPI & HTTP contract for the ScanForge 3D Reconstruction Platform.

---

## 1. Overview & Conventions

- Base URL: `/api`
- Content Type: `application/json` (except file uploads and SSE)
- Error Response Format:
  ```json
  {
    "detail": "Descriptive error message"
  }
  ```
- SSE Streaming: `text/event-stream` with `Cache-Control: no-cache`

---

## 2. Endpoints

### System & Health

#### `GET /api/health`
Returns system component connectivity and resource availability.
- **Response `200 OK`**:
  ```json
  {
    "status": "ok",
    "engine": "mock",
    "db": "connected",
    "redis": "connected",
    "disk_free_gb": 45.2,
    "version": "0.1.0"
  }
  ```

#### `GET /api/capabilities`
Returns available scan types, quality presets, runtime format availability, limits, and active engine mode. Available converters (such as Blender) are detected dynamically at runtime.
- **Response `200 OK`**:
  ```json
  {
    "engine": "mock",
    "gpu_available": false,
    "scan_types": ["photo", "gaussian_splat", "lidar"],
    "lidar_enabled": false,
    "quality_presets": ["draft", "standard", "high"],
    "mesh_routes": ["auto", "photogrammetry", "depth_fusion"],
    "format_matrix": {
      "photo": ["glb", "obj", "ply", "stl", "xyz"],
      "gaussian_splat": ["ply", "splat", "spz"],
      "lidar": ["glb", "ply", "xyz"]
    },
    "runtime_converters": {
      "blender": false,
      "fbx_supported": false,
      "usdz_supported": false
    },
    "limits": {
      "max_upload_mb": 2048,
      "max_video_seconds": 180,
      "max_frames_photo": 300,
      "max_frames_3dgs": 300
    }
  }
  ```

---

### Job Management

#### `POST /api/jobs`
Submit a scan job with video or image archive upload.
- **Pre-flight Storage Guard**: Checks available disk space. If free space is less than `SCANFORGE_MIN_FREE_DISK_GB` (default: 5.0 GB), rejects the upload with `507 Insufficient Storage`.
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `file`: Binary file (`.mp4`, `.mov`, `.zip`) — optional if `server_file_path` is specified
  - `server_file_path`: (Optional string) Absolute server-side filesystem path to a video/archive already present on disk (bypasses Nginx upload buffering)
  - `scan_type`: `photo` | `gaussian_splat` | `lidar`
  - `quality`: `draft` | `standard` | `high` (default: `standard`)
  - `output_formats`: JSON string array, e.g. `["glb", "obj"]`
  - `options`: JSON string object (JobOptions)
- **JobOptions Schema**:
  ```json
  {
    "include_mesh": false,
    "mesh_route": "auto",
    "poly_target": null,
    "texture_size": 4096,
    "up_axis": "y",
    "units": "m",
    "mask_background": false
  }
  ```
- **Response `202 Accepted`**:
  ```json
  {
    "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "queued",
    "message": "Job enqueued successfully"
  }
  ```
- **Error Response `507 Insufficient Storage`**:
  ```json
  {
    "detail": "Insufficient storage space: 2.10 GB free, minimum 5.0 GB required. Please clean up old jobs or free disk space."
  }
  ```

#### `GET /api/jobs`
List scan jobs with pagination.
- **Query Params**: `limit` (default: 20), `offset` (default: 0), `status` (optional)
- **Response `200 OK`**:
  ```json
  {
    "total": 1,
    "items": [
      {
        "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "status": "completed",
        "scan_type": "photo",
        "quality": "standard",
        "current_stage": "export",
        "progress": 100,
        "created_at": "2026-10-09T10:00:00Z",
        "started_at": "2026-10-09T10:00:05Z",
        "completed_at": "2026-10-09T10:02:15Z",
        "error": null
      }
    ]
  }
  ```

#### `GET /api/jobs/{id}`
Retrieve complete job status, stage logs, and generated artifacts.
- **Response `200 OK`**:
  ```json
  {
    "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "status": "completed",
    "scan_type": "photo",
    "quality": "standard",
    "current_stage": "export",
    "progress": 100,
    "cumulative_scale": 1.0,
    "error": null,
    "error_code": null,
    "error_details": null,
    "log_tail": ["[COLMAP] Registered 293 / 293 frames (100.0%)"],
    "options": {
      "mesh_route": "auto"
    },
    "output_formats": ["glb", "obj", "ply"],
    "original_filename": "room.mp4",
    "created_at": "2026-10-09T10:00:00Z",
    "started_at": "2026-10-09T10:00:05Z",
    "completed_at": "2026-10-09T10:02:15Z",
    "artifacts": []
  }
  ```
- **Error Diagnostics Schema**:
  When `status` is `"failed"`, `error_code` contains a machine-readable failure category (`ERR_LOW_SFM_REGISTRATION`, `ERR_MOTION_BLUR`, `ERR_PURE_ROTATION`, `ERR_CUDA_OOM`, `ERR_CORRUPT_INPUT`, or `ERR_GENERIC_FAILURE`), and `error_details` provides structured guidance:
  ```json
  {
    "error_code": "ERR_LOW_SFM_REGISTRATION",
    "error_details": {
      "title": "Insufficient Camera Registration",
      "reason": "SfM registered fewer than 60% of video frames due to poor feature matches or low overlap.",
      "checklist": [
        "Aim for > 70% frame overlap.",
        "Walk in a slow, continuous perimeter loop around the room.",
        "Ensure even lighting; avoid featureless blank walls by including corners or furniture in view."
      ]
    }
  }
  ```

#### `GET /api/jobs/{id}/events`
Server-Sent Events (SSE) stream for real-time progress and logging.
- **Behavior**: On connect, immediately replays the current stage, progress, and recent log lines before streaming live events.
- **Event Types**:
  - `stage`: `{"stage": "mesh_reconstruct", "progress": 45, "message": "Densifying point cloud"}`
  - `log`: `{"timestamp": "10:01:02", "line": "[OpenMVS] Points: 154,230"}`
  - `completed`: `{"job_id": "...", "status": "completed"}`
  - `cancelled`: `{"job_id": "...", "status": "cancelled", "message": "Job cancelled by user"}`
  - `error`: `{"job_id": "...", "status": "failed", "error": "CUDA out of memory", "error_code": "ERR_CUDA_OOM", "error_details": {...}}`

#### `POST /api/jobs/{id}/cancel`
Cancel a queued or currently executing job across container boundaries via Redis bridge (`scanforge:cancel:{id}`). Kills active subprocesses and their process groups (`os.killpg`) within `< 3.0s`, freeing GPU VRAM immediately. Job status transitions to `cancelled` (never `failed`).
- **Response `200 OK`**: `{"status": "cancelled", "job_id": "..."}`

#### `POST /api/jobs/{id}/resume`
Idempotent crash resume for failed or cancelled jobs. Resets job status to `queued`, clears error and Redis cancel flags, and re-enqueues the job. Pipeline stages utilize SHA-256 parameter and input hashing (`.cache_<stage>.json`) to automatically skip completed stages (0.0s runtime) and resume directly from the interruption point.
- **Response `200 OK`**: Job object (resumed).
- **Error `400 Bad Request`**: If job is currently active or completed.

#### `POST /api/jobs/{id}/cleanup-scratch`
Purges heavy intermediate scratch files (raw `.npy` depth maps, `.dmap` depth fields, intermediate dense point clouds) for completed jobs, reclaiming `> 80%` disk space while strictly preserving all deliverable assets (`mesh.glb`, `mesh.ply`, `model.splat`, `preview_textured.glb`, `floor_plan.*`, `quality_report.json`, and `sparse_txt/`).
- **Response `200 OK`**: `{"job_id": "...", "reclaimed_bytes": 105481200, "reclaimed_mb": 100.59}`

#### `DELETE /api/jobs/{id}`
Atomically deletes job record from the database, removes all workdir assets, uploads, and registered artifacts.
- **Response `200 OK`**: `{"status": "deleted", "job_id": "..."}`

---

### Artifacts & Downloads

#### `GET /api/jobs/{id}/artifacts`
List generated 3D files and reports for a completed job.
- **Response `200 OK`**:
  ```json
  [
    {
      "id": "art-1",
      "format": "glb",
      "kind": "mesh",
      "filename": "scan_mesh.glb",
      "size_bytes": 14205800,
      "download_url": "/api/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/download/glb"
    }
  ]
  ```

#### `GET /api/jobs/{id}/download/{format}`
Download a specific format (e.g., `glb`, `obj`, `ply`, `splat`).
- Returns binary file stream.

#### `GET /api/jobs/{id}/download-all`
Download all generated output artifacts packaged into a single ZIP archive.
- Returns `application/zip`.

---

### Calibration & Measurement

#### `POST /api/jobs/{id}/calibrate`
Scale calibration using two 3D mesh points and user-measured real-world distance.
- **Request Body**:
  ```json
  {
    "point_a": [1.2, 0.4, -2.1],
    "point_b": [2.5, 0.4, -2.1],
    "real_distance": 1.3
  }
  ```
- **Scale Calculation Rule**:
  Stores cumulative scale:
  `measured_distance = ||point_a - point_b||`
  `new_factor = real_distance / measured_distance`
  `cumulative_scale = current_scale * new_factor`
- **Behavior**: Re-runs from `ScaleStage` onward; upstream SfM and meshing stages remain cached.
- **Response `202 Accepted`**:
  ```json
  {
    "status": "calibrating",
    "measured_distance": 1.3,
    "applied_factor": 1.0,
    "cumulative_scale": 1.0
  }
  ```

#### `GET /api/jobs/{id}/report`
Quality report and room metrics JSON.
- **Response `200 OK`**:
  ```json
  {
    "vertex_count": 120500,
    "face_count": 240000,
    "hole_count": 0,
    "dimensions_meters": {
      "length": 5.4,
      "width": 3.8,
      "height": 2.6
    },
    "floor_area_sqm": 20.52,
    "cumulative_scale": 1.0,
    "up_axis": "y"
  }
  ```
