# ScanForge Reconstruction Pipelines (docs/PIPELINES.md)

Detailed specifications for ScanForge reconstruction stages, quality presets, and VRAM management.

---

## 1. Quality Presets & Dynamic VRAM Tiers (Photo Scan — Route A)

ScanForge dynamically tunes reconstruction parameters based on detected GPU VRAM memory.

### VRAM Detection Precedence
1. **Explicit Override**: `SCANFORGE_VRAM_GB` environment variable (e.g. `SCANFORGE_VRAM_GB=8.0`).
2. **Auto-Discovery**: Queries `nvidia-smi` for the first device in `CUDA_VISIBLE_DEVICES` (or GPU 0), and applies a **0.5 GB safety margin** for OS, display, and driver overhead.
3. **Fallback Baseline**: Assumes 8.0 GB baseline if unparseable or running in mock mode.

### VRAM Tier Table

| VRAM Tier | Effective VRAM | Preset | COLMAP Max Size | OpenMVS Res Level | RefineMesh | Target Faces | Max Splat Gaussians |
|---|---|---|---|---|---|---|---|
| **High Tier** | $\ge 11.5\text{ GB}$ (12+ GB raw) | Draft<br>Standard<br>High | 1600 px<br>2400 px<br>3200 px | Level 2<br>Level 1<br>Level 1 | Off<br>Off<br>On | 100k<br>250k<br>500k | 1.0M<br>1.5M<br>2.5M |
| **8 GB Baseline**<br>*(RTX 4060 Target)* | $6.5\text{ -- }11.4\text{ GB}$ (~7.5 GB effective) | Draft<br>Standard<br>**High** | 1200 px<br>1600 px<br>**2000 px (Capped)** | Level 2<br>Level 2<br>**Level 1** | Off<br>Off<br>On | 100k<br>200k<br>350k | 800k<br>1.2M<br>1.5M |
| **Constrained Tier** | $< 6.5\text{ GB}$ (4–6 GB raw) | Draft<br>Standard<br>High | 1000 px<br>1200 px<br>1600 px | Level 3<br>Level 2<br>Level 2 | Off<br>Off<br>Off | 50k<br>100k<br>150k | 500k<br>800k<br>1.0M |

### 8 GB VRAM Budget Rules
- Concurrency limit is **strictly 1 GPU job at a time**.
- COLMAP feature extraction and mapper image sizes are capped at **$\le 2000\text{ px}$** in the 8 GB tier.
- Subprocesses exit between pipeline stages to guarantee full CUDA memory deallocation.
- In case of OpenMVS CUDA out-of-memory errors, an automated retry mechanism falls back to `resolution-level + 1`.


---

## 2. Texturing Execution Order

> **Amendment 2 Compliance**: Texturing is executed on the **final cleaned and decimated mesh** with COLMAP camera projections (`OpenMVS TextureMesh`).
> For Route B depth fusion and splat-extracted meshes, fallback UV mapping and camera projection is performed via `xatlas`.

Pipeline stage sequence:
1. `IngestStage` (Validate file format & metadata)
2. `FrameExtractionStage` (Adaptive FPS, sharpness scoring)
3. `ColmapSfMStage` (Sequential matching + vocab tree loop closure)
4. `OpenMVSDenseStage` (Densify point cloud)
5. `OpenMVSMeshStage` (Reconstruct mesh geometry)
6. `MeshCleanupStage` (Component filtering, isolated islands removal)
7. `PlaneRepairStage` (Planar RANSAC hole filling)
8. `FloorAlignStage` (Level floor to Y=0)
9. `ScaleStage` (Apply metric scaling)
10. `DecimateStage` (Planarity-preserving quadric decimation)
11. `UVTextureBakeStage` (**Final stage**: OpenMVS TextureMesh / xatlas UV projection)
12. `ExportStage` (GLB, OBJ, PLY, STL, XYZ, FBX/USDZ)

---

## 3. Scale Calibration Workflow

- When `/api/jobs/{id}/calibrate` is called with two mesh points and a true physical distance, the system computes:
  $$\text{scale\_factor} = \frac{\text{real\_distance}}{\|\mathbf{p}_a - \mathbf{p}_b\|}$$
  $$\text{cumulative\_scale} = \text{current\_scale} \times \text{scale\_factor}$$
- The job is re-enqueued starting from `ScaleStage`. Upstream stages (1 through 8) are cached and skipped instantly.

---

## 4. COLMAP Version Adaptation & Hang Protection

ScanForge supports both COLMAP 3.9.x (baseline container image) and COLMAP 3.13.x+ dynamically via `colmap_compat.py`.

### Option Renaming Map
- **Feature Extraction**:
  * 3.9.x: `--SiftExtraction.use_gpu`, `--SiftExtraction.num_threads`
  * 3.13+: `--FeatureExtraction.use_gpu`, `--FeatureExtraction.num_threads`
  * Both: `--SiftExtraction.max_image_size` (unchanged)
- **Feature Matching**:
  * 3.9.x: `--SiftMatching.use_gpu`, `--SiftMatching.num_threads`, `--SiftMatching.guided_matching`, `--SiftMatching.max_num_matches`
  * 3.13+: `--FeatureMatching.use_gpu`, `--FeatureMatching.num_threads`, `--FeatureMatching.guided_matching`, `--FeatureMatching.max_num_matches`
  * 3.13+ Matcher-Specific Threads: sets **both** `--FeatureMatching.num_threads` and `--SequentialMatching.num_threads` / `--VocabTreeMatching.num_threads`.

### Hang Protection & Ceres Quality
- **COLMAP 3.13+**: Protected against infinite bundle adjustment loops via `--Mapper.max_runtime_seconds <timeout>` directly passed to COLMAP.
- **COLMAP 3.9.x**: Protected via `ToolRunner(timeout=<timeout>)` process-level timeout.
- **Ceres Iteration Caps**: Artificial low iteration caps (e.g. 30/20 iterations) are avoided to maintain full interior reconstruction quality. Default COLMAP convergence criteria (50 global / 25 local iterations) run unimpeded under runtime timeout enforcement.

### Loop Detection
- **COLMAP 3.13+**: Automatically downloads the FAISS vocabulary tree (`vocab_tree_faiss_flickr100K_words256K.bin`) when network access is available.
- **COLMAP 3.9.x**: Requires a local vocabulary tree file (configured via `SCANFORGE_VOCAB_TREE_PATH` or job options). If unavailable, falls back gracefully to sequential matching without loop detection with a warning logged.

### Optional GPU Bundle Adjustment (`--Mapper.ba_use_gpu`)
- COLMAP 3.13 introduces the `--Mapper.ba_use_gpu` flag for Ceres GPU bundle adjustment.
- **Default Status**: **Disabled** by default in ScanForge to strictly stay within the 8 GB VRAM budget on consumer GPUs (RTX 4060) and avoid memory thrashing during mapper point triangulation.
- **Server Testing Note**: Configured as an optional toggle in `build_mapper_args(ba_use_gpu=True)` for future evaluation on multi-GPU or high-VRAM server instances (>= 16 GB VRAM).

---

## 5. Route B (Depth Fusion) & Mesh-Inclusive 3DGS Architecture

### Route B: Monocular Depth + TSDF Fusion
Designed for low-texture indoor spaces (apartments, plain drywall, hallways) where photogrammetry produces surface tearing:
1. **Model**: Depth Anything V2 Small (~95 MB, `depth_anything_v2_vits.pth`, strictly Apache-2.0, loaded offline from `/data/models/`).
2. **3-Pass Depth Alignment (`depth_align.py`)**:
   - *Pass 1*: RANSAC inverse-depth fitting against sparse COLMAP SfM points ($s_i \cdot \text{disp} + t_i \approx 1/z$).
   - *Pass 2*: Bidirectional zero-phase EMA temporal smoothing ($\alpha = 0.35$) eliminates inter-frame depth flickering and mid-air "curtain" artifacts.
   - *Pass 3*: Sobel edge discontinuity masking ($|\nabla z| / z > 0.08 \to 0$) removes flying occlusion pixels, followed by bilateral smoothing.
3. **Open3D TSDF Fusion (`tsdf_fusion.py`)**:
   - Scale-invariant voxel sizing: $D_{\text{room}} / 380$ (standard), $\text{sdf\_trunc} = \max(8.0 \times \text{voxel\_size}, 0.05\text{m})$.
   - Open3D native C++ Taubin smoothing (`filter_smooth_taubin(number_of_iterations=10)`).
   - Component cluster pruning dropping floating sheets $< 2,500$ faces or $< 3\%$ of main volume.

### Mesh-Inclusive 3DGS (`splat_mesher.py`)
Single-pass generation of Gaussian Splatting + watertight textured mesh + architectural CAD floor plan:
1. **Expected Depth Verification**: In `gsplat==1.4.0`, `render_mode="RGB+ED"` is confirmed to be alpha-normalized. Low opacity splats ($\alpha < 0.70$) and depth edges ($|\nabla z| / z > 0.08$) are masked to $0.0$.
2. **Kabsch/SVD Camera Transform**: Solves exact rigid transform $(R_{c2r}, t_{c2r})$ from `cleaned_splat` space back to raw COLMAP `sparse/0` poses, asserting $\text{error} < 10^{-3}$ units (achieved $8.09 \times 10^{-5}$). Ensures $100\%$ co-registration during OpenMVS UV texturing (0.0% untextured void).

### Manhattan Yaw & Architectural CAD Floor Plans
1. **Manhattan Histogram Yaw Alignment (`floor_align.py`)**:
   - Folds vertical wall normals ($|n_y| < 0.35$) into $[0, \pi/2)$ with circular wrap-around padding (`np.pad(mode='wrap')`).
   - Rotates by $-\theta_{\text{peak}}$ around the Y-axis, guaranteeing all room walls sit square to $0^\circ, 90^\circ, 180^\circ, 270^\circ$.
2. **Multi-Height Aggregation CAD Floor Plans (`floor_plan.py`)**:
   - Slices 7 horizontal planes across vertical wall band $[Y_{\min} + 0.25 H, Y_{\min} + 0.75 H]$.
   - Rasterizes into $1024 \times 1024$ 2D occupancy grid with morphological closing ($7\times 7$ kernel) closing mesh cracks $< 12\text{cm}$ while preserving open doors.
   - Vectorizes with Douglas-Peucker (`approxPolyDP`) and snaps near-orthogonal segments into crisp architectural CAD blueprints (`floor_plan.svg`, `floor_plan.png`).

