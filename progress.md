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
| Nginx Reverse Proxy (Port 3000) | **VERIFIED** | Reverse-proxies UI (`/`) and API (`/api/`) with chunked transfer and disabled buffering. Configured with dynamic Docker DNS resolver (`127.0.0.11 valid=10s`) and dynamic upstream variable binding to prevent 502 Bad Gateway / Connection Refused on container recreations (`fa04d9e`). Tested with 43 MB video upload (`enhanced_interior_tour_1080p.mp4`). |
| Artifact Generation & Download | **VERIFIED** | Validated download of generated `.ply`, `.png`, and `.json` outputs, including directory artifacts |
| Scale Calibration Math | **VERIFIED** | Two consecutive calibrations tested, verifying cumulative scale factor `1.5 * 2.0 = 3.0` |
| Backend Pytest Suite | **VERIFIED** | 45/45 tests passing in container (`test_sfm_diagnostic.py`, `test_portability.py`, `test_colmap_compat.py`, `test_ingest_crop_and_cuts.py`, `test_cancel_sfm.py`, `test_sfm_failure.py`, etc.) |
| Dynamic VRAM Detection & Tiers | **VERIFIED** | Tested `SCANFORGE_VRAM_GB` override vs `nvidia-smi` total memory minus 0.5 GB safety margin; logs tier selection and source; preserves 2000 px COLMAP cap on 8 GB tier (`f1ec5ac`) |
| Ingest Auto-Crop & Multi-Criteria Cut Filter | **VERIFIED** | Auto-detected letterbox bars (`cropdetect=24:2:0`); cropped 60px top/bottom bars on `enhanced_interior_tour_1080p.mp4` to 1080x1800 (`65a594e`). Multi-criteria cut validation rejected false cuts on textureless walls and exposure shifts while preserving real sequence cuts. |
| Adaptive Keyframe Extraction | **VERIFIED** | Evaluated frames with Laplacian sharpness scoring, Farneback optical flow, and homography rotation check |
| Low-Texture SIFT Filtering | **VERIFIED** | Automatic dropping of feature-starved frames before matching (`min_sift_keypoints=100`); dropped 11 featureless wall/ceiling frames in `bedroom_vid.mp4`, logged in `sfm_report.json` |
| GPU COLMAP SfM (RTX 4060) | **VERIFIED** | Full GPU SIFT extraction, sequential + auto exhaustive matching, unconstrained Ceres BA. Tested across reference clip (`house_test_30s.mp4`), indoor bedroom clip, and enhanced interior tour (`enhanced_interior_tour_1080p.mp4` with SIMPLE_RADIAL and OPENCV). |
| 4-Panel Diagnostic Camera Trajectory | **VERIFIED** | `camera_path.png` generated with: (1) 3D camera trajectory colored by frame index, broken at gaps/jumps, equal axes, high-contrast points, (2) Side view (Z-Y / X-Z), (3) Consecutive distance ratio to median with jumps >5x flagged, (4) Per-frame SIFT keypoints, consecutive verified matches, and rotation-vs-translation metric |
| COLMAP Multi-Version Adaptation | **VERIFIED** | Verified rename mapping against 3.9.1 and 3.13.0 help fixtures; hang protection via timeout without Ceres iteration caps; FAISS loop detection fallback (`59a4724`) |
| Native Docker Client Operation | **VERIFIED** | Executed in sequence via native Docker client (`/usr/bin/docker`): `make up-mock` (code 0), `make smoke` (code 0), `make up-gpu` (code 0, `gpu_available=True`). |
| OpenMVS Route A Mesh Pipeline | **UNVERIFIED** | Milestone P2c plan written; execution stopped for user approval |
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

### Comparative Evaluation Matrix across Real Video Captures

| Metric | Reference Clip (`house_test_30s.mp4`) | Enhanced Tour — `SIMPLE_RADIAL` (`dde47794...`) | Enhanced Tour — `OPENCV` (`a31916f3...`) | Bedroom Baseline (`bedroom_vid.mp4`) | Bedroom 4 fps Exp. (`bac945fd...`) | Bedroom 6 fps Exp. (`5a1eeaa9...`) |
|---|---|---|---|---|---|---|
| **Duration / Raw Dim** | 30.0s, 478x850, 60 fps | 20.2s, 1080x1920 (portrait), 30 fps | 20.2s, 1080x1920 (portrait), 30 fps | 90.5s, 478x850, 30 fps | 90.5s, 478x850, 30 fps | 90.5s, 478x850, 30 fps |
| **Auto-Crop Applied** | None (no bars) | `1080x1800:0:60` (60px top/bottom) | `1080x1800:0:60` (60px top/bottom) | None (no bars) | None (no bars) | None (no bars) |
| **Camera Model** | `SIMPLE_RADIAL` | `SIMPLE_RADIAL` | `OPENCV` | `SIMPLE_RADIAL` | `SIMPLE_RADIAL` | `SIMPLE_RADIAL` |
| **Frames Extracted** | 99 | 67 | 67 | 180 | 361 | 542 |
| **Active Match Frames** | 99 | 67 | 67 | 170 | 333 | 504 |
| **Largest Single Model** | **92 / 99 (92.9%)** | **67 / 67 (100.0%)** | **67 / 67 (100.0%)** | **72 / 170 (42.4%)** | **45 / 333 (13.5%)** | **70 / 504 (13.9%)** |
| **Best Result (Exhaustive)** | 92 / 99 (92.9%) | 67 / 67 (100.0%) | 67 / 67 (100.0%) | 72 / 180 (40.0% total) | N/A (Sequential only) | N/A (Sequential only) |
| **Sparse 3D Points** | 8,214 | 13,129 | 13,631 | 8,872 | 5,618 | 14,649 |
| **Reprojection Error** | 0.662 px | 0.627 px | 0.607 px | 0.542 px | 0.601 px | 0.585 px |
| **Sub-models Found** | 2 (92, 2) | 1 (67) | 1 (67, 2 discarded) | 1 (72) | 6 (45, 27, 22, 22, 18, 11) | 10 (70, 50, 39, 34, 34, 24, 17, 17, 16, 11) |
| **Trajectory Jumps** | 0 flagged | 0 flagged (1 borderline) | 0 flagged (1 borderline) | 0 flagged (7 gaps tracked) | 0 flagged | 0 flagged |
| **Peak VRAM / RAM** | 415 MB / ~400 MB | 1,151 MB / 652.8 MB | 1,175 MB / 462.2 MB | 527 MB / ~420 MB | 415 MB / ~430 MB | 527 MB / ~450 MB |
| **Mapper Runtime** | 54.0s | 64.9s | 117.6s | 127.9s | 260.2s | 507.2s |
| **Total SfM Duration** | 159.6s | 190.3s | 270.6s | 266.7s | 315.4s | 583.3s |

---

### Detailed Findings & Engineering Rationale

1. **Scene Cut Investigation & Frame Brightness Verification (`bedroom_vid.mp4`)**:
   - The user noted frames at 23.5s, 24.0s, 24.5s, and 25.0s of `bedroom_vid.mp4` are bright (white wall, corner, bed, curtain), showing that the earlier "mean brightness < 30" explanation was contradictory.
   - **Empirical Brightness Measurement (Original vs Normalized)**:
     - $t=23.0\text{s}$ (f681): ORIGINAL mean = 107.12 | NORMALIZED mean = 107.14 ($\Delta = +0.02$)
     - $t=23.5\text{s}$ (f695): ORIGINAL mean = 156.93 | NORMALIZED mean = 161.21 ($\Delta = +4.28$)
     - $t=24.0\text{s}$ (f710): ORIGINAL mean = 162.98 | NORMALIZED mean = 162.40 ($\Delta = -0.58$)
     - $t=24.5\text{s}$ (f725): ORIGINAL mean = 149.84 | NORMALIZED mean = 150.34 ($\Delta = +0.50$)
     - $t=25.0\text{s}$ (f740): ORIGINAL mean = 139.34 | NORMALIZED mean = 137.52 ($\Delta = -1.81$)
   - **Finding**: The normalized copy is **not darker** (deviations are within $\pm 0.5 - 4$ pixel values due to standard YUV-RGB color conversion). There is **no color range or tone-mapping ingest bug**.
   - **True Root Cause of False Cut**: Frame 705 (mean brightness 161.21) transitions to Frame 720 (mean brightness 162.40), where the lens pans directly across a completely smooth, uniform, textureless white wall section. In Frame 720, ORB keypoints dropped to **0** and Laplacian blur variance dropped to **0.5**. Because zero features could be extracted from the uniform white surface, RANSAC matching produced zero inliers. The old detector mistakenly interpreted the zero inliers as a shot cut.
   - **Refined Cut Detector Rule**: Completely eliminated the arbitrary `brightness >= 35` threshold. Cut confirmation now strictly requires:
     1. Histogram divergence ($\text{corr} < 0.15$), **AND**
     2. Feature-match collapse ($\text{inliers} < 8$), **AND**
     3. Not explained by motion blur ($\text{blur\_variance} \ge 25.0$), **AND**
     4. Not explained by blank/textureless frames ($\min(\text{kp}_a, \text{kp}_b) \ge 40$), **AND**
     5. Not explained by abrupt exposure swing ($|\text{mean}_a - \text{mean}_b| \le 40.0$).
   - On the new `enhanced_interior_tour_1080p.mp4` clip, 0 false cuts were detected.

2. **Accurate Reporting of Sampling Experiment**:
   - In photogrammetry, disconnected sub-models represent mutually disjoint coordinate systems and cannot be treated as a single reconstructed scene. Summing registered frame counts across disconnected sub-models is invalid.
   - **Corrected Single Model Ratios**:
     - 2.0 fps sequential: **12 / 170 (7.1%)** registered in largest single model (baseline).
     - 4.0 fps sequential: **45 / 333 (13.5%)** registered in largest single model (split across 6 submodels).
     - 6.0 fps sequential: **70 / 504 (13.9%)** registered in largest single model (split across 10 submodels).
     - Best result remains 2.0 fps with exhaustive cross-matching: **72 / 180 (40.0%)** in a single connected model.
   - Removed any "+483%" wording or claims of reconstruction gain from sub-model summation.

3. **Evaluation of `enhanced_interior_tour_1080p.mp4`**:
   - Letterbox detection: `ffmpeg cropdetect=24:2:0` detected 60px black bars top and bottom. Auto-cropped from $1080\times 1920$ to $1080\times 1800$ (`crop=1080:1800:0:60`), removing black border artifacts during SIFT extraction.
   - `SIMPLE_RADIAL`: Reached 67/67 (100%) registration in 1 sub-model with 13,129 points and 0.627 px reprojection error. Mapper runtime: 64.9s.
   - `OPENCV`: Reached 67/67 (100%) registration in 1 sub-model with 13,631 points (+502 points) and 0.607 px reprojection error. Mapper runtime: 117.6s.
   - Both runs demonstrated excellent convergence, peak VRAM well within 8 GB budget (~1.15 - 1.18 GB), and clean 4-panel camera trajectory plots. The clip is kept outside the git repository.

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
8. **Dynamic Docker DNS Resolution in Reverse Proxy**:
   - Standard Nginx caches upstream container IPs once at startup, which triggers `502 Bad Gateway` when backend containers are recreated by Docker Compose.
   - Configured Docker's internal DNS resolver (`127.0.0.11 valid=10s`) and dynamic proxying via variable (`set $api_backend http://api:8000; proxy_pass $api_backend;`) to ensure transparent IP re-resolution without UI upload errors.

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

