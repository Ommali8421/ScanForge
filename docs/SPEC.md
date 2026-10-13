

# MY ENVIRONMENT (overrides the generic ASSUMPTIONS section)
- Windows 11, NVIDIA GeForce RTX 4060 with 8 GB VRAM (Ada architecture, compute capability 8.9). Use WSL2 (Ubuntu 22.04) + Docker Desktop with GPU passthrough. All project files live inside the WSL filesystem (~/scanforge), never under /mnt/c.
- Set TORCH_CUDA_ARCH_LIST=8.9 and CUDA architectures to 89 for COLMAP/OpenMVS/gsplat builds. Choose a CUDA toolkit version that matches the PyTorch build you pin, and verify it.
- 8 GB VRAM is a hard budget. Design every preset to fit it:
  - Photo: cap COLMAP max image size (about 2000 px), use OpenMVS resolution-level 1 or 2 for Standard/High, and expose a "low-memory" retry that automatically drops the resolution level if a stage fails with an out-of-memory error.
  - 3DGS: default to plain `splatfacto` (NOT splatfacto-big). Downscale training images (about 1080p max; try the downscale factor option), cap total splat count, and catch CUDA OOM by retrying with a lower setting.
  - Mesh-inclusive 3DGS: prefer 2DGS + TSDF at reduced resolution; treat Gaussian Opacity Fields/marching tetrahedra as optional because of memory use.
  - Monocular depth fallback: use the small/base model variant.
- Run only one GPU job at a time (concurrency = 1) and free GPU memory between stages (separate subprocesses, not one long-lived process).
- `scripts/doctor.py` must check: Windows GPU driver via nvidia-smi inside WSL, Docker GPU access, free VRAM, free disk space, WSL memory limit, and warn if the project is under /mnt/c.
- First docker builds will be slow (COLMAP, OpenMVS, gsplat CUDA compile). Use multi-stage builds and BuildKit cache mounts so rebuilds are fast, and say in the plan how long the first build is expected to take.
# USE CASE: INTERIORS (overrides generic defaults where they conflict)
The primary use is scanning rooms and whole apartments/houses, not small objects. Optimize for this.

## Priorities and build order
1. Shared SfM (COLMAP) tuned for interiors → 2. 3DGS (best visual result for interiors) → 3. LiDAR/RGB-D fusion (best geometry and true scale) → 4. Photo-scan mesh. Update the milestones accordingly.
Default scan type in the UI = 3DGS for video input, LiDAR when an .r3d/RGB-D file is uploaded (auto-detect and suggest).

## SfM tuning for interiors
- Walk-through videos: use sequential matching with loop closure (vocab-tree loop detection), single shared camera, and a camera model that handles wide-angle phone lenses (verify OPENCV vs SIMPLE_RADIAL on test data; offer a "wide-angle / ultra-wide" toggle).
- Frame selection: prefer a fixed spatial/temporal spacing plus sharpness filtering; reject frames with severe motion blur and rolling-shutter smear. Warn about fast rotation (low parallax).
- Low-light/exposure: detect large frame-to-frame exposure swings and warn the user to lock exposure/focus; apply optional exposure normalization before SfM.
- If COLMAP registers several disconnected models (common when moving between rooms), merge them if possible; otherwise report which part registered and offer to process the largest part.

## 3DGS for rooms on 8 GB VRAM
- Train on downscaled images (about 1080p or less), plain `splatfacto`, cap the maximum number of Gaussians, and retry automatically at a lower setting on CUDA OOM.
- Use splatfacto's camera pose/appearance refinement options if they help with exposure changes (verify what is available in the pinned version).
- Floater cleanup is mandatory for interiors: statistical outlier removal, opacity/scale filtering, and a user-adjustable crop box so the viewer shows only the room (no background haze outside windows/doors).
- Splat viewer must work with first-person-style navigation (WASD + mouse look) in addition to orbit.
- Mesh-inclusive mode for interiors: use depth/normal-regularized training (2DGS or monocular-depth-supervised) + TSDF in unbounded mode; walls and floors should come out flat.

## Geometry quality for textureless walls (Photo and mesh outputs)
- OpenMVS leaves holes on blank walls. After meshing, run plane-aware repair: detect dominant planes (RANSAC in Open3D), fill holes lying on those planes, regularize planar regions, remove ghost surfaces behind windows/mirrors.
- Offer an alternative mesh route for interiors: TSDF fusion from per-frame depth (from the splat, or from a monocular depth model aligned to the sparse points), compared against the OpenMVS route in `docs/PIPELINES.md` with sample results.
- Mesh decimation presets must keep planar walls clean (use quadric decimation with planarity-aware settings or verify the result visually).

## LiDAR / RGB-D for rooms (highest geometric accuracy, metric scale)
- Tune TSDF for room scale: larger voxel size than object scans (about 1-2 cm; make it a preset), larger truncation distance, depth range clamp to the sensor's reliable range, use the confidence map when present, and run pose-graph or loop-closure refinement to reduce drift over long walks (Open3D RGB-D odometry/registration or refine with COLMAP poses; verify what works on real data).
- Handle multi-room scans by chunking the TSDF volume to stay within memory, then merging.
- Output must be in real-world meters.

## Scale and orientation (important for interiors)
- Photo/3DGS reconstructions have arbitrary scale. Add a scale-calibration step: the user enters one known real distance (for example ceiling height or a door width) by picking two points in the viewer, and the backend rescales all outputs. LiDAR results are already metric.
- Auto-align the floor to Y=0 (or Z=0 per the chosen up-axis) by RANSAC plane fitting on the lowest dominant plane, and level the model so walls are vertical.

## Interior-specific outputs (add to the format matrix)
- Top-down floor plan as PNG + SVG (orthographic projection or horizontal slice of the cleaned mesh/point cloud), stretch goal: DXF.
- Room dimensions summary (bounding box length/width/height, approximate floor area) shown in the results page and exported as JSON.
- Keep the usual mesh/splat/point-cloud formats.

## Capture guidance in the UI
On the New Scan page show a short, scan-type-specific tip panel for interiors: lock exposure and focus, keep lights constant, move slowly, avoid pure rotation in place, overlap passes, include corners/furniture for texture, cover mirrors/screens or avoid pointing at them, one continuous walk per floor with a return to the start for loop closure, turn on all lights or shoot in even daylight, and keep videos under the configured limit (split large homes by room). Show warnings after upload based on the video analysis (blur, exposure swings, too fast).

## Interior test data
Extend `scripts/make_sample_data.py` with a synthetic room (four walls, floor, ceiling, a couple of boxes) rendered from a walk-through camera path with known poses and depth, so the TSDF, scale calibration, floor alignment and floor-plan outputs can be tested without real captures. Also document one public indoor sample dataset to try for real runs (verify the license).
# MISSION
Build "ScanForge": a self-hostable 3D-scanning web app that replicates the core capabilities of the KIRI Engine app using open-source reconstruction tools. A user uploads a video (or an RGB-D capture), picks a scan type, picks one or more output formats, and gets downloadable 3D files plus an in-browser preview.

Three scan types (the three modes of KIRI Engine):
1. PHOTO SCAN – photogrammetry → textured mesh
2. 3DGS SCAN – 3D Gaussian Splatting → splat file (optionally + mesh, "mesh-inclusive 3DGS")
3. LIDAR SCAN – RGB-D (depth + camera poses) → fused mesh / point cloud

Do NOT use KIRI's name, logo or branding anywhere. Product name is "ScanForge".

# HOW TO WORK (Antigravity instructions)
- Start in Planning mode. First produce an Implementation Plan artifact (architecture, assumptions, risks, phased milestones, test plan). Wait for my approval before writing code.
- Create `AGENTS.md` in the repo root with the conventions below so every agent session follows them.
- You may split work across parallel agents: (A) backend + job system, (B) frontend, (C) reconstruction pipelines, (D) Docker/infra/tests. Agree on the API contract in `docs/API.md` first.
- NEVER guess CLI flags, package versions or APIs from memory. Run `<tool> --help`, read the installed package's docs, or use the browser to read official docs before using them. Pin every version you end up using in `docs/VERSIONS.md`.
- After each phase: run the tests, show me a walkthrough artifact (screenshots/logs of the real UI working), and list what is verified vs. unverified. Do not claim something works unless you ran it.
- If a required GPU/tool is missing in my environment, don't stall: use the MOCK engine (below), finish everything else, and clearly list what still needs real-hardware verification.

# ASSUMPTIONS (state yours in the plan; flag any you change)
- Target runtime: Linux or Windows+WSL2, Docker with NVIDIA GPU (CUDA) support. Reconstruction stages need an NVIDIA GPU; the app must still boot and be fully demoable without one via MOCK mode.
- Single-machine deployment, single GPU worker, jobs processed one at a time (configurable concurrency).
- No authentication in v1 (add a clean seam for it). Local filesystem storage behind a storage interface so S3/MinIO can be added later.

# TECH STACK
Backend: Python 3.11+, FastAPI, Pydantic v2, SQLModel + SQLite (Postgres-ready), Redis + RQ or Celery for the job queue (pick one, justify), Server-Sent Events for live progress. Uvicorn.
Frontend: React + TypeScript + Vite + Tailwind. three.js (react-three-fiber) for GLB/PLY mesh preview. For splat preview use a maintained web Gaussian-splat viewer (evaluate options, verify maintenance and license, pin the version; fallback = render splat centers as a colored point cloud).
Infra: Docker Compose (services: frontend, api, worker-gpu, redis), `.env` driven config, health checks.
Tooling: ffmpeg, COLMAP (CUDA build, optional GLOMAP as alternative SfM), OpenMVS, nerfstudio (splatfacto, gsplat backend), Open3D, trimesh, pygltflib, xatlas, Blender (headless, as an external converter process for FBX/USDZ), optional rembg for masking.

# ARCHITECTURE
Browser → FastAPI (upload, validation, job CRUD, SSE, downloads) → queue → GPU worker → Pipeline runner executing ordered Stages → artifacts on disk → exporter → API serves files.

Core abstractions (put in `backend/app/pipelines/base.py`):
- `Stage`: name, `run(ctx) -> StageResult`, declared inputs/outputs, `weight` for progress, idempotent + cached (skip if outputs exist and params hash unchanged → enables resume after crash).
- `Pipeline`: ordered list of Stages per scan type, built by a registry keyed by `ScanType`.
- `JobContext`: job id, workdir, params, logger, progress callback, cancel token (check between stages and kill subprocesses on cancel).
- `ToolRunner`: single wrapper around `subprocess` that streams stdout/stderr into the job log, parses progress where possible, enforces timeouts, and raises typed errors with the last 50 log lines.
- Engines are pluggable via interfaces (`SfMEngine`, `MVSEngine`, `SplatTrainer`, `SplatMesher`, `DepthSource`, `Exporter`) so e.g. OpenMVS (AGPL) can be swapped for AliceVision/Meshroom later.
- MOCK engine: every stage can run in a fake mode that sleeps, emits realistic progress, and outputs a bundled sample mesh/splat. Enabled with `SCANFORGE_ENGINE=mock`. The UI must be fully usable on it.

Job state machine: `queued → preprocessing → running(stage) → exporting → completed | failed | cancelled`. Persist stage, progress 0–100, timestamps, error, and log tail.

# PIPELINE SPECS

## Common ingest (all types)
- Validate extension/MIME and probe with ffprobe. Limits (all configurable in `config.py`): video ≤ 180 s, downscale to max 1920x1080, max upload size configurable, max frames per type (Photo 300, 3DGS 300, default; a "Pro-like" env switch raises Photo to 500).
- Frame extraction (video): ffmpeg sample at adaptive FPS to hit the target frame count; score sharpness (variance of Laplacian) and keep the sharpest frame per time window; drop near-duplicates; report how many frames were kept and why. Also accept a ZIP of photos instead of video.
- Reject/flag too-few frames, extreme blur, or too-little parallax with a clear user-facing message.

## 1) PHOTO SCAN (photogrammetry)
1. Frames → COLMAP `feature_extractor` (SIMPLE_RADIAL or OPENCV camera model, single camera for video) → matcher (`sequential_matcher` for video, `exhaustive_matcher` for ≤ ~200 photos, vocab-tree beyond that) → `mapper` (or GLOMAP if enabled) → pick the largest reconstructed model; fail clearly if < 60% of frames registered.
2. `image_undistorter` → OpenMVS `InterfaceCOLMAP` → `DensifyPointCloud` → `ReconstructMesh` → `RefineMesh` (optional, off on draft) → `TextureMesh` (UV-atlas textured mesh). Verify exact flags with `--help`.
3. Post-process (Open3D/trimesh): remove small disconnected components, fill small holes, orient upright and center, optional metric scale hint, decimate to chosen poly target (Low 50k / Medium 200k / High 1M faces / Ultra = no decimation), resize texture to 1K/2K/4K/8K.
4. Canonical output: textured OBJ+MTL+PNG and GLB → hand to the Exporter.
Quality presets (Draft/Standard/High) must map to concrete COLMAP max image size, OpenMVS resolution level, and refine on/off. Document the table in `docs/PIPELINES.md`.

## 2) 3DGS SCAN
1. Same ingest + COLMAP poses (reuse the Photo SfM stages, don't duplicate code). Use nerfstudio's data format (`ns-process-data`) or convert COLMAP output; verify which is more robust.
2. Train with `ns-train splatfacto` (High preset = `splatfacto-big` or more steps; Draft = fewer steps). Expose steps as a preset parameter. Parse training logs for progress.
3. Export with `ns-export gaussian-splat` → `.ply` (the canonical splat). Then convert to `.splat` (compact web format; write a small converter) and `.spz` (use the official library if installable; otherwise mark as optional).
4. Optional MESH-INCLUSIVE mode (`include_mesh=true`): nerfstudio cannot export a mesh, so implement a `SplatMesher` interface with this default: train a surface-accurate variant (2D Gaussian Splatting) or render depth from the splat, TSDF-fuse with Open3D (unbounded mode for scenes, bounded for objects), clean the mesh, then texture it by running OpenMVS `TextureMesh` with the COLMAP cameras and the extracted mesh (fallback: vertex colors). IMPORTANT: record the license of each component in `docs/LICENSES.md` (original Inria 3DGS code and derivatives such as 2DGS are non-commercial; gsplat/nerfstudio are Apache-2.0; OpenMVS is AGPL-3.0). Mark this feature "experimental" in the UI. Build it last.
5. Splat cleanup step: remove floaters (opacity/scale outlier filtering), optional crop box.

## 3) LIDAR SCAN (RGB-D)
A plain video contains no depth, so be explicit with the user. Accepted inputs:
- Record3D `.r3d` file (it is a zip: RGB frames, depth maps, camera poses, intrinsics; the depth files are typically lzfse-compressed float32 — inspect real files and write the parser against what you actually find, add a clear error if a recording has no valid poses, e.g. front-camera recordings).
- Generic RGB-D ZIP with a documented manifest (`rgb/*.jpg`, `depth/*.png` 16-bit mm or `.npy`/`.exr` float meters, `poses.json` camera-to-world 4x4, `intrinsics.json`). Document it in `docs/LIDAR_INPUT_FORMAT.md` and provide a sample.
- Optional: an existing point cloud (`.ply`/`.xyz`) → just clean + mesh.
Pipeline: parse → keyframe selection (distance/rotation thresholds) → depth filtering (confidence mask if present, range clamp, bilateral/median) → Open3D `ScalableTSDFVolume` integration with color → extract triangle mesh → remove small components, smooth lightly, decimate → texture: vertex colors by default; optional UV bake with xatlas + color projection from the best keyframe per face → also emit a colored point cloud.
Optional fallback "Estimated depth (not true LiDAR)" for plain video: SfM poses (COLMAP) + a monocular depth model, scale-aligned to the sparse points, then the same TSDF path. Label it clearly in the UI and results as non-LiDAR. Build last, behind a feature flag.

# EXPORT LAYER
One `Exporter` that converts the canonical result into any selected formats; the user can select several at once and gets each as a separate download plus an "all as ZIP" option.
Capability matrix (served by `GET /api/capabilities` so the UI never hard-codes it):
- Mesh formats (Photo, LiDAR, and 3DGS-with-mesh): GLB, GLTF, OBJ (+MTL+textures zipped), FBX, USDZ, STL (geometry only, warn about no color), PLY, XYZ (colored points).
- Splat formats (3DGS): PLY (splat), SPZ, .splat.
- Point cloud (LiDAR): PLY, XYZ.
Implementation: GLB/GLTF/OBJ/PLY/STL/XYZ via trimesh/pygltflib/Open3D; FBX and USDZ through headless Blender (separate process, scripted; check version-specific exporter flags) or an equivalent you verify. Each exporter must be validated: re-load the output and check vertex/face counts and that the texture is attached. Unsupported combos return a clear error, and the UI disables them.
Also expose export options: poly target, texture size, up-axis (Y-up/Z-up), units (m/cm/mm).

# API (write the OpenAPI contract first, in `docs/API.md`)
- `POST /api/jobs` multipart: `file` (video/zip/.r3d), `scan_type` (photo|gaussian_splat|lidar), `quality` (draft|standard|high), `output_formats[]`, `options` (JSON: include_mesh, poly_target, texture_size, up_axis, units, mask_background) → `202 {job_id}`
- `GET /api/jobs` list, `GET /api/jobs/{id}` detail
- `GET /api/jobs/{id}/events` SSE (stage, progress, log lines)
- `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}`
- `GET /api/jobs/{id}/artifacts`, `GET /api/jobs/{id}/download/{format}`, `GET /api/jobs/{id}/download-all`
- `GET /api/capabilities` (scan types, quality presets, format matrix, limits, engine mode, GPU present?), `GET /api/health`
Data models: `Job`, `Artifact(kind: mesh|splat|pointcloud|preview|log)`, `JobEvent`.
Security basics: stream uploads to disk with a size cap, sanitize filenames, never shell-interpolate user input, safe zip extraction (no path traversal, zip-bomb limits), CORS limited to the frontend origin, auto-delete jobs after N days (configurable).

# FRONTEND (keep it simple and clean)
Three screens:
1. NEW SCAN: drag-and-drop upload (shows file name, size, duration/resolution after probing); radio cards for scan type (Photo / 3DGS / LiDAR) each with a one-line description and the accepted input type (LiDAR card shows the RGB-D requirement); quality segmented control; multi-select checkboxes for output formats, filtered and disabled according to `/api/capabilities` and the chosen scan type; collapsible Advanced (poly target, texture size, axis, units, include mesh for 3DGS); Submit button with upload progress.
2. JOBS: list with status badge, stage, progress bar, created time; auto-updates.
3. JOB DETAIL: live stage timeline + log panel via SSE; cancel button; on completion a 3D preview (mesh viewer or splat viewer, orbit controls), per-format download buttons, "download all (ZIP)", and the settings used.
Requirements: responsive, dark/light aware, accessible form labels, clear error states (failed stage + last log lines), empty states, no placeholder data. Typed API client generated from or matching the OpenAPI contract.

# FILE STRUCTURE (create exactly this, adjust only with justification in the plan)
```
scanforge/
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── Makefile
├── docs/
│   ├── ARCHITECTURE.md  API.md  PIPELINES.md  LIDAR_INPUT_FORMAT.md
│   ├── LICENSES.md  VERSIONS.md  TROUBLESHOOTING.md
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── app/
│       ├── main.py  config.py  deps.py
│       ├── api/        (jobs.py, capabilities.py, health.py, sse.py)
│       ├── models/     (job.py, artifact.py, schemas.py)
│       ├── db/         (session.py, migrations/)
│       ├── services/   (storage.py, job_service.py, upload_service.py, cleanup.py)
│       ├── queue/      (worker.py, tasks.py)
│       ├── pipelines/
│       │   ├── base.py  registry.py  tool_runner.py  mock.py
│       │   ├── common/     (ingest.py, frame_extraction.py, sfm_colmap.py, postprocess.py)
│       │   ├── photo/      (openmvs.py, pipeline.py)
│       │   ├── gaussian/   (train_splatfacto.py, export_splat.py, splat_cleanup.py, mesher.py, pipeline.py)
│       │   └── lidar/      (r3d_parser.py, rgbd_zip_parser.py, tsdf.py, depth_estimation.py, pipeline.py)
│       ├── export/         (exporter.py, gltf.py, obj.py, ply.py, stl.py, xyz.py,
│       │                    splat_formats.py, blender_convert.py, scripts/blender_export.py)
│       └── utils/          (zip_safe.py, ffprobe.py, logging.py)
│   └── tests/              (unit/, integration/, fixtures/)
├── frontend/
│   ├── package.json  vite.config.ts  tailwind.config.ts  Dockerfile  nginx.conf
│   └── src/
│       ├── main.tsx  App.tsx
│       ├── api/            (client.ts, types.ts, useJobEvents.ts)
│       ├── pages/          (NewScan.tsx, Jobs.tsx, JobDetail.tsx)
│       ├── components/     (UploadDropzone, ScanTypeCards, QualitySelect, FormatPicker,
│       │                    StageTimeline, LogPanel, MeshViewer, SplatViewer, StatusBadge)
│       └── lib/            (formatMatrix.ts, format.ts)
├── docker/
│   └── worker-gpu.Dockerfile    (CUDA base; builds COLMAP, OpenMVS; installs nerfstudio, Blender)
├── scripts/
│   ├── doctor.py            (checks GPU, CUDA, ffmpeg, colmap, OpenMVS binaries, nerfstudio, Blender; prints fix hints)
│   ├── make_sample_data.py  (synthetic photo set + synthetic RGB-D capture with known poses)
│   └── download_samples.sh
└── data/  (gitignored: uploads/, jobs/, exports/)
```

# TESTING & VERIFICATION
- Unit tests: frame extraction + sharpness selection, zip safety, `.r3d`/RGB-D parsers, TSDF on a synthetic scene (render depth of a known shape from known poses; assert the recovered mesh is within tolerance), each exporter's round-trip load, capability-matrix consistency between backend and frontend.
- Integration: full pipeline in MOCK mode (CI-friendly); real smoke tests per scan type on small public sample data (for example a nerfstudio sample capture via `ns-download-data`) marked `@gpu`.
- Frontend: component tests for FormatPicker filtering and an end-to-end test (Playwright) that uploads a sample, watches progress, and downloads two formats.
- Use the Antigravity browser to actually exercise the UI and attach screenshots to the walkthrough.

# MILESTONES (stop and report after each; do not skip ahead)
- P0: repo skeleton, Docker Compose, `doctor.py`, AGENTS.md, API contract. Done = `docker compose up` serves UI + health.
- P1: job system + upload + SSE + full frontend working end-to-end on MOCK engine, all three scan types and format selection. Done = I can upload, watch progress, preview, download.
- P2: real PHOTO pipeline + exporters (GLB/OBJ/PLY/STL/XYZ first, then FBX/USDZ via Blender).
- P3: real 3DGS pipeline (PLY, .splat, SPZ) + splat viewer.
- P4: real LIDAR pipeline (.r3d + RGB-D zip) + synthetic-data tests.
- P5: hardening (cancel, resume, cleanup, error messages), docs, and stretch items: mesh-inclusive 3DGS, quad retopology, background masking, PBR map generation, estimated-depth fallback, auth.

# DEFINITION OF DONE
`docker compose up` → open the UI → upload a video → choose scan type + several output formats → see live progress → preview the result → download each selected format, each of which opens correctly in Blender (or a splat viewer for splat formats). README has exact setup steps for GPU and no-GPU (mock) modes. `docs/LICENSES.md` and `docs/VERSIONS.md` are accurate. The final report lists exactly what was verified on real hardware vs. only in mock mode.
# PRIORITY OVERRIDE (supersedes earlier build order, milestones, and "experimental" labels)

## New priority order
1. MESH quality for interiors (highest). Mesh is now the primary deliverable, not a side output.
2. 3DGS, including mesh-inclusive mode as a CORE feature (no longer "experimental").
3. LiDAR / RGB-D (lowest). Build last, behind a feature flag (`ENABLE_LIDAR=false` by default). Keep the scan-type card in the UI but mark it "Beta, needs RGB-D capture".

## What "mesh high priority" means concretely
- Two mesh routes for interiors, both built early and compared in `docs/PIPELINES.md` on the same test capture:
  A. Photogrammetry route: COLMAP → OpenMVS (Densify → ReconstructMesh → optional Refine → Texture).
  B. Depth-fusion route: per-frame depth (rendered from the trained splat, or from a monocular depth model aligned to the sparse SfM points) → Open3D TSDF fusion (unbounded/room-scale mode) → mesh.
  Let the user pick "Auto / Photogrammetry / Depth fusion" under Advanced; Auto chooses by a simple heuristic (for example, share of textureless pixels, number of registered frames) and records the reason.
- Mesh post-processing is mandatory, not optional: component cleanup, plane-aware hole filling and wall/floor regularization (RANSAC planes), ghost-surface removal behind windows and mirrors, floor leveling, planarity-aware decimation, UV unwrap (xatlas) and texture baking at 1K/2K/4K/8K.
- Mesh exports are the first exporters finished and the most thoroughly validated: GLB, GLTF, OBJ(+MTL+textures), FBX, USDZ, STL, PLY, XYZ. Add automated checks: watertightness/hole count report, face count vs. target, texture attached, up-axis and units correct, and a per-mesh quality report (JSON) shown on the results page.
- The viewer's mesh mode gets the most polish: wireframe toggle, textured/untextured/normals views, first-person walk mode, and measurement tool (two-point distance, also used for scale calibration).
- Mesh-inclusive 3DGS: one job produces both the splat and a cleaned, textured mesh (core feature). Use depth/normal-regularized training or 2DGS + TSDF within the 8 GB VRAM budget, with the OOM-retry logic. Gaussian Opacity Fields is the only part that stays optional because of memory use. Keep the license notes in `docs/LICENSES.md`.

## New milestones (replace P0–P5)
- P0: repo skeleton, Docker Compose, doctor.py, AGENTS.md, API contract. 
- P1: job system + upload + SSE + full frontend on MOCK engine (all scan types and the format picker visible; LiDAR card shows "Beta"). Mock mode must produce a sample interior mesh and splat.
- P2: shared interior-tuned SfM + Route A (photogrammetry mesh) end to end, with mesh post-processing, scale calibration, floor alignment and the mesh exporters (GLB/OBJ/PLY/STL/XYZ first, then FBX/USDZ via Blender) plus the mesh viewer.
- P3: 3DGS training + floater cleanup + splat formats (PLY, .splat, SPZ) + splat viewer.
- P4: Route B (depth-fusion mesh) and mesh-inclusive 3DGS; compare against Route A on the same capture and wire up the Auto heuristic; floor plan and room-dimension outputs.
- P5: hardening (cancel, resume, cleanup, error messages), docs, tests.
- P6 (last, feature-flagged): LiDAR / RGB-D pipeline (.r3d + RGB-D zip), synthetic-data tests, estimated-depth fallback.

## Definition-of-done change
The main acceptance test is now: upload a room walk-through video → get a clean, textured, correctly scaled interior mesh in several selected formats that opens correctly in Blender, plus the splat. LiDAR is not required for "done"; it is a documented follow-up if P6 isn't reached.
# CLARIFICATIONS AND ADDITIONS (final authority; wins over anything above)

## Conflict resolution
If any earlier text conflicts with the PRIORITY OVERRIDE section or this section, follow these. Priority is: Mesh quality > 3DGS (with mesh as a core feature) > LiDAR (last, feature-flagged). Ignore any remaining "experimental", "build last" or old milestone wording for mesh-inclusive 3DGS.

## How the mesh routes map to scan types
- Scan types in the UI stay: Photo, 3DGS, LiDAR (Beta).
- PHOTO scan = interior mesh job. Advanced option `mesh_route`: auto | photogrammetry | depth_fusion.
  - photogrammetry = Route A (COLMAP → OpenMVS).
  - depth_fusion = Route B using a monocular depth model aligned to the sparse SfM points, then Open3D TSDF (no splat training).
  - auto = heuristic choice, with the reason stored in the job and shown on the results page.
- 3DGS scan with `include_mesh=true`: splat + mesh in one job; the mesh comes from depth rendered out of the trained splat (or 2DGS) + TSDF fusion, textured with OpenMVS TextureMesh or vertex colors.
- Both meshing routes feed the same shared mesh post-processing and the same exporters.

## Additional files (add to the file structure)

## Additional API
- `POST /api/jobs/{id}/calibrate` body: two 3D points + real distance in meters → re-runs only the scale/align/export stages (stages are cached, so SfM and meshing are not repeated).
- `GET /api/jobs/{id}/report` → mesh quality report JSON + room dimensions JSON.
- Add `mesh_route`, `voxel_size`, `crop_box` to the job `options`.

## Mock mode
Mock mode must generate its sample interior procedurally (a simple room mesh with a texture, plus a matching small synthetic splat) so no binary asset has to be sourced.

## Delivery order
Plan first. Then deliver P0 to P2 and stop for my review on a real room video before starting P3.