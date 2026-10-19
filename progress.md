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
| **P2b** | Video ingest + adaptive frame extraction + interior-tuned COLMAP SfM (GPU) + 4-panel diagnostic trajectory plot + scene-cut detection + low-texture filtering + real test runs | **Done** | Verified on RTX 4060 GPU with 3 real video runs (`house_test_30s.mp4`, `bedroom_vid.mp4` with/without filter) |
| **P2c** | OpenMVS Route A mesh (Densify, ReconstructMesh, Refine, Texture) + planar repair + floor align + scale calibrate | **Not Started** | **UNVERIFIED** — Stopped for user review after P2b |
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
| Artifact Generation & Download | **VERIFIED** | Validated download of generated `.ply`, `.png`, and `.json` outputs, including directory artifacts |
| Scale Calibration Math | **VERIFIED** | Two consecutive calibrations tested, verifying cumulative scale factor `1.5 * 2.0 = 3.0` |
| Backend Pytest Suite | **VERIFIED** | 19/19 tests passing in container (`test_sfm_diagnostic.py`, `test_portability.py`, `test_colmap_compat.py`) |
| Dynamic VRAM Detection & Tiers | **VERIFIED** | Tested `SCANFORGE_VRAM_GB` override vs `nvidia-smi` total memory minus 0.5 GB safety margin; logs tier selection and source; preserves 2000 px COLMAP cap on 8 GB tier (`f1ec5ac`) |
| Real Video Ingestion & Scene Cuts | **VERIFIED** | Probed duration, dimensions, normalized color, and detected scene transitions via HSV histogram correlation (detected 5 cuts in `bedroom_vid.mp4`, 0 in `house_test_30s.mp4`) |
| Adaptive Keyframe Extraction | **VERIFIED** | Evaluated frames with Laplacian sharpness scoring, Farneback optical flow, and homography rotation check |
| Low-Texture SIFT Filtering | **VERIFIED** | Automatic dropping of feature-starved frames before matching (`min_sift_keypoints=100`); dropped 11 featureless wall/ceiling frames in `bedroom_vid.mp4`, logged in `sfm_report.json` |
| GPU COLMAP SfM (RTX 4060) | **VERIFIED** | Full GPU SIFT extraction, sequential + auto exhaustive matching, unconstrained Ceres BA. House clip: 92/99 registered (92.9%), 8,214 points, 0.662 px error in 159.6s. Mapper runtime 54.0s (no timeout, timeout is 1800s). |
| 4-Panel Diagnostic Camera Trajectory | **VERIFIED** | `camera_path.png` generated with: (1) 3D camera trajectory colored by frame index, broken at gaps/jumps, equal axes, high-contrast points, (2) Side view (Z-Y / X-Z), (3) Consecutive distance ratio to median with jumps >5x flagged, (4) Per-frame SIFT keypoints, consecutive verified matches, and rotation-vs-translation metric |
| COLMAP Multi-Version Adaptation | **VERIFIED** | Verified rename mapping against 3.9.1 and 3.13.0 help fixtures; hang protection via timeout without Ceres iteration caps; FAISS loop detection fallback (`59a4724`) |
| OpenMVS Route A Mesh Pipeline | **UNVERIFIED** | Scheduled for Milestone P2c |
| Real 3DGS Training (nerfstudio/splatfacto) | **UNVERIFIED** | P3 scope; not yet implemented or tested on RTX 4060 hardware |
| Real Depth-Fusion Route B | **UNVERIFIED** | P4 scope; monocular depth estimation and TSDF fusion not yet built |
| Apple LiDAR / Record3D Ingestion | **UNVERIFIED** | P6 scope; behind feature flag `ENABLE_LIDAR=false` |
| Public GitHub Backup | **VERIFIED** | Pushed to `https://github.com/Ommali8421/ScanForge.git` (`origin/main`); zero secrets or personal emails |

---

## 3. Real Hardware Verification Results (Milestone P2b)

### Side-by-Side Comparison: Clip 1 vs Clip 2 (Filtered vs Unfiltered)

| Metric | Clip 1 (`house_test_30s.mp4`) — Earlier Run | Clip 1 (`house_test_30s.mp4`) — Uncapped Ceres (Run 1) | Clip 2 (`bedroom_vid.mp4`) — With SIFT Filter (Run 2) | Clip 2 (`bedroom_vid.mp4`) — No SIFT Filter (Run 3) |
|---|---|---|---|---|
| **Job ID** | `e113930...` | `bcaa88f4-2ffa-4e56-998b-76c6f15dbf7d` | `4179ece6-fd3d-4eef-b432-3474fedb858c` | `65a6fc3e-31b5-4e9b-9299-965b39035b1b` |
| **Duration / Res** | 30.0 s, 478x850, 60 fps | 30.0 s, 478x850, 60 fps | 90.5 s, 478x850, 30 fps | 90.5 s, 478x850, 30 fps |
| **Frames Extracted** | 99 | 99 | 180 | 180 |
| **Low-Texture Filter** | Disabled | Enabled (0 dropped) | Enabled (11 dropped: idx 47, 92, 154, 155, 156, 159, 162, 163, 164, 165, 172) | Disabled (0 dropped) |
| **Active Match Frames** | 99 | 99 | 169 | 180 |
| **Scene Cuts Detected** | 0 | 0 | 5 (t=24.0s, 24.5s, 66.5s, 87.0s, 89.0s) | 5 (t=24.0s, 24.5s, 66.5s, 87.0s, 89.0s) |
| **Sequential Reg.** | 68 / 99 | 68 / 99 (auto exhaustive triggered) | 12 / 180 (auto exhaustive triggered) | 12 / 180 (auto exhaustive triggered) |
| **Final Registered** | 92 / 99 (92.9%) | **92 / 99 (92.9%)** | **61 / 180 (33.9%)** | **64 / 180 (35.6%)** |
| **3D Sparse Points** | 7,803 | **8,214 (+5.3%)** | **7,444** | **8,431** |
| **Reprojection Error** | 0.671 px | **0.662 px (-1.3%)** | **0.553 px** | **0.546 px** |
| **Mean Track Length** | N/A | **4.676** | **4.313** | **4.258** |
| **Obs / Points per Img** | N/A | 417.489 obs / 89.3 pts | 526.344 obs / 122.0 pts | 559.906 obs / 131.7 pts |
| **Sub-models Found** | 2 | 2 (submodel_0: 2 imgs, 572 pts; submodel_1: 92 imgs, 8,214 pts) | 2 (submodel_0: 61 imgs, 7,444 pts; submodel_1: 2 imgs, 442 pts) | 3 (submodel_0: 64 imgs, 8,431 pts; submodel_1: 2 imgs; submodel_2: 2 imgs) |
| **Unregistered Frames** | [14-18, 97-98] | [14, 15, 16, 17, 18, 97, 98] | 119 frames | 116 frames |
| **Trajectory Jumps (>5x)**| N/A | **0 flagged** (max ratio: 2.12x) | **6 flagged** (max ratio: 13.43x) | **6 flagged** (max ratio: 13.43x) |
| **Mapper Runtime** | Bounded (~90s) | **54.0s** (Timeout: 1800s, did NOT fire) | **150.8s** (Timeout: 1800s, did NOT fire) | **176.7s** (Timeout: 1800s, did NOT fire) |
| **Total SfM Duration** | 228.4 s | **159.6 s (30.1% faster)** | **345.1 s** | **377.9 s** |

### Key Observations & Diagnostic Findings

1. **Ceres Iteration Uncapping (Item 3)**:
   - Removing the earlier artificial Ceres BA iteration caps (`--Mapper.ba_global_max_num_iterations 30`, etc.) did **not** hang on RTX 4060 with COLMAP 3.9.1.
   - Mapper runtime was **54.0s**, and the timeout (1800s) did **not** fire.
   - Point count increased by +411 points (8,214 vs 7,803), reprojection error improved from 0.671 px to 0.662 px, and total SfM runtime was 30% faster (159.6s vs 228.4s).
2. **SIFT Low-Texture Filter Performance (Addendum)**:
   - On `bedroom_vid.mp4`, the low-texture filter automatically dropped **11 frames** whose SIFT keypoints were below the conservative threshold of 100 (featureless ceiling/wall sweeps: idx 47, 92, 154, 155, 156, 159, 162, 163, 164, 165, 172).
   - Comparing Run 2 (filtered) against Run 3 (unfiltered):
     - SfM duration decreased from 377.9s to 345.1s (**32.8s saved / 8.7% faster**).
     - Reprojection error and track length remained virtually identical (0.553 px vs 0.546 px; 4.313 vs 4.258 track length).
     - Dropped frames prevented matching noise without degrading the reconstructed cluster.
3. **Scene-Cut & Trajectory Analysis on `bedroom_vid.mp4` (Items 4 & 5)**:
   - Ingest detected **5 abrupt scene cuts** at timestamps 24.0s, 24.5s, 66.5s, 87.0s, and 89.0s.
   - Because of non-overlapping scene cuts, COLMAP split the sequence into disjoint clusters; the primary continuous cluster registered 61-64 frames (~34-36%).
   - The consecutive-camera jump metric flagged **6 distinct jumps exceeding 5x the median distance** (reaching up to 13.43x median distance). These jump indices line up directly with the detected cut timestamps and the dropped frames.

---

## 4. Known Issues & Fixed Bugs

| Issue | Root Cause | Resolution | Commit Hash |
|---|---|---|---|
| UI stuck at "Queued 0%" | Multi-container SSE isolation: `worker-mock` published events to Redis, but `api` SSE listener was bound to a local in-memory queue. In addition, Nginx buffered streaming responses. | Updated `sse.py` to subscribe to Redis PubSub `job:{job_id}`, enabled `chunked_transfer_encoding on;` with `proxy_buffering off;` in Nginx, and added 2.5s fallback polling in `JobDetail.tsx`. | `1e1bbac` |
| Duplicate Nginx config | Both `docker/nginx.conf` and `frontend/nginx.conf` existed, creating maintenance ambiguity. | Removed `docker/nginx.conf`, retained canonical `frontend/nginx.conf`, updated `docs/SPEC.md`. | `1f6b9f7` |
| Missing LiDAR card in UI when flag disabled | `GET /api/capabilities` excluded `"lidar"` from `scan_types` when `ENABLE_LIDAR=false`, preventing frontend from displaying disabled state. | Updated `capabilities.py` to always include `"lidar"` in `scan_types` with `lidar_enabled` boolean; updated `ScanTypeCards.tsx` badge to "Beta, needs RGB-D capture". | `b9ee7ab` |
| Container pytest import error | `backend/Dockerfile` ran editable pip install before copying source files, leaving `app` module unlinked in fresh builds. | Configured `ENV PYTHONPATH=/app`, added post-copy `pip install -e ".[dev]"`, and added `pythonpath = ["."]` in `pyproject.toml`. | `0ccd635` |
| Untracked `.env` check | Ensure development secrets and local paths are not committed to git repository. | Verified `.env` in `.gitignore`; confirmed `git ls-files .env` is empty. | *Verified* |
| COLMAP mapper Ceres BA iteration stall | Exhaustive matching on dense scene graph caused Ceres solver to run unconstrained global BA iterations. | Investigated on RTX 4060 with COLMAP 3.9.1; removed artificial iteration caps; confirmed mapper converges cleanly in 54s without hanging; protected by 1800s `ToolRunner` timeout. | `59a4724` / `8ab91e5` |
| Multi-queue worker dispatch | GPU profile worker only listened to `scanforge_gpu`, leaving mock and test jobs stalled in `scanforge_mock`. | Enabled worker to listen to both `['scanforge_gpu', 'scanforge_mock']` in priority order. | `3d9ad27` |
| Mock worker RQ task import failure | `worker-mock` container crashed on task execution with `ValueError: Invalid attribute name: run_pipeline_task` due to missing `app.queue.__init__.py` and eager top-level imports in `registry.py` importing `cv2` in the slim mock container. | Created `app/queue/__init__.py` and changed `create_real_pipeline` in `registry.py` to lazily import real pipeline stages (`IngestStage`, `FrameExtractionStage`, `ColmapSfMStage`). | *Verified* |
| Directory artifact registration | Exporter stage outputs directories (`submodels/`) which failed file-based size check during artifact registration. | Updated `job_runner.py` to calculate directory tree size and skip sha256 for directory artifacts. | `e175f65` |
| Model analyzer output parsing | COLMAP 3.9.1 `model_analyzer` prefixes log lines with glog timestamp strings containing colons (e.g. `I1019 10:26:33.756991 924 model.cc:434]`). | Implemented robust regex extractors for `Mean track length`, `Mean observations per image`, and `Mean points per image`. | `fda7f98` |

---

## 5. Architectural Decisions

1. **Redis Pub/Sub for SSE Across Containers**:
   - Background workers run in separate containers (`worker-mock`, `worker-gpu`) from the web API (`api`).
   - All pipeline progress and log events are published to Redis channel `job:{job_id}`.
   - The FastAPI SSE endpoint (`/api/jobs/{id}/events`) subscribes to Redis asynchronously (`redis.asyncio`) and streams events live to clients.
2. **Reverse Proxy Buffering Disabled for SSE**:
   - `frontend/nginx.conf` proxies `/api/` to `http://api:8000/api/` with `proxy_buffering off;`, `proxy_cache off;`, and `chunked_transfer_encoding on;` to guarantee instantaneous event delivery.
3. **Pluggable Engine Interface**:
   - `SCANFORGE_ENGINE=mock` uses lightweight, fast procedural generators suitable for rapid testing and CI.
   - `SCANFORGE_ENGINE=real` activates external tool wrappers (`ColmapSfM`, `OpenMVSDense`, `NerfstudioSplatfacto`).
4. **Resilient Matcher Fallback & Uncapped Ceres BA**:
   - Sequential matching with overlap 25 is used first.
   - If registered frames are <90% (for $\le 200$ frames), exhaustive matching is automatically executed.
   - Uncapped Ceres BA runs with full convergence, protected by configurable timeouts (1800s default).
5. **Scale Calibration Pipeline Invariance**:
   - Calling `POST /api/jobs/{id}/calibrate` does not restart heavy upstream SfM or meshing stages. It only triggers `ScaleStage` and exporter stages, applying cumulative scaling factor `current_scale * (real_distance / measured_distance)`.
6. **COLMAP Multi-Version Portability & Hang Protection**:
   - `colmap_compat.py` provides dynamic CLI adaptation between COLMAP 3.9.x and 3.13.0+ based on real help fixtures.
   - SIFT extraction flags (`--SiftExtraction.use_gpu/num_threads` vs `--FeatureExtraction.use_gpu/num_threads`) and matching flags (`--SiftMatching.*` vs `--FeatureMatching.*`) are mapped dynamically.
   - Hang protection uses native `--Mapper.max_runtime_seconds` on 3.13+ and `ToolRunner(timeout=...)` on 3.9.x.
7. **Dynamic VRAM Tier Architecture**:
   - Automatically inspects `SCANFORGE_VRAM_GB` or active visible GPU memory from `nvidia-smi` minus a 0.5 GB safety buffer.
   - Dynamic tier matrix selects `colmap_max_image_size`, `openmvs_resolution_level`, and `low_memory_retry` parameters.

---

## 6. Environment Specifications

- **Remote Repository**: `https://github.com/Ommali8421/ScanForge.git` (Public, branch `main`).
- **Host Machine**: Windows 11 Laptop, 15 GB RAM, NVIDIA GeForce RTX 4060 Laptop GPU (8 GB VRAM, Ada arch, compute capability 8.9).
- **Runtime OS**: WSL2 (Ubuntu 22.04 LTS), 11 GB RAM limit, 16 GB swap.
- **Project Directory**: Native WSL filesystem (`/home/om_mali/scanforge`).
- **Containerization**: Docker Desktop with WSL2 backend + NVIDIA Container Toolkit (`nvidia-smi` accessible).
- **Environment Profiles**:
  - `mock`: default (`COMPOSE_PROFILES=mock`), runs `api`, `worker-mock`, `redis`, `frontend`.
  - `gpu`: activated via `make up-gpu` or `SCANFORGE_ENGINE=real COMPOSE_PROFILES=gpu docker compose up -d`, builds and runs heavy CUDA image with COLMAP, OpenMVS, and nerfstudio.

---

## 7. Next Steps (Immediate Steps for Milestone P2c)

*P2b completed and verified on real test video with RTX 4060 GPU. Awaiting user review before proceeding to Milestone P2c.*

1. **User Review on Milestone P2b**: Present reconstruction report, side-by-side comparison tables, 4-panel camera trajectory plots, and verified logs from both test video runs.
2. **Milestone P2c Planning (STOPPED UNTIL USER APPROVAL)**:
   - OpenMVS dense point cloud reconstruction (`DensifyPointCloud` at resolution level 2, with auto-retry at resolution level 3 on OOM).
   - Watertight tetrahedral Delaunay surface mesh reconstruction (`ReconstructMesh`).
   - Mesh post-processing: non-manifold edge cleanup, RANSAC plane detection and hole repair (Open3D), floor leveling to Y=0, planarity-aware decimation.
   - OpenMVS texture baking (`TextureMesh`) using undistorted cameras.
   - Exporters to canonical formats (GLB, OBJ, PLY, STL, XYZ, FBX, USDZ).

---

## 8. Session Resumption Guide

For any agent resuming work in this codebase:
1. **Read this file (`progress.md`) first** to understand the current milestone state and recent bug fixes.
2. Check `AGENTS.md` and `docs/SPEC.md` for conventions and strict architecture rules.
3. Verify that the current stack is healthy using `make smoke` and `docker compose ps`.
4. Always check git status (`git status`) to ensure the working tree is clean.
5. Update this file whenever you complete a milestone, fix a bug, or execute a new verification.

