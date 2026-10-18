# ScanForge — Project Progress & Living Status (progress.md)

> **Single Source of Truth** for current project state, milestone tracking, verified vs. unverified status, architectural decisions, and session resumption.
> **Rule:** Must be updated on every behavior change, milestone transition, bug fix, or verification state change. Never leave this file stale.

---

## 1. Milestones Overview (P0 – P6)

| Milestone | Scope | Status | Commit / Reference |
|---|---|---|---|
| **P0** | Repo skeleton, Docker Compose (mock profile), `doctor.py`, AGENTS.md, API contract, versions pinned | **Done** | `cf97f7c` |
| **P1** | Job system + multipart upload + live SSE streaming + full frontend on MOCK engine | **Accepted** | `e113930` (base), `1e1bbac`, `6918eaa`, `1f6b9f7`, `1e5bf0a`, `b9ee7ab`, `0ccd635` |
| **P2a** | GPU Worker Build (CUDA 12.1.1, COLMAP 3.9.1 sm_89, OpenMVS v2.2.0 sm_89, Blender 4.1.0, PyTorch 2.5.1+cu121, Open3D 0.20.0, Trimesh 5.1.1) | **Done** | Verified via `doctor.py` in container & `e2e_smoke.py` |
| **P2b** | Video ingest + adaptive frame extraction + interior-tuned COLMAP SfM (GPU) + trajectory plot + real test run | **Done** | Verified on RTX 4060 GPU with real test video (92.9% registration, 7,803 points, 0.671px error) |
| **P2c** | OpenMVS Route A mesh (Densify, ReconstructMesh, Refine, Texture) + planar repair + floor align + scale calibrate | **Not Started** | Blocked on user review after P2b |
| **P3** | 3DGS training + floater cleanup + splat formats + splat viewer | **Not Started** | Blocked on P2 |
| **P4** | Route B (depth-fusion mesh) + mesh-inclusive 3DGS + Auto heuristic + floor plan + room dimensions | **Not Started** | Blocked on P3 |
| **P5** | Hardening: cancel, resume, cleanup, error messages, comprehensive docs, test suite | **Not Started** | Blocked on P4 |
| **P6** | LiDAR / RGB-D pipeline (feature-flagged `ENABLE_LIDAR=false`) + synthetic tests | **Not Started** | Blocked on P5 |

---

## 2. Verification Matrix (VERIFIED vs. UNVERIFIED)

*Strict verification honesty rule: Never claim something works unless executed with recorded evidence.*

| Component / Feature | State | Evidence / Justification |
|---|---|---|
| Mock Engine Execution | **VERIFIED** | Completed multiple simulated reconstructions emitting procedural interior room mesh |
| Job Submission (Multipart Upload) | **VERIFIED** | Successfully tested via UI and Python script (`scripts/submit_real_run.py`) creating jobs in SQLite DB |
| Redis Job Queue (`scanforge_gpu` / `scanforge_mock`) | **VERIFIED** | Enqueuing validated; worker-gpu consumes from both queues in priority order |
| Live SSE Event Streaming | **VERIFIED** | Real-time events received via Redis PubSub through Nginx port 3000 (`1e1bbac`) |
| Nginx Reverse Proxy (Port 3000) | **VERIFIED** | Reverse-proxies UI (`/`) and API (`/api/`) with chunked transfer and disabled buffering |
| Artifact Generation & Download | **VERIFIED** | Validated download of generated `.ply` (114.5 KB), `.png` (76.0 KB), and `.json` (0.4 KB) outputs |
| Scale Calibration Math | **VERIFIED** | Two consecutive calibrations tested, verifying cumulative scale factor `1.5 * 2.0 = 3.0` |
| Backend Pytest Suite | **VERIFIED** | 22/22 unit & integration tests passing in container (`test_api_jobs.py`, `test_cancel_sfm.py`, `test_capabilities.py`, `test_frame_selection.py`, `test_integration.py`, `test_mock_pipeline.py`, `test_sfm_failure.py`, `test_zip_safe.py`) |
| Real Video Ingestion & ffprobe | **VERIFIED** | `IngestStage` probed duration, dimensions (478x850), stripped audio, normalized color, and baked orientation |
| Adaptive Keyframe Extraction | **VERIFIED** | `FrameExtractionStage` selected 99 keyframes using Laplacian sharpness scoring, Farneback optical flow, and homography rotation check |
| GPU COLMAP SfM (RTX 4060) | **VERIFIED** | `ColmapSfMStage` executed SIFT GPU extraction, sequential + exhaustive matching, bounded Ceres BA: 92/99 frames registered (92.9%), 7,803 3D points, 0.671 px reprojection error, 415 MB peak VRAM, 367 MB peak RAM in 228.4s |
| Camera Trajectory Top-Down Plot | **VERIFIED** | `camera_path.png` generated showing 92 camera nodes, Start/End markers, and 3D spatial points |
| SfM Failure & Cancel Handling | **VERIFIED** | SfM failure under 60% threshold raises typed error; cancel kills active process tree cleanly |
| Portability & Dynamic Tool Resolution | **VERIFIED** | Dynamic binary resolution from PATH/env, runtime COLMAP flag filtering via `--help`, VRAM-aware presets, thread budgeting, stage isolation (27/27 tests passing) |
| OpenMVS Route A Mesh Pipeline | **UNVERIFIED** | Scheduled for Milestone P2c |
| Real 3DGS Training (nerfstudio/splatfacto) | **UNVERIFIED** | P3 scope; not yet implemented or tested on RTX 4060 hardware |
| Real Depth-Fusion Route B | **UNVERIFIED** | P4 scope; monocular depth estimation and TSDF fusion not yet built |
| Apple LiDAR / Record3D Ingestion | **UNVERIFIED** | P6 scope; behind feature flag `ENABLE_LIDAR=false` |
| Public GitHub Backup | **VERIFIED** | Pushed to `https://github.com/Ommali8421/ScanForge.git` (`origin/main`); zero secrets or personal emails |

---

## 3. Known Issues & Fixed Bugs

| Issue | Root Cause | Resolution | Commit Hash |
|---|---|---|---|
| UI stuck at "Queued 0%" | Multi-container SSE isolation: `worker-mock` published events to Redis, but `api` SSE listener was bound to a local in-memory queue. In addition, Nginx buffered streaming responses. | Updated `sse.py` to subscribe to Redis PubSub `job:{job_id}`, enabled `chunked_transfer_encoding on;` with `proxy_buffering off;` in Nginx, and added 2.5s fallback polling in `JobDetail.tsx`. | `1e1bbac` |
| Duplicate Nginx config | Both `docker/nginx.conf` and `frontend/nginx.conf` existed, creating maintenance ambiguity. | Removed `docker/nginx.conf`, retained canonical `frontend/nginx.conf`, updated `docs/SPEC.md`. | `1f6b9f7` |
| Missing LiDAR card in UI when flag disabled | `GET /api/capabilities` excluded `"lidar"` from `scan_types` when `ENABLE_LIDAR=false`, preventing frontend from displaying disabled state. | Updated `capabilities.py` to always include `"lidar"` in `scan_types` with `lidar_enabled` boolean; updated `ScanTypeCards.tsx` badge to "Beta, needs RGB-D capture". | `b9ee7ab` |
| Container pytest import error | `backend/Dockerfile` ran editable pip install before copying source files, leaving `app` module unlinked in fresh builds. | Configured `ENV PYTHONPATH=/app`, added post-copy `pip install -e ".[dev]"`, and added `pythonpath = ["."]` in `pyproject.toml`. | `0ccd635` |
| Untracked `.env` check | Ensure development secrets and local paths are not committed to git repository. | Verified `.env` in `.gitignore`; confirmed `git ls-files .env` is empty. | *Verified* |
| COLMAP mapper Ceres BA iteration stall | Exhaustive matching on dense scene graph caused Ceres solver to run unconstrained global BA iterations. | Bounded `--Mapper.ba_global_max_num_iterations 30`, `--Mapper.ba_local_max_num_iterations 20`, `--Mapper.ba_global_max_refinements 2`, `--Mapper.ba_local_max_refinements 1`, and increased sequential overlap to 25. | `3d9ad27` |
| Multi-queue worker dispatch | GPU profile worker only listened to `scanforge_gpu`, leaving mock and test jobs stalled in `scanforge_mock`. | Enabled worker to listen to both `['scanforge_gpu', 'scanforge_mock']` in priority order. | `3d9ad27` |

---

## 4. Architectural Decisions

1. **Redis Pub/Sub for SSE Across Containers**:
   - Background workers run in separate containers (`worker-mock`, `worker-gpu`) from the web API (`api`).
   - All pipeline progress and log events are published to Redis channel `job:{job_id}`.
   - The FastAPI SSE endpoint (`/api/jobs/{id}/events`) subscribes to Redis asynchronously (`redis.asyncio`) and streams events live to clients.
2. **Reverse Proxy Buffering Disabled for SSE**:
   - `frontend/nginx.conf` proxies `/api/` to `http://api:8000/api/` with `proxy_buffering off;`, `proxy_cache off;`, and `chunked_transfer_encoding on;` to guarantee instantaneous event delivery.
3. **Pluggable Engine Interface**:
   - `SCANFORGE_ENGINE=mock` uses lightweight, fast procedural generators suitable for rapid testing and CI.
   - `SCANFORGE_ENGINE=real` activates external tool wrappers (`ColmapSfM`, `OpenMVSDense`, `NerfstudioSplatfacto`).
4. **Resilient Matcher Fallback & Bounded Bundle Adjustment**:
   - Sequential matching with overlap 25 is used first.
   - If registered frames are <90% (for $\le 200$ frames), exhaustive matching is attempted with a 600s timeout. If exhaustive fails or produces fewer frames, the pipeline gracefully falls back to the sequential model.
   - Ceres BA iterations are bounded to prevent infinite or multi-hour stalls on dense scene graphs.
5. **Scale Calibration Pipeline Invariance**:
   - Calling `POST /api/jobs/{id}/calibrate` does not restart heavy upstream SfM or meshing stages. It only triggers `ScaleStage` and exporter stages, applying cumulative scaling factor `current_scale * (real_distance / measured_distance)`.

---

## 5. Environment Specifications

- **Remote Repository**: `https://github.com/Ommali8421/ScanForge.git` (Public, branch `main`).
- **Host Machine**: Windows 11 Laptop, 15 GB RAM, NVIDIA GeForce RTX 4060 Laptop GPU (8 GB VRAM, Ada arch, compute capability 8.9).
- **Runtime OS**: WSL2 (Ubuntu 22.04 LTS), 11 GB RAM limit, 16 GB swap.
- **Project Directory**: Native WSL filesystem (`/home/om_mali/scanforge`).
- **Containerization**: Docker Desktop with WSL2 backend + NVIDIA Container Toolkit (`nvidia-smi` accessible).
- **Environment Profiles**:
  - `mock`: default (`COMPOSE_PROFILES=mock`), runs `api`, `worker-mock`, `redis`, `frontend`.
  - `gpu`: activated via `make up-gpu` or `SCANFORGE_ENGINE=real COMPOSE_PROFILES=gpu docker compose up -d`, builds and runs heavy CUDA image with COLMAP, OpenMVS, and nerfstudio.

---

## 6. Next Steps (Immediate Steps for Milestone P2c)

*P2b completed and verified on real test video with RTX 4060 GPU. Awaiting user review before proceeding to Milestone P2c.*

1. **User Review on Milestone P2b**: Present reconstruction report, camera trajectory plot, resource metrics (VRAM/RAM), and verified logs from the real room video run.
2. **Milestone P2c Planning**:
   - OpenMVS dense point cloud reconstruction (`DensifyPointCloud` at resolution level 2, with auto-retry at resolution level 3 on OOM).
   - Watertight tetrahedral Delaunay surface mesh reconstruction (`ReconstructMesh`).
   - Mesh post-processing: non-manifold edge cleanup, RANSAC plane detection and hole repair (Open3D), floor leveling to Y=0, planarity-aware decimation.
   - OpenMVS texture baking (`TextureMesh`) using undistorted cameras.
   - Exporters to canonical formats (GLB, OBJ, PLY, STL, XYZ, FBX, USDZ).

---

## 7. Session Resumption Guide

For any agent resuming work in this codebase:
1. **Read this file (`progress.md`) first** to understand the current milestone state and recent bug fixes.
2. Check `AGENTS.md` and `docs/SPEC.md` for conventions and strict architecture rules.
3. Verify that the current stack is healthy using `make smoke` and `docker compose ps`.
4. Always check git status (`git status`) to ensure the working tree is clean.
5. Update this file whenever you complete a milestone, fix a bug, or execute a new verification.
