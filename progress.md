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

### Reference Result (Milestone P2b Target)
> **P2b Reference Result**: `house_test_30s.mp4` (Job `bcaa88f4-2ffa-4e56-998b-76c6f15dbf7d`):
> - **Registered Frames**: 92 / 99 (92.9%)
> - **Reprojection Error**: 0.662 px
> - **Sparse 3D Points**: 8,214 points
> - **Trajectory Jumps**: 0 flagged jumps (max consecutive step ratio 2.12x)
> - **Mapper Runtime**: 54.0s (Timeout: 1800s, did NOT fire)

---

### Comparative Evaluation Matrix across Videos, Presets & Sampling Frequencies

| Metric | Reference Clip (`house_test_30s.mp4`) | Bedroom Baseline (`bedroom_vid.mp4`) — Partial Model (0.30 Threshold) | Bedroom Filtered (Run 2) | Bedroom Unfiltered (Run 3) | Bedroom 4 fps Experiment (361 frames, overlap 20) | Bedroom 6 fps Experiment (542 frames, overlap 20) |
|---|---|---|---|---|---|---|
| **Job ID** | `bcaa88f4...` | `0d9060a5...` | `4179ece6...` | `65a6fc3e...` | `bac945fd...` | `5a1eeaa9...` |
| **Duration / Res** | 30.0s, 478x850, 60 fps | 90.5s, 478x850, 30 fps | 90.5s, 478x850, 30 fps | 90.5s, 478x850, 30 fps | 90.5s, 478x850, 30 fps | 90.5s, 478x850, 30 fps |
| **Sampling Mode** | Adaptive (~3.3 fps) | Adaptive (2.0 fps) | Adaptive (2.0 fps) | Adaptive (2.0 fps) | Uniform 4.0 fps | Uniform 6.0 fps |
| **Frames Extracted**| 99 | 180 | 180 | 180 | 361 | 542 |
| **Low-Texture Drop**| 0 | 10 | 11 | 0 (Disabled) | 28 | 38 |
| **Active Match Frames**| 99 | 170 | 169 | 180 | 333 | 504 |
| **Cuts Validated** | 0 | 0 of 5 survived (all 5 rejected as continuous pans) | 5 candidates | 5 candidates | 0 confirmed | 0 confirmed |
| **Sequential Reg.** | 68 / 99 | 12 / 170 | 12 / 169 | 12 / 180 | 45 / 333 (145 across 6 submodels) | 70 / 504 (312 across 10 submodels) |
| **Exhaustive Reg.** | 92 / 99 | 72 / 170 | 61 / 169 | 64 / 180 | N/A (Sequential only) | N/A (Sequential only) |
| **Final Registered**| **92 / 99 (92.9%)** | **72 / 180 (40.0%)** | **61 / 180 (33.9%)** | **64 / 180 (35.6%)** | **45 / 361 (12.5%)** | **70 / 542 (12.9%)** |
| **Sparse 3D Points**| 8,214 | 8,872 | 7,444 | 8,431 | 5,618 | 14,649 |
| **Reprojection Err** | 0.662 px | 0.542 px | 0.553 px | 0.546 px | 0.601 px | 0.585 px |
| **Sub-models Found** | 2 (92, 2) | 1 (72) | 2 (61, 2) | 3 (64, 2, 2) | 6 (45, 27, 22, 22, 18, 11) | 10 (70, 50, 39, 34, 34, 24, 17, 17, 16, 11) |
| **Trajectory Jumps** | 0 flagged | **0 flagged (7 gaps tracked)** | 6 flagged across gaps | 6 flagged across gaps | 0 flagged (consecutive checked) | 0 flagged (consecutive checked) |
| **Status Badge** | Completed | Partial Model (40.0%) | Failed (<60%) | Failed (<60%) | Failed (<30%) | Partial Model (12.9%) |
| **Mapper Runtime** | 54.0s | 127.9s | 150.8s | 176.7s | 260.2s | 507.2s |
| **Total SfM Duration**| 159.6s | 266.7s | 345.1s | 377.9s | 315.4s | 583.3s |

---

### Detailed Findings & Engineering Rationale

1. **Scene Cut Dual-Validation & Rejection of False Positives**:
   - The 5 candidate cuts detected on `bedroom_vid.mp4` (at timestamps ~24.0s, 24.5s, 66.5s, 87.0s, 89.0s) were investigated.
   - Root cause: During a rapid camera pan past a dark doorway (t=23.5s to 25.0s), the frame brightness dropped abruptly (<30 mean pixel intensity), causing the HSV histogram correlation to drop sharply (`corr = 0.003` and `0.189`), while darkness and motion blur temporarily starved FAST/ORB features.
   - Refined detector logic: Added dual validation requiring significant histogram change (`corr < 0.15`), verified RANSAC inlier collapse (`inliers < 10`), adequate illumination (`mean_brightness >= 35`), and sufficient texture (`keypoints >= 20`).
   - Result: **0 of the 5 false positive cuts survived**. All 5 were properly classified as continuous motion past dark zones, preventing unnecessary sequence splitting. Before/after and comparison composite images are automatically saved to `cuts/` for visual verification on the job page.

2. **Gap Separation vs. Camera Trajectory Jumps**:
   - The previously reported "13.4x jump between frames 46 and 58" was an artifact of computing distances across an unmodelled gap of 11 unregistered frames.
   - Fixed motion jump detector: Now strictly tests consecutive registered frames (`frame_b == frame_a + 1`). Unregistered stretches are tracked and reported separately as `registration_gaps` (e.g., "Registration gap: frames 22..47 missing (26 frames)").
   - Borderline jumps (4x to 5x median step) are categorized separately as fast camera pans rather than discontinuities. Trajectory plot axes are explicitly labeled in "SfM units (arbitrary scale, not metres)".

3. **Low-Texture Filtering Accuracy**:
   - Accurate reporting: Filtering low-texture frames on `bedroom_vid.mp4` resulted in a slight loss of registered frames (61 vs 64) and points (7,444 vs 8,431) while reducing SfM runtime from 377.9s to 345.1s. It is documented accurately as a performance-for-coverage tradeoff rather than "no quality loss".

4. **Configurable Registration Threshold (`min_registration_ratio`)**:
   - Added `min_registration_ratio` (default 0.60) in backend options, API, and frontend NewScan slider (10% to 100%).
   - Partial models (`min_registration_ratio <= ratio < 0.60`) are accepted and highlighted with an amber "Partial Model" badge in the UI and `sfm_report.json`.
   - Re-running `bedroom_vid.mp4` with `min_registration_ratio=0.30` yielded an accepted 72-frame partial model with 8,872 points, 0.542 px error, 0 jumps, and downloadable diagnostics.

5. **Sampling Density Experiment (Uniform 4 fps vs 6 fps)**:
   - Evaluated 4 fps (361 frames) and 6 fps (542 frames) with sequential overlap 20 on `bedroom_vid.mp4`.
   - Increasing sampling density significantly improved sequential matching tracking: primary submodel registration increased from **12 frames (at 2 fps)** to **45 frames (at 4 fps, 3.75x)** and **70 frames (at 6 fps, 5.8x)**. Total registered frames across all submodels reached 145 frames (4 fps) and 312 frames (6 fps).
   - However, sequential matching fragmented the walkthrough into **6 submodels (at 4 fps)** and **10 submodels (at 6 fps)** because rapid rotation sweeps past blank doors broke visual tracking without cross-loop matching.
   - **Conclusion**: Sampling rate is a significant factor in consecutive frame tracking, but **not the sole root cause** of walkthrough fragmentation. Per user directive, the `low_texture_indoor` preset, adaptive sampler, and pre-flight check are deferred until after Milestone P2c.

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

