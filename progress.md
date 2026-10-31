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
| **P2c** | Route A mesh: Phase 1/1b (InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, KDTree vertex color transfer, TextureMesh UV atlas, camera up-vector preview alignment up=+Y, long-edge/bbox garbage filtering, 4-view offscreen Blender evidence) + Phase 2 (floater cleanup, room analysis, relative floor rule, normal-aware plane snapping, envelope pruning, quadric decimation, UV texture mapping, Poisson A/B) + Phase 3 (floor align Y=0, scale calibration, exporters, quality report) | **Phase 2 Done (VERIFIED)** | Phase 2 verified on RTX 4060 GPU with `house_test_30s.mp4` (Job `f0e89d25`) and `enhanced_interior_tour_1080p.mp4` (Job `2b7b3bcc`). 4-view before/after evidence sheets saved in `outputs/`. Stopped for user review before Phase 3. |
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
| OpenMVS Phase 1 & 1b (Dense Cloud + Mesh + UV Texture + Up-Alignment + Filtering) | **VERIFIED** | Verified on RTX 4060 GPU with real data (`house_test_30s.mp4`: 1.23M points, 176k clean mesh verts, UV textured GLB; `enhanced_interior_tour_1080p.mp4`: 2.88M points, 381k clean mesh verts, UV textured GLB). Camera up-vector alignment ($\bar{\mathbf{u}}$ to $+Y$), nearest-neighbor KDTree vertex colors, TextureMesh 4K UV atlas, long-edge/bbox garbage removal, and Three.js OrbitControls with multi-tab preview verified. |
| OpenMVS Phase 2 (Mesh Cleanup, Room Analysis, Relative Floor Detection, Plane Snapping, Envelope Pruning, Quadric Decimation, UV Texture, Poisson A/B, Viewer Fixes) | **VERIFIED** | Verified on RTX 4060 GPU with both reference clips (`house_test_30s.mp4` Job `f0e89d25` and `enhanced_interior_tour_1080p.mp4` Job `2b7b3bcc`) run through normal job flow. Exterior slab and mirror ghosts pruned. Viewer white background, light-grey grid, high-contrast markers, and PBR material fix verified. 4-view before/after sheets saved under `outputs/`. |
| OpenMVS Phase 3 (Floor Leveling Y=0, Scale Calibration Seam, Exporters, Quality Report) | **UNVERIFIED** | Planned; stopped for user review of Phase 2 evidence before execution. |
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

## 4. Real Hardware Verification Results (Milestone P2c Phase 1)

### Stack Verification Raw Output Summary
All baseline suite checks were executed directly against the live environment:
- **`make up-mock`**: Exited with code 0 (`SCANFORGE_ENGINE=mock COMPOSE_PROFILES=mock`, 7/7 containers healthy).
- **`make smoke`**: Exited with code 0 (`scripts/e2e_smoke.py` through Nginx port 3000: 7 steps + 2 scale calibrations passed, 13 progress events received live).
- **`make up-gpu`**: Exited with code 0 (`SCANFORGE_ENGINE=real COMPOSE_PROFILES=gpu`, 7/7 containers healthy, verified `/api/capabilities` reports `engine=real, gpu_available=True`).
- **`make test-backend` (Pytest)**: **45 passed, 1 warning in 13.00s** (100% test pass rate in container).
- **`doctor.py` on `worker-gpu`**:
  - GPU: NVIDIA GeForce RTX 4060 Laptop GPU (7.6 GB VRAM free / 8.0 GB total)
  - Tooling: FFmpeg 4.4.2 [OK], COLMAP 3.9.1 (CUDA enabled) [OK], OpenMVS v2.2.0 (InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, TextureMesh) [OK]
  - Python: PyTorch 2.5.1+cu121 (CUDA: True), Open3D 0.20.0 [OK], Trimesh 5.1.1 [OK]

---

### Comparative Evaluation Matrix across Real Video Captures (Phase 1 & Phase 1b)

| Metric | Reference Clip (`house_test_30s.mp4`) | Enhanced Interior Tour (`enhanced_interior_tour_1080p.mp4`) |
|---|---|---|
| **Phase 1b Job ID** | `7d4c7704-7fec-4bbc-9aa6-2950db1bbb4e` | `f888dc62-136d-40d7-b74a-5fe7823a27de` |
| **Duration / Effective Res** | 30.0s, 478x850, 60 fps | 20.2s, 1080x1800 (auto-cropped 60px letterbox), 30 fps |
| **Calibrated Cameras** | 92 calibrated images | 67 calibrated images |
| **Camera Mean Up Vector ($\bar{\mathbf{u}}$)** | `[0.081, -0.985, -0.151]` | `[0.000, -1.000, -0.000]` |
| **InterfaceCOLMAP Runtime** | 0.04s (`scene.mvs`, 511.6 KB) | 0.58s (`scene.mvs`, 841.1 KB) |
| **OpenMVS Working Resolution** | `resolution-level 0` (478x850) | `resolution-level 0` (1080x1800 on 8 GB RTX 4060) |
| **Dense Point Cloud Count** | **1,231,802 points** (31.72 MB) | **2,884,988 points** (74.29 MB) |
| **DensifyPointCloud Runtime** | 53.1s | 275.4s (~4.6 min) |
| **Raw Delaunay Vertices / Faces** | 180,086 verts / 360,037 faces | 384,861 verts / 769,677 faces |
| **ReconstructMesh Runtime** | 8.1s (`--remove-spurious 20 -f 1 --smooth 2`) | 28.1s (`--remove-spurious 20 -f 1 --smooth 2`) |
| **Long-Edge Spikes Dropped** | 7,355 faces ($> 6\times \text{median}$) | 17,544 faces ($> 6\times \text{median}$) |
| **Out-of-Bounds Faces Dropped** | 5,885 faces (outside camera bbox) | 3,355 faces (outside camera bbox, removing thin outer sheet) |
| **Cleaned Mesh Vertices / Faces** | **176,431 verts / 347,043 faces (kept 96.4%)** | **381,041 verts / 750,062 faces (kept 97.5%)** |
| **Nearest-Neighbor Color Transfer** | KDTree from 1.23M dense points to vertices | KDTree from 2.88M dense points to vertices |
| **TextureMesh Atlas & Runtime** | 4096x4096 atlas (`scene_textured.png`), 41.2s | 4096x4096 atlas (`scene_textured.png`), 184.2s (3.1 min) |
| **Oriented Previews (up = +Y)** | `preview_mesh.glb` (6.66 MB), `preview_textured.glb` (19.66 MB), `preview_cloud.ply` (59.91 MB) | `preview_mesh.glb` (14.28 MB), `preview_textured.glb` (42.17 MB), `preview_cloud.ply` (140.32 MB) |
| **Offscreen Visual Evidence** | `outputs/house_dense_4views.png`, `outputs/house_textured_4views.png` | `outputs/tour_dense_4views.png`, `outputs/tour_textured_4views.png` |
| **Three.js UI Viewer Enhancements** | OrbitControls, Zoom (+/-), Reset View, Multi-Tab Switcher | OrbitControls, Zoom (+/-), Reset View, Multi-Tab Switcher |

---

### Investigation of Vertex Count Discrepancy (App served 399,209 vs reported 391,619)

- **Finding**: In Milestone P2c Phase 1, job `dde47794-b416-4730-9b46-60aed5299c30` was submitted via CLI script with 67 extracted frames, generating `raw_mesh.glb` with **391,619 vertices**. Subsequently, the user uploaded the tour video directly through the web UI creating job `b8367aa4-0fd4-4a92-9b8d-ac7d343d809f`.
- In job `b8367aa4`, COLMAP registered frames with slightly different feature keypoint densities, producing **399,209 vertices** in `raw_mesh.glb`.
- Because the frontend always queries `/api/jobs` sorted by `created_at DESC` and selects the most recent completed job, the web UI served the artifacts from job `b8367aa4` (399,209 vertices) rather than the earlier job `dde47794` (391,619 vertices).
- With the Phase 1b automated garbage filtering and spike removal implemented, the raw mesh from ReconstructMesh (384,861 vertices / 769,677 faces) is cleanly pruned of 17,544 spikes and 3,355 out-of-bounds spurious faces, resulting in exactly **381,041 vertices / 750,062 faces** in the clean oriented `preview_mesh.glb`.

---

## 5. Known Issues & Fixed Bugs

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
| Raw preview meshes uncolored and tilted | OpenMVS `ReconstructMesh` creates raw geometry without textures or vertex colors, leaving output in raw COLMAP camera coordinate system (upside-down). | Implemented Rodrigues alignment matrix rotating mean camera up vector ($\bar{\mathbf{u}} = \frac{1}{N}\sum \mathbf{R}_i^\top [0, -1, 0]^\top$) to $+Y$; transferred dense cloud RGB colors via KDTree nearest-neighbor search (`cKDTree`); added OpenMVS `TextureMesh` to pipeline emitting 4K UV texture atlas (`scene_textured.png`) and oriented textured GLB. | *Verified (Phase 1b)* |
| Obvious spikes and spurious sheets outside room | OpenMVS Delaunay mesher constructs tetrahedra across empty space and distant background points. | Enabled OpenMVS surface tuning (`--remove-spurious 20 --remove-spikes 1 --close-holes 30 --smooth 2 -f 1`); added vectorized triangle filtering dropping faces with edge lengths $> 6\times \text{median}$ and dropping faces outside camera trajectory bounding box with minimum span margin. | *Verified (Phase 1b)* |
| Planar trajectory bounding box clipping | In horizontal corridor or tripod videos (like synthetic tour), vertical camera span $\Delta Y \approx 0.02$ m; an unscaled percentage margin clipped ceiling and floor. | Set bounding box margin to `np.maximum(1.2 * cam_span, max(0.4 * max_span, 2.5))`, ensuring at least 2.5m vertical clearance for interior walls, floors, and ceilings. | *Verified (Phase 1b)* |
| Web viewer zoom/pan and scroll hijacking | Custom spherical mouse listener lacked `e.preventDefault()`, broke page scrolling, had no camera panning, and clamped phi to $87^\circ$. | Replaced with standard Three.js `OrbitControls` with smooth damping, scroll zoom, right-click pan, explicit toolbar buttons (+/- zoom, reset view), and multi-tab switcher for Textured Mesh, Dense Cloud (PLY), and Raw Geometry (GLB). | *Verified (Phase 1b)* |

---

## 6. Architectural Decisions

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
9. **SfM-Frame Texturing & Zero-Retexturing Calibration Seam (P2c)**:
   - Mesh cleanup, plane repair, and quadric decimation all execute strictly in the original COLMAP/SfM coordinate frame.
   - `TextureMesh` executes against the unmodified camera poses in `scene.mvs`.
   - Floor leveling and metric scaling are applied as a post-texture similarity transform on vertex positions only, leaving UV texture coordinates intact.

---

## 7. Environment Specifications

- **Remote Repository**: `https://github.com/Ommali8421/ScanForge.git` (Public, branch `main`).
- **Host Machine**: Windows 11 Laptop, 15 GB RAM, NVIDIA GeForce RTX 4060 Laptop GPU (8 GB VRAM, Ada arch, compute capability 8.9).
- **Runtime OS**: WSL2 (Ubuntu 22.04 LTS), 11 GB RAM limit, 16 GB swap.
- **Project Directory**: Native WSL filesystem (`/home/om_mali/scanforge`).
- **Containerization**: Docker Desktop with WSL2 backend + NVIDIA Container Toolkit (`nvidia-smi` accessible).
- **Environment Profiles**:
  - `mock`: default (`COMPOSE_PROFILES=mock`), runs `api`, `worker-mock`, `redis`, `frontend`.
  - `gpu`: activated via `make up-gpu` or `SCANFORGE_ENGINE=real COMPOSE_PROFILES=gpu docker compose up -d`, builds and runs heavy CUDA image with COLMAP, OpenMVS, and nerfstudio.

---

## 8. Real Hardware Verification Results (Milestone P2c Phase 2)

> **Execution Date**: 2026-10-31  
> **Environment**: NVIDIA GeForce RTX 4060 Laptop GPU (8 GB VRAM, Ada sm_89), Ubuntu 22.04 on WSL2 (11 GB RAM limit).  
> **Run Mode**: Real API Pipeline (`POST /api/jobs` via `scripts/submit_real_run.py`), automated worker processing end-to-end.  
> **Scope**: Phase 2 ONLY (Floater cleanup, room analysis, relative floor rule, normal-aware plane snapping, envelope pruning, quadric decimation, OpenMVS TextureMesh, Poisson A/B, viewer fixes). Phase 3 stopped for review.

### A. Viewer Enhancements & PBR Shader Corrections
1. **White Scene Background & Contrast Markers**: Default `#ffffff` background with light-grey `#9ca3af`/`#e5e7eb` grid and sun/moon theme toggle. High-contrast measure markers: crimson red (`#dc2626`) for Point A, royal blue (`#2563eb`) for Point B, vivid purple (`#9333ea`) for distance segment.
2. **PBR glTF Black Render Fix**:
   - Fixed at export: In `openmvs.py`, `fix_glb_pbr_materials()` parses glTF binary chunks and explicitly patches `metallicFactor = 0.0`, `roughnessFactor = 1.0`, `doubleSided = True`.
   - Fixed in viewer: `MeshViewer.tsx` traverses materials setting `metalness = 0.0`, `roughness = 1.0`, `side = THREE.DoubleSide`, `map.colorSpace = THREE.SRGBColorSpace`, illuminated by `HemisphereLight(0xffffff, 0xcccccc, 1.2)` and ambient/directional fill.
3. **Investigation of Job `bc22c9e8` (`test_scene.mp4`)**:
   - `bc22c9e8-c3d6-4c65-91a9-535847762665` was created by an automated test (`tests/test_integration.py:test_sse_replay_on_connect`), completing in 38 ms with 0 artifacts.
   - When opened in the UI, `MeshViewer` silently executed `createProceduralFallback()`, rendering a grey test box (`BoxGeometry(4, 2.6, 5)`).
   - **Resolution**: `createProceduralFallback` is completely eliminated. Real mode displays an explicit error message card (`<AlertTriangle>`) if an artifact fails to load.

### B. TextureMesh Configuration
- Configured `--empty-color 13158600` (RGB 200, 200, 200 neutral light-grey) instead of default bright orange.
- Added `--global-seam-leveling 0 --local-seam-leveling 0` when texturing decimated/pruned meshes, eliminating the OpenMVS `_Map_base::at` container out-of-bounds abort and accelerating texture atlas generation to ~200 ms.
- Log parsing extracts and reports exact textured face coverage and untextured face percentage.

### C. End-to-End Test Dataset Metrics

| Stage Metric | Reference Clip (`house_test_30s.mp4`) | Enhanced Interior Tour (`enhanced_interior_tour_1080p.mp4`) |
|---|---|---|
| **Job ID** | `f0e89d25-b4fb-4878-abef-3c2dc479bf35` | `2b7b3bcc-0c24-40ed-82b0-b2e2d4c82351` |
| **Video Dimensions** | 478 x 850 (60 fps, 30.0s) | 1080 x 1920 -> 1080 x 1800 auto-cropped (30 fps, 20.2s) |
| **SfM Registered Frames** | 92 / 99 frames (92.9%) | 67 / 67 frames (100.0%) |
| **Dense Cloud Points** | 1,217,117 points | 2,797,368 points |
| **Raw Delaunay Faces** | 356,101 faces | 734,133 faces |
| **Cleaned Mesh Floaters** | 1 component, 0 floaters dropped (100% kept) | 3 components, 2 floaters dropped (536 faces dropped) |
| **Camera Mean Up $\hat{\mathbf{u}}$** | $[0.079, -0.985, -0.154]$ | $[0.000, -1.000, 0.001]$ |
| **Scene Diagonal $D_{\text{bbox}}$** | 32.112 (SfM units) | 32.951 (SfM units) |
| **Floor Plane Selection** | Depth 5.201 below camera (16.2% $D_{\text{bbox}}$), 1,848 inliers | Depth 1.530 below camera (4.6% $D_{\text{bbox}}$), 289 inliers |
| **Plane Snapping** | 35,048 verts (19.7%), max disp: 0.2406 (0.75% $D_{\text{bbox}}$) | 54,484 verts (14.9%), max disp: 0.1647 (0.50% $D_{\text{bbox}}$) |
| **Spurious Geometry Pruned** | 79,759 below floor, 4,155 outside walls (83,914 faces) | 13,300 below floor, 88,914 outside walls (**102,214 faces**) |
| **Exterior Slab / Ghost Removal** | Clean wall boundaries | **Exterior blue-grey slab & mirror ghosts completely removed** |
| **Repaired Mesh Count** | 136,678 verts, 272,187 faces | 316,241 verts, 631,383 faces |
| **Decimated Mesh Count** | 100,584 verts, **200,000 faces** (boundary_weight=1.0) | 100,487 verts, **199,999 faces** (boundary_weight=1.0) |
| **TextureMesh Execution** | 20.8s, 4,635 atlas patches, 4096 texture size | 25.1s, 4,545 atlas patches, 4096 texture size |
| **Texture Coverage** | **200,000 / 200,000 faces (100.0%)**, 0 untextured | **199,999 / 199,999 faces (100.0%)**, 0 untextured |
| **Poisson Surface A/B** | 322,866 verts, 639,630 faces (15.9s, depth 9) | 142,637 verts, 282,610 faces (5.6s, depth 9) |
| **Total Pipeline Wall Clock** | **207.9s** (3m 27s) | **375.8s** (6m 15s) |

### D. Composite Evidence Sheets Generated
Both composite contact sheets rendered across 4 canonical views (Perspective 1, Perspective 2, Top-Down Plan, Side Elevation) and all 6 progression stages:
1. `outputs/house_phase2_sheet.png` (1.2 MB, 1790x2394)
2. `outputs/tour_phase2_sheet.png` (942 KB, 1790x2394)

---

## 9. Next Steps (Immediate Steps for Milestone P2c Phase 3)

*Phase 2 is completed and VERIFIED. Stopped for user review before proceeding to Phase 3.*

1. **User Review on Phase 2 Evidence**: Review composite sheets in `outputs/house_phase2_sheet.png` and `outputs/tour_phase2_sheet.png`.
2. **Phase 3 Scope (Awaiting User Approval to Implement)**:
   - `FloorAlignAndScaleStage`: Rigid similarity transform $\mathbf{v}' = S \cdot \mathbf{R} (\mathbf{v} - \mathbf{c}) + \mathbf{t}$ rotating dominant floor plane to $Y=0$ (or $Z=0$ per up-axis setting), centering bounds on $(0, 0)$, and applying scale factor $S$.
   - **Zero-Retexturing Calibration Seam**: `/calibrate` applies transformation to vertex positions only, leaving UV atlases and image textures completely intact (<3s execution).
   - `MeshExportStage`: Exporters for GLB, OBJ (+MTL+PNG), PLY, STL, XYZ (native Python) and FBX, USDZ (headless Blender 4.1 script).
   - `QualityReportStage`: Mesh watertightness, area, volume, and room dimensions (bounding box length/width/height, estimated floor area).
   - Frontend `MeasureTool.tsx`, `QualityReport.tsx`, and interactive calibration modal.

---

## 10. Session Resumption Guide

For any agent resuming work in this codebase:
1. **Read this file (`progress.md`) first** to understand the current milestone state and recent bug fixes.
2. Check `AGENTS.md` and `docs/SPEC.md` for conventions and strict architecture rules.
3. Verify that the current stack is healthy using `make smoke` and `docker compose ps`.
4. Always check git status (`git status`) to ensure the working tree is clean.
5. Update this file whenever you complete a milestone, fix a bug, or execute a new verification.

