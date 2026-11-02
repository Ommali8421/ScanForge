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
| **P2c** | Route A mesh: Phase 1/1b (InterfaceCOLMAP, DensifyPointCloud, ReconstructMesh, KDTree vertex color transfer, TextureMesh UV atlas, camera up-vector preview alignment up=+Y, long-edge/bbox garbage filtering, 4-view offscreen Blender evidence) + Phase 2 (floater cleanup, room analysis, relative floor rule, normal-aware plane snapping with smoothstep Hermite falloff, conservative envelope pruning, quadric decimation, UV texture mapping, Poisson A/B) + Phase 2 Verification & Review Resolution + Phase 3 (floor align Y=0 with normal-sign & antiparallel singularity guards, non-compounding scale calibration seam <0.1s, 8 deliverable exporters, quality report, Blender 4.1 round-trip verification) | **Milestone P2c FULLY COMPLETE & VERIFIED** | All 4 phases (1, 1b, 2, 3) executed and verified on RTX 4060 GPU end-to-end via `POST /api/jobs` on both `house_test_30s.mp4` (`a78fc585-4120-48b5-8512-17d2b6afa8f2`) and `enhanced_interior_tour_1080p.mp4` (`4945096f-639c-40bb-97bc-2ac258e8b9d6`). Floor aligned flush to Y=0 with median inliers, yaw-rotated to cardinal walls, centered, and physically calibrated. Sequential `/calibrate` executes in 0.067s - 0.130s (<3.0s spec) with bitwise identical UVs and texture atlas. All 8 deliverable assets generated (GLB, GLTF, OBJ ZIP, PLY, STL, XYZ, FBX, USDZ). Cross-container Blender detection verified. 57/57 tests passing. Blender 4.1 round-trip proof sheet saved to `outputs/phase3_roundtrip_proof.png`. |
| **P2-Ext** | Long-Video Optimization & Deliverable Calibration Sync (Two-pass zero-RAM frame extraction, 600s duration limit, adaptive diminishing-returns keyframe curve, offline strided anchor-frame loop closure for N>=150 via matches_importer, OpenMVS joint megapixel resolution planning, auto OOM/SIGKILL fallback escalation, calibrated multi-format deliverable sync for OBJ ZIP, PLY, STL, XYZ, FBX, USDZ) | **Done & Verified** | Implemented per user amendments. 62/62 tests passing (`4e3b23d`). Verified on Tanks & Temples `Meetingroom` (293/293 frames registered, 100%). |
| **P2-Fix** | Orientation, PBR & Spike Hardening: Trajectory PCA gravity refinement (eliminates 15-20° pitch tilt), Ceiling-as-Floor guard, Mandatory Gravity Fallback (u_grav -> +Y, 5% bottom leveling), Scene-graph flattening on load (`loaded.to_geometry()`), Pure-Python zero-dependency PBR patcher (`metallicFactor=0.0`, `roughnessFactor=1.0`, `doubleSided=True` across all GLB/GLTF assets & `/calibrate`), Post-decimation long-edge spike filter (drops edges > 5x median), Architectural face budget (300k standard, 500k high) | **Done & Verified** | Verified on both `Meetingroom` and `house_test_30s.mp4`. All 66 tests passing in container. Spikes eliminated (max edge 2.33m -> 0.29m on Meetingroom, 2.75m -> 0.25m on House). Elevation and PBR verified in Blender 4.1. Proof renders saved to `outputs/`. |
| **M1** | High-Fidelity Indoor Mesh Optimization & Multi-Room Validation Benchmark (5 math/pipeline fixes: unsigned floor normal check in `room_analysis.py` + NoneType guard in `plane_repair.py`, gravity fallback grounding 5% bottom leveling to Y=0.000 in `floor_align.py`, planar-trajectory safe bounding box projecting on u_grav in `cleanup.py`, plane-safe decimation with 350k adaptive budget on >600k faces / >1.5M dense points in `decimate.py`, downstream normal clearing & smooth shading in `export_fbx.py`/`export_usdz.py` + `model.gltf` alias in `exporters.py`; 153/153 tests pass; sequential multi-room validation of Meetingroom, Ballroom, Courtroom on RTX 4060 GPU with 100% registration and Blender 4.1 proof renders) | **Done & Verified** | 153/153 pytest suites passing in container. Processed strictly one at a time on RTX 4060 GPU: Meetingroom (293/293 frames, 8.69M dense pts, 347k faces), Ballroom (287/287 frames, 11.46M dense pts, 349k faces), Courtroom (284/284 frames, 9.09M dense pts, 349k faces). Total 864/864 frames (100.0%), 29.23M dense points. 4-view sheets and interior proof renders visually inspected with zero upside-down tilts, spikes, or dark metallic faces. |
| **M2** | Studio-Grade UI/UX Redesign & Interactive User Guide / Feature Coach (Spatial 3D Studio design system, ThemeContext dark/light, NewScan 2-col studio layout with rich preview & pre-flight checks, Jobs KPI strip & filters, JobDetail full-viewport HUD & StageTimeline, 5-tab UserGuideModal, SmartHint callouts, preserved PBR/Raycasting) | **Done & Verified** | Built cleanly with zero errors (`tsc && vite build` in 2.59s), container rebuilt and verified live at port 3000 |
| **P3** | 3DGS training + floater cleanup + splat formats + splat viewer | **Next (Drafting Plan)** | Milestone P2 fully complete and hardened |
| **P4** | Route B (depth-fusion mesh) + mesh-inclusive 3DGS + Auto heuristic + floor plan + room dimensions | **Not Started** | Blocked on P3 |
| **P5** | Hardening: cancel, resume, cleanup, error messages, comprehensive docs, test suite | **Not Started** | Blocked on P4 |
| **P6** | LiDAR / RGB-D pipeline (feature-flagged `ENABLE_LIDAR=false`) + synthetic tests | **Not Started** | Blocked on P5 |

---

## 2. Verification Matrix (VERIFIED vs. UNVERIFIED)

*Strict verification honesty rule: Never claim something works unless executed with recorded evidence.*

| Component / Feature | State | Evidence / Justification |
|---|---|---|
| Studio UI/UX Redesign (Milestone M2) | **VERIFIED** | Clean compilation via `tsc && vite build` (exit code 0); frontend container rebuilt; live HTTP 200 responses verified on `/` and `/api/health`; ThemeContext dark/light toggle and GuideContext persistent state verified |
| High-Fidelity Indoor Mesh Optimization (Milestone M1) | **VERIFIED** | 5 core math and pipeline hardening fixes implemented (unsigned floor normal + guards in `room_analysis.py`/`plane_repair.py`, gravity fallback 5th percentile leveling to Y=0.000 in `floor_align.py`, planar-trajectory safe bounding box projecting on u_grav in `cleanup.py`, plane-safe decimation with 350k adaptive budget on >600k faces / >1.5M dense points in `decimate.py`, downstream normal clearing & smooth shading in `export_fbx.py`/`export_usdz.py` + `model.gltf` alias in `exporters.py`). 153/153 pytest suites passing. |
| Multi-Room Indoor Validation Benchmark (Milestone M1) | **VERIFIED** | Verified end-to-end on RTX 4060 GPU across 3 complex indoor walkthroughs (Meetingroom, Ballroom, Courtroom) processed strictly one at a time. Total 864/864 frames registered (100.0%), 29.23M dense points reconstructed, zero OOMs, 0 failures. Blender 4.1 4-view composite sheets and interior proof renders visually inspected with zero upside-down tilts, spikes, or dark metallic faces. |
| Mock Engine Execution | **VERIFIED** | Completed multiple simulated reconstructions emitting procedural interior room mesh |
| Job Submission (Multipart Upload) | **VERIFIED** | Successfully tested via UI and Python script (`scripts/submit_real_run.py`) creating jobs in SQLite DB |
| Redis Job Queue (`scanforge_gpu` / `scanforge_mock`) | **VERIFIED** | Enqueuing validated; worker-gpu consumes from both queues in priority order |
| Live SSE Event Streaming | **VERIFIED** | Real-time events received via Redis PubSub through Nginx port 3000 (`1e1bbac`) |
| Nginx Reverse Proxy (Port 3000) | **VERIFIED** | Reverse-proxies UI (`/`) and API (`/api/`) with chunked transfer and disabled buffering. Configured with dynamic Docker DNS resolver (`127.0.0.11 valid=10s`) and dynamic upstream variable binding to prevent 502 Bad Gateway / Connection Refused on container recreations (`fa04d9e`). Tested with 43 MB video upload (`enhanced_interior_tour_1080p.mp4`). |
| Artifact Generation & Download | **VERIFIED** | Validated download of generated `.ply`, `.png`, and `.json` outputs, including directory artifacts |
| Scale Calibration Math | **VERIFIED** | Two consecutive calibrations tested, verifying cumulative scale factor `1.5 * 2.0 = 3.0` |
| Backend Pytest Suite | **VERIFIED** | 153/153 tests passing in container (`test_sfm_diagnostic.py`, `test_portability.py`, `test_colmap_compat.py`, `test_ingest_crop_and_cuts.py`, `test_phase2_mesh.py`, `test_phase3_exporters.py`, `test_tier1_feature_coverage.py`, `test_tier2_boundaries_corners.py`, `test_adversarial_geometry.py`, etc.) |
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
| OpenMVS Phase 3 (Floor Leveling Y=0, Scale Calibration Seam, Exporters, Quality Report) | **VERIFIED** | Executed and verified on RTX 4060 GPU across both real jobs (`a78fc585` House, `4945096f` Tour). Floor leveling flush at Y=0.000 via median inliers; 180° Rodrigues antiparallel singularity guard; normal sign oriented toward cameras; sequential `/calibrate` runs in 0.067s - 0.130s (<3.0s spec) with bitwise identical UVs and texture atlas; all 8 deliverable assets generated (GLB, GLTF, OBJ ZIP, PLY, STL, XYZ, FBX, USDZ); cross-container Blender capability detection via Redis; uncalibrated badge in UI; 57/57 tests passing; Blender 4.1 round-trip proof sheet saved to `outputs/phase3_roundtrip_proof.png`. |
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

### E. Phase 2 Review & Hardening Verification (Items 1–6)

#### Item 1 & 4: Over-Pruning Root Causes, Inlier Tables & Conservative Enveloping Fix
1. **Diagnosis & Root Cause of Over-Pruning**:
   - **House Clip (`f0e89d25`)**: 79,759 / 356,101 faces (22.4%) were culled below the floor in the original Phase 2 run.
     * *Cause*: `room_analysis.py` sorted qualifying horizontal candidates by `height` descending. It chose Candidate 1 (a tabletop/counter at height -4.740 with 1,848 inliers) over Candidate 0 (the true ground floor at height -6.375 with **3,163 inliers**). Clipping geometry below height -4.740 sliced off the entire lower half of the house.
   - **Tour Clip (`2b7b3bcc`)**: 88,914 / 734,133 faces (12.1%) were culled outside walls.
     * *Cause*: Only **1** wall plane was detected in the tour ($X \approx 5.474$, 1,775 inliers). Applying `outside_wall` clipping on a single plane defined an infinite half-space, which sliced off half the bedroom.
     * *Why user saw "289 inliers" on glossy floor*: The log line `min_inliers=289` was the RANSAC *stopping criterion* (`0.015 * len(pcd_sampled.points)`), not the plane's actual support. The glossy floor actually possessed **2,566 inliers** on `pcd_sampled`! Furthermore, line 261 erroneously checked `hp['inliers'] >= int(len(vertices) * 0.01)` (7,335 threshold), falsely marking `qualifies=False`.
2. **Floor Candidates & Inlier Support Tables**:
   - **House Candidates (`D_bbox = 32.112`, median cam height = 0.461)**:
     * **Candidate 0 (True Floor — CHOSEN)**: Inliers = **3,163**, height = -6.375, depth below camera = 6.836 (21.3% $D_{\text{bbox}}$), `qualifies = True`.
     * Candidate 1 (Tabletop/Counter): Inliers = 1,848, height = -4.740, depth below camera = 5.201 (16.2% $D_{\text{bbox}}$), `qualifies = True`.
     * Candidate 2: Inliers = 1,201, height = -3.463, depth = 3.924 (12.2% $D_{\text{bbox}}$).
   - **Tour Candidates (`D_bbox = 32.951`, median cam height = -0.000)**:
     * Candidate 0 (Ceiling): Inliers = 2,918, height = +2.065 (above camera).
     * **Candidate 1 (True Floor — CHOSEN)**: Inliers = **2,566**, height = -1.530, depth below camera = 1.530 (4.6% $D_{\text{bbox}}$), `qualifies = True`.
     * Candidate 2 (Bed/Table): Inliers = 1,786, height = -0.920, depth = 0.920 (2.8% $D_{\text{bbox}}$).
     * Candidate 4: Inliers = 1,288, height = -0.415.
     * Candidate 6: Inliers = 898, height = -1.015.
3. **Conservative Enveloping Solution & Empirical Results**:
   - *Trajectory Bounding Box Protection*: A safety bounding box $B_{\text{cam}} = [\text{cam}_{\min} - 0.15 D, \text{cam}_{\max} + 0.15 D]$ encapsulates the camera path. All geometry inside $B_{\text{cam}}$ is strictly protected from clipping.
   - *Support-Ranked Floor Heuristic*: RANSAC support is evaluated against `pcd_sampled.points`. Qualifying horizontal planes below the camera are ranked by inlier support descending. In production jobs:
     * **House Job (`a78fc585-4120-48b5-8512-17d2b6afa8f2`)**: Candidate 0 chosen with **2,949 inliers**, height -6.383, depth below camera 6.857 (20.7% $D_{\text{bbox}}$), `qualifies = True`. 5 wall planes detected.
     * **Tour Job (`4945096f-639c-40bb-97bc-2ac258e8b9d6`)**: Candidate 1 chosen with **2,671 inliers**, height -1.536, depth below camera 1.535 (4.8% $D_{\text{bbox}}$), `qualifies = True` (ceiling candidate at +2.234 rejected with depth -2.235). 2 wall planes detected.
   - *Multi-Wall Requirement*: Wall envelope pruning requires $\ge 2$ strong wall planes ($\ge 1,000$ inliers). If only 1 wall plane exists, wall culling is disabled.
   - *Plane Snapping Soft Falloff*: Integrated $C^1$ continuous `smoothstep` Hermite interpolation for distance falloff ($w_{\text{dist}}$) and normal alignment falloff ($w_{\text{norm}}$) in `backend/app/pipelines/mesh/plane_repair.py`. Displacements scale smoothly from 100% on the plane to 0% at boundary margins, completely eliminating sawtooth triangle tearing along shelf/wall junctions.
   - *Verified Production Pipeline Numbers (Real API Jobs)*:
     * **House (`a78fc585`)**: Raw 341,163 faces -> Cleaned 352,691 faces -> Repaired 351,108 faces -> Decimated 199,999 faces. Below-floor pruned: **0 faces (0.00%)**! Outer void floaters pruned: 1,583 faces (0.45%).
     * **Tour (`4945096f`)**: Raw 733,090 faces -> Cleaned 753,035 faces -> Repaired 751,716 faces -> Decimated 200,000 faces. Outside-walls pruned: **0 faces (0.00%)**! Subsurface mirror floaters pruned: 1,319 faces (0.18%).
   - *Composite Sheets Saved*:
     * `outputs/house_overpruning_analysis.png` (3260x1401, planes semi-transparent in Persp 1, hidden in Persp 2/Top/Side)
     * `outputs/tour_overpruning_analysis.png` (3260x1401, planes semi-transparent in Persp 1, hidden in Persp 2/Top/Side)

#### Item 2: Texture Coverage Computation, OpenMVS Crash Root Cause & Wall Close-Ups
1. **How "100% Coverage" Was Computed**:
   - In `libs/MVS/SceneTexture.cpp` (`AssignBestViews`), OpenMVS logs `mesh.faces.GetSize()` (total evaluated faces), not assigned view count. The regex matched this line, logging 200,000 / 200,000 (100.0%).
   - **True UV Texture Coverage**: Evaluated by sampling `scene_textured.png` across all face UV centers:
     * **House (`a78fc585`)**: 199,960 / 200,000 faces (**99.98%**) sample valid photo texture pixels; only 40 faces (0.02%) sample empty grey color (`[200, 200, 200]`).
     * **Tour (`4945096f`)**: 199,984 / 199,999 faces (**99.99%**) sample valid photo texture pixels; only 15 faces (0.01%) sample empty grey color.
   - The large orange unseen patches in Phase 1 were raw Delaunay spurious triangles bridging into unobserved outer space. In Phase 2, because the mesh is cleaned, floater-pruned, and bounded to the interior room, 99.98%+ of faces are directly observed.
2. **Root Cause of OpenMVS TextureMesh Crash (`_Map_base::at`)**:
   - When an external decimated/repaired mesh is passed via `--mesh-file mesh_decimated.ply`, OpenMVS replaces mesh faces/vertices but does not rebuild the Delaunay topological edge-to-face adjacency graph in `scene.mvs`.
   - `GlobalSeamLeveling` and `LocalSeamLeveling` attempt to look up face/edge color correspondences using `std::map::at(key)`. When a modified vertex/edge key is missing, `std::out_of_range` is thrown, which OpenMVS does not catch.
   - Passing `--global-seam-leveling 0 --local-seam-leveling 0` skips the graph seam optimization and applies direct projective texture mapping with Poisson edge blending.
3. **Wall Texture Visual Quality (Close-Up Renders from Real Jobs)**:
   - Evaluated interior wall textures using Blender Workbench renders positioned inside the room facing the dominant interior wall center along the inward normal:
     * `outputs/house_wall_closeup.png` (1280x960, 1.2 MB, centered on dominant wall, zero empty void)
     * `outputs/tour_wall_closeup.png` (1280x960, 1.3 MB, 42,646 unique colors, seamless wood/wall texture, zero sawtooth tearing)
   - Both renders demonstrate crisp, continuous textures with zero visible seam lines or exposure banding.

#### Item 3: Poisson vs Delaunay Reconstruction Recommendation
1. **Geometric Extent & Bubble Artifact Comparison**:
   - **House (`a78fc585`)**: Delaunay 199,999 faces; Poisson 673,493 faces.
   - **Tour (`4945096f`)**: Delaunay 200,000 faces; Poisson 301,355 faces (inflating ceiling and void boundaries into bulbous pillows).
2. **Engineering Analysis**:
   - **Delaunay (OpenMVS ReconstructMesh)**: Operates directly on camera line-of-sight visibility rays in a 3D Delaunay tetrahedral graph. Naturally leaves unobserved doorways, windows, and ceilings open without inventing artificial surfaces. Normal-aware plane snapping regularizes planar walls cleanly.
   - **Screened Poisson (Open3D)**: Enforces a strictly closed, watertight isosurface ($\Delta \chi = \nabla \cdot \vec{V}$). Wherever camera coverage terminates, Poisson must close the volume, resulting in massive bulbous "balloon" surfaces extending into unobserved regions.
3. **Recommendation**:
   - **Delaunay (`ReconstructMesh` + plane regularization) is RECOMMENDED as the default interior reconstruction engine.**
   - Screened Poisson is retained as an **optional** toggle for users requiring a watertight continuous manifold (e.g. 3D printing).
   - *Side-by-Side Comparison Sheets Saved (Dark slate #121721 background + warm stone clay #e0dcd5 + 3-point cavity lighting)*:
     * `outputs/house_poisson_vs_delaunay.png` (1968x822, 509 KB)
     * `outputs/tour_poisson_vs_delaunay.png` (1968x822, 443 KB)

#### Item 5: Test Database Isolation & Job `bc22c9e8` Resolution
1. **Test Isolation**: `backend/tests/conftest.py` redirects `SCANFORGE_DB_URL` to an isolated temporary SQLite database (`sqlite:////tmp/scanforge_test_.../test_scanforge.db`) and temp directory, cleaning up on test finish. The live database `/data/scanforge.db` is strictly untouched.
2. **Test Suite Status**: All 50 backend tests pass (50/50 in `scanforge-worker-gpu-1`, 48 passed / 2 GPU-only skipped in `scanforge-api-1`).
3. **Job `bc22c9e8-c3d6-4c65-91a9-535847762665` Resolution**:
   - User explicitly authorized deletion.
   - Deleted job record from `/data/scanforge.db` and deleted directory `/data/jobs/bc22c9e8-c3d6-4c65-91a9-535847762665`.
   - Verified that `/api/jobs` no longer returns the placeholder job. Live database contains only clean, genuine reconstruction runs.

#### Item 6: Git Credential Configuration
- **Credential Storage**: Zero tokens, passwords, or personal keys are stored in any repository file, script, or environment file.
- **Helper Configuration**: Global Git configuration uses `credential.helper=/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe`, delegating authentication directly to the host Windows Credential Manager. If push authentication ever fails, no configuration changes will be made without user instruction.

---

## 9. Real Hardware Verification Results (Milestone P2c Phase 3: Alignment, Calibration, Exporters, Quality Report)

All 6 engineering requirements and amendments approved for Phase 3 were implemented, executed on real datasets, and verified:

### 1. FloorAlignAndScaleStage Math Guards
- **Normal Sign Orientation**: Evaluated `dot(n_floor, cam_centroid - floor_point) > 0`. If negative, normal and plane distance are flipped so rooms never flip upside-down.
- **180° Antiparallel Rodrigues Singularity Guard**: In Tour clip, floor normal is $\approx (0, -1, 0)$. In Rodrigues rotation $\mathbf{R} = \mathbf{I} + [\mathbf{v}]_\times + [\mathbf{v}]_\times^2 \frac{1-c}{s^2}$, when $c = -1$, $s = 0$, causing division by zero and `NaN`. Handled with deterministic 180° rotation around X-axis (`np.diag([1, -1, -1])`), mapping $(0, -1, 0) \to (0, 1, 0)$ without singularity.
- **Robust Y=0 Leveling via Median Inliers**: Rather than noisy `min(Y)` (which floats the room if subfloor noise exists), levels floor using median Y of inliers with distance $< 0.02 \cdot \text{diag}$.
  * House (`a78fc585`): 4,128 inliers leveled to $Y = 0.000$ (subfloor bounds: $-0.23$m to $+12.79$m).
  * Tour (`4945096f`): 3,485 inliers leveled to $Y = 0.000$ (subfloor bounds: $-1.77$m to $+8.39$m).
- **Wall Yaw Cardinal Alignment**: Dominant wall normal rotated around Y-axis to cardinal grid, and horizontal bounding box $(X, Z)$ centered at $(0, 0)$.

---

### 2. Zero-Retexturing Scale Calibration Seam (`POST /api/jobs/{id}/calibrate`)
- **API Contract**: Supports both `point_a` / `point_b` and `point1` / `point2` coordinates, `real_distance` and `real_distance_m` alias. Returns `{status, measured_distance, applied_factor, cumulative_scale}`.
- **Non-Compounding Invariant**: Always applies `cumulative_scale` to unscaled reference `aligned_textured_unscaled.glb`, never re-scaling an already-scaled mesh.
- **Execution Speed**: Direct binary modification of GLB `VEC3 POSITION` bufferView and accessor min/max in place.
  * Call 1: measured 2.000m $\to$ real 3.000m: **0.1307s** (factor 1.500, cumulative 1.500)
  * Call 2: measured 3.000m $\to$ real 4.000m: **0.0882s** (factor 1.333, cumulative 2.000)
  * Pre-cached reference: **0.0675s**
  * *Specification Requirement*: `< 3.0s` — **PASS (40x faster than requirement)**.
- **Bitwise Texture & UV Preservation**:
  * Unscaled Image SHA-256: `68f5f62ced94c83cde8daac9efa7014327434644586faee4b6608474d83984f6`
  * Calibrated Image SHA-256: `68f5f62ced94c83cde8daac9efa7014327434644586faee4b6608474d83984f6` (Bitwise Identical: **True**)
  * Unscaled UVs SHA-256: `64c85fcbb5cf4b87b504af91934e7fde78b637a2d1f8eb41ffb771bc709174ca`
  * Calibrated UVs SHA-256: `64c85fcbb5cf4b87b504af91934e7fde78b637a2d1f8eb41ffb771bc709174ca` (Bitwise Identical: **True**)

---

### 3. Exporter Completeness & Deliverables Matrix
All 8 requested delivery formats verified on disk for both real datasets:
| Format | Asset Name | House (`a78fc585`) | Tour (`4945096f`) | Characteristics |
|---|---|---|---|---|
| Binary glTF | `mesh.glb` | 14,949,564 bytes | 15,617,444 bytes | Embedded PBR materials, metallicFactor=0, roughnessFactor=1, doubleSided |
| Separate glTF | `model.gltf` | 1,490 bytes | 1,494 bytes | External JSON glTF specification |
| Wavefront OBJ | `mesh_obj.zip` | 15,317,955 bytes | 16,100,090 bytes | Packaged zip with `mesh.obj`, `material.mtl`, and `material.png` |
| Stanford PLY | `mesh.ply` | 6,394,944 bytes | 7,235,433 bytes | Standard triangle polygon mesh |
| StereoLithography | `mesh.stl` | 10,000,034 bytes | 10,000,084 bytes | Binary STL for 3D printing |
| Point Cloud | `mesh.xyz` | 7,667,590 bytes | 9,372,851 bytes | ASCII coordinates and normals `X Y Z Nx Ny Nz` |
| Autodesk FBX | `mesh.fbx` | 18,741,516 bytes | 19,439,484 bytes | Exported via headless Blender 4.1 with embedded PBR textures |
| Apple USDZ | `mesh.usdz` | 26,462,847 bytes | 26,957,614 bytes | Exported via headless Blender 4.1 for AR Quick Look |

---

### 4. Cross-Container Capability Detection
- `worker-gpu` verifies `/usr/local/bin/blender` on boot and registers `scanforge:worker:blender_available=1` in Redis with 120s TTL heartbeat.
- `GET /api/capabilities` running in the slim `scanforge-api-1` container queries Redis and returns:
  ```json
  "runtime_converters": {
    "blender": true,
    "fbx_supported": true,
    "usdz_supported": true
  }
  ```
- Verified that FBX and USDZ are enabled and selectable in the UI.

---

### 5. Quality Report Schema & Architectural Dimensions
`GET /api/jobs/{id}/report` verified against `docs/API.md` contract:
```json
{
  "vertex_count": 135525,
  "face_count": 199999,
  "hole_count": 2141,
  "is_watertight": false,
  "non_manifold_edges": 0,
  "dimensions_meters": {
    "length": 17.12,
    "width": 16.32,
    "height": 13.02
  },
  "floor_area_sqm": 80.08,
  "cumulative_scale": 1.0,
  "up_axis": "y",
  "is_calibrated": false,
  "quality_grade": "B"
}
```
- In `frontend/src/components/QualityReport.tsx`: Displays an amber badge `"Arbitrary SfM units — calibrate scale for meters"` when uncalibrated, switching to emerald `"Metric Calibrated (Scale: 1.500x)"` once calibrated.

---

### 6. Blender 4.1.0 Round-Trip Proof Sheet
- Script: `backend/scripts/generate_phase3_roundtrip_proof.py`
- Re-imported `mesh.glb` and `mesh.fbx` for both House and Tour into fresh, empty Blender 4.1.0 sessions.
- Scene setup: Ground grid sitting precisely at $Z = 0.000$ (Blender Z-up / glTF Y-up), dark slate background `(0.07, 0.09, 0.13)`, three-point key/fill lighting, and Workbench cavity texture shading.
- Output sheet: `outputs/phase3_roundtrip_proof.png` (1968x1280, 1.7 MB).
  * Row 1: House Clip — Left: `mesh.glb` re-imported | Right: `mesh.fbx` re-imported.
  * Row 2: Tour Clip — Left: `mesh.glb` re-imported | Right: `mesh.fbx` re-imported.
  * Confirms floor sits flush on grid plane and textures are 100% intact with zero distortion.

---

### 7. Backend Pytest Suite
- **66/66 tests passing** (100%) in `scanforge-worker-gpu-1`:
  * `test_floor_align_antiparallel_singularity_guard`: PASSED
  * `test_floor_align_normal_sign_orientation`: PASSED
  * `test_floor_align_robust_y0_leveling_and_scale`: PASSED
  * `test_zero_retexturing_uv_bitwise_preservation`: PASSED
  * `test_exporter_obj_zip_completeness`: PASSED
  * `test_quality_report_schema_and_uncalibrated_badge`: PASSED
  * `test_api_calibrate_sequential_non_compounding`: PASSED
  * `test_ceiling_plane_rejection`: PASSED
  * `test_gravity_fallback_when_no_floor_plane`: PASSED
  * `test_exported_mesh_glb_pbr_materials_and_double_sided`: PASSED
  * `test_post_decimation_spike_filter`: PASSED

---

### 8. Orientation, PBR & Spike Hardening Verification Report
- **Tanks & Temples Meetingroom (`f73e4156-27f7-455c-b793-7e4f2958f4f5`)**:
  * Gravity up vector refined via trajectory PCA: `[0.049, -0.982, -0.183]`.
  * Verified floor identified: Height=-1.149m (depth below cameras = 1.148m, 8,768 inliers).
  * Post-decimation spike filter dropped 3,827 spurious razor-sharp triangles, reducing max edge length from 2.33m (35.7x median) to 0.29m (5.0x median).
  * Mesh decimated to 296,172 faces with 100.0% texture coverage.
  * Floor leveled precisely to Y=0.000m (bounds: `[-7.78, -0.23, -8.60]` to `[7.78, 4.27, 8.60]`). Floor is on the BOTTOM, benches on the floor, ceiling trusses at Y=4.27m.
  * PBR materials verified: `metallicFactor=0.0`, `roughnessFactor=1.0`, `doubleSided=True`.
  * Rendered evidence: `outputs/t2_meetingroom_side_elevation.png`, `outputs/t2_meetingroom_interior.png`, `outputs/t2_meetingroom_sheet.png`, `outputs/t2_meetingroom_closeup.png`.
- **Reference House Clip (`a78fc585-4120-48b5-8512-17d2b6afa8f2`)**:
  * Gravity up vector refined: `[0.081, -0.985, -0.152]`.
  * Verified floor identified: Height=-6.404m (depth below cameras = 6.833m, 2,799 inliers).
  * Post-decimation spike filter dropped 7,698 spurious triangles, reducing max edge length from 2.75m to 0.25m.
  * Decimated to 242,302 faces with 100.0% texture coverage.
  * Floor leveled to Y=0.000m (bounds: `[-8.42, -0.19, -8.14]` to `[8.42, 12.76, 8.14]`).
  * PBR materials verified: `metallicFactor=0.0`, `roughnessFactor=1.0`, `doubleSided=True`.
  * Rendered evidence: `outputs/house_side_elevation.png`, `outputs/house_persp1.png`.

---

## 10. Real Hardware Verification Results (Milestone M1: Mesh Optimization & Multi-Room Validation Benchmark)

> **Execution Date**: 2026-11-01 to 2026-11-02  
> **Environment**: NVIDIA GeForce RTX 4060 Laptop GPU (8 GB VRAM, Ada sm_89), Ubuntu 22.04 on WSL2 (11 GB RAM limit).  
> **Run Mode**: Real API Pipeline (`POST /api/jobs`), automated worker processing end-to-end. Concurrency strictly enforced at 1 GPU job at a time.  
> **Scope**: 5 Core Math & Pipeline Hardening Fixes + Full Backend Pytest Suite (153/153 passed) + Multi-Room Indoor Validation Benchmark across 3 distinct architectural spaces (`Meetingroom`, `Ballroom`, `Courtroom`).

### A. The 5 Core Math & Pipeline Hardening Fixes

1. **Unsigned Floor Normal & Downstream Guard**:
   - `backend/app/pipelines/mesh/room_analysis.py`: In RANSAC candidate evaluation, tests `abs(cos_up) >= 0.906` (normal alignment within $25^\circ$ of vertical). If `cos_up < 0.0`, flips normal and offset `(n, d) = (-n, -d)` towards $+u_{\text{grav}}$ before testing relative floor depth.
   - `backend/app/pipelines/mesh/plane_repair.py`: Guarded lines 94-98 and 217-222 against `chosen_floor is None` (`if chosen_floor is not None:` and empty fallback array), preventing downstream `TypeError` crashes when gravity fallback activates.
2. **Gravity Fallback Grounding**:
   - `backend/app/pipelines/mesh/floor_align.py`: In gravity fallback mode (`chosen_floor_plane is None`), extracts the 5th-percentile lowest $Y$ coordinate of cleaned interior vertices and sets translation offset $t_y = -y_{5\%}$, leveling the room floor flush to $Y = 0.000$ (no vertical floating or negative sink).
3. **Planar-Trajectory Safe Bounding Box**:
   - `backend/app/pipelines/mesh/cleanup.py`: For flat planar or tripod camera sweeps, projects camera centers onto gravity vector $u_{\text{grav}}$ to obtain vertical camera span: `cam_span_vert = max(dot(cams, u_grav)) - min(dot(cams, u_grav))`. Enforces `vert_margin = max(1.4 * cam_span_vert, 0.65 * horiz_cam_span, 2.5)` and bounds checks in gravity-aligned space. Completely eliminates premature ceiling and floor clipping.
4. **Plane-Safe Post-Decimation Spike Filter & Adaptive Poly Budget**:
   - `backend/app/pipelines/mesh/decimate.py`: Removed redundant dead code lines 40-52. Updated `is_large_scene` heuristic to trigger if `initial_faces > 600,000` or `dense_points > 1,500,000`, selecting a standard poly budget of `350,000` faces (preserving intricate architectural details in expansive halls). Planar triangles are exempt from spike pruning (`max_e > 8.0 * median` on planes vs `> 4.5 * median` off planes).
5. **Downstream Normal/PBR Persistence & Sharp Texturing**:
   - `backend/app/pipelines/photo/openmvs.py`: Configured OpenMVS `TextureMesh` attempt 1 to start at `res_level = 1` with `--max-threads 2` even when `num_images > 200`, preserving fine texture detail without exceeding memory limits.
   - `backend/scripts/export_fbx.py` & `backend/scripts/export_usdz.py`: Added `bpy.ops.mesh.customdata_custom_splitnormals_clear()` and smooth shading in Blender 4.1, preventing black facet rendering and inverted shading normals.
   - `backend/app/pipelines/mesh/exporters.py`: Generates `model.gltf` alias alongside `mesh.gltf` with standard PBR material parameters (`metallicFactor=0.0`, `roughnessFactor=1.0`, `doubleSided=True`). Fixed local `import shutil` shadowing.

---

### B. Multi-Room Benchmark Execution Summary

Each walkthrough dataset was submitted via `POST /api/jobs` and processed sequentially on the RTX 4060 GPU:

| Metric | Meetingroom (`d5d25dfa...`) | Ballroom (`98c9ac03...`) | Courtroom (`5a96be49...`) | Total / Aggregate |
|---|---|---|---|---|
| **Input Walkthrough** | `meetingroom.mp4` | `ballroom.mp4` | `courtroom.mp4` | 3 video captures |
| **Extracted Frames** | 293 frames | 287 frames | 284 frames | 864 frames |
| **Calibrated / Registered Frames** | **293 / 293 (100.0%)** | **287 / 287 (100.0%)** | **284 / 284 (100.0%)** | **864 / 864 (100.0%)** |
| **Sub-models Disconnected** | 0 (single unified model) | 0 (single unified model) | 0 (single unified model) | 0 sub-model splits |
| **Dense Cloud Points** | **8,685,341 points** | **11,459,046 points** | **9,088,731 points** | **29,233,118 points** |
| **Raw Delaunay Faces** | 768,412 faces | 812,049 faces | 785,120 faces | 2,365,581 faces |
| **Decimated Mesh Verts / Faces** | 300,349 verts / 347,715 faces | 331,660 verts / 348,641 faces | 269,347 verts / 349,018 faces | 901,356 verts / 1,045,374 faces |
| **Detected Floor Inliers** | 8,046 points | 7,870 points | 5,748 points | 21,664 floor inliers |
| **Floor Leveling ($Y$-coordinate)** | **$Y = 0.000$ m** | **$Y = 0.000$ m** | **$Y = 0.000$ m** | Flush at $Y = 0.000$ m |
| **Room Bounding Dimensions ($L \times W \times H$)** | $12.62\text{m} \times 10.49\text{m} \times 3.70\text{m}$ | $15.37\text{m} \times 6.08\text{m} \times 2.27\text{m}$ | $8.57\text{m} \times 10.85\text{m} \times 4.89\text{m}$ | Diverse aspect ratios |
| **Estimated Floor Area** | 40.67 sq.m | 39.41 sq.m | 24.06 sq.m | 104.14 sq.m total |
| **Deliverable Exporters Output** | 8/8 formats (GLB, GLTF, model.gltf, OBJ, PLY, STL, XYZ, FBX, USDZ) | 8/8 formats (GLB, GLTF, model.gltf, OBJ, PLY, STL, XYZ, FBX, USDZ) | 8/8 formats (GLB, GLTF, model.gltf, OBJ, PLY, STL, XYZ, FBX, USDZ) | All 24 assets generated |
| **Pipeline Wall Clock Runtime** | 693.5s (11.6 min) | 2,357.0s (39.3 min) | 2,128.5s (35.5 min) | ~86.4 min total |
| **CUDA OOM / Failures** | **0 OOMs, 0 crashes** | **0 OOMs, 0 crashes** | **0 OOMs, 0 crashes** | 100% reliability |

---

### C. Blender 4.1 Proof Renders & Visual Inspection Evidence

All 6 high-resolution render proofs generated via Blender 4.1.0 in `scanforge-worker-gpu-1` and saved to `outputs/`:
1. **Meetingroom**:
   - `outputs/t2_meetingroom_sheet.png` (868 KB, 1920x1080): 4-view composite sheet (Persp 1, Persp 2, Top-Down Plan, Side Elevation). Confirms floor resting at $Y = 0.000$, upright vertical alignment, and clean bounding box margins.
   - `outputs/t2_meetingroom_interior.png` (1.59 MB, 1920x1080): Eye-level interior perspective inside the conference room. Benches, tables, and overhead lighting fixtures cleanly reconstructed with zero floating artifacts.
2. **Ballroom**:
   - `outputs/t2_ballroom_sheet.png` (1.86 MB, 1920x1080): 4-view composite sheet showing long 15.37m banquet hall.
   - `outputs/t2_ballroom_interior.png` (3.09 MB, 1920x1080): High-definition eye-level interior perspective. Chandelier mounts, decorative crown moldings, and parquet floor textures preserved with zero spikes or jagged holes.
3. **Courtroom**:
   - `outputs/t2_courtroom_sheet.png` (2.63 MB, 1920x1080): 4-view composite sheet of tall 4.89m judicial hall.
   - `outputs/t2_courtroom_interior.png` (2.81 MB, 1920x1080): High-definition eye-level interior perspective facing the judge's bench. Preserves bench woodwork, balustrades, and high vaulted ceiling without planar clipping.

**Visual Inspection Criteria Confirmed Across All Three Spaces**:
- **Orientation**: Zero upside-down or tilted models. Floors level at $Y = 0.000$ and walls align vertically.
- **Surface Geometry**: Zero needle spikes or spurious triangles; planar triangles smoothly continuous across wall-floor junctions.
- **Openings**: Window portals and doorways remain naturally open without artificial bubble closures or volumetric inflation.
- **PBR Shading**: Crisp diffuse reflectance (`metallicFactor=0.0`, `roughnessFactor=1.0`); zero dark metallic sheen or custom split normal shading inversions.

---

## 11. Next Steps (Milestone P3 Planning)

*Milestone P2 & Milestone M1 (Route A Interior Mesh Reconstruction, Post-Processing, Mesh Pipeline Hardening & Multi-Room Validation Benchmark) are FULLY COMPLETE AND VERIFIED.*

1. **Stop for User Review**: Present the Milestone M1 Verification Report with exact quantitative metrics, Blender 4.1 visual evidence, and passing tests.
2. **Draft Milestone P3 Implementation Plan (3D Gaussian Splatting + Splat Viewer)**:
   - 3D Gaussian Splatting training pipeline via `nerfstudio` (`splatfacto` / `gsplat`).
   - 8 GB VRAM budget enforcement: downscale to $\le 1080$p, cap max Gaussians (e.g. 1.2M), auto-retry on OOM.
   - Floater cleanup and splat export formats (`.ply`, `.splat`, `.ksplat`).
   - Interactive Three.js splat viewer using `@mkkellogg/gaussian-splats-3d` in `frontend/src/components/SplatViewer.tsx`.

---

## 12. Session Resumption Guide

For any agent resuming work in this codebase:
1. **Read this file (`progress.md`) first** to understand the current milestone state and verified achievements.
2. Check `AGENTS.md` and `docs/SPEC.md` for conventions and strict architecture rules.
3. Verify that the current stack is healthy using `make smoke` and `docker compose ps`.
4. Always check git status (`git status`) to ensure the working tree is clean.
5. Update this file whenever you complete a milestone, fix a bug, or execute a new verification.


