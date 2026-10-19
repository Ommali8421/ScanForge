# ScanForge Reconstruction Pipelines (docs/PIPELINES.md)

Detailed specifications for ScanForge reconstruction stages, quality presets, and VRAM management.

---

## 1. Quality Presets (Photo Scan — Route A)

| Preset | Max Image Size (px) | OpenMVS Resolution Level | RefineMesh | Texture Size | Target Polycount |
|---|---|---|---|---|---|
| **Draft** | 1200 | Level 2 | Off | 1024 × 1024 | ~50,000 |
| **Standard** | 1600 | Level 2 | Off | 4096 × 4096 | ~200,000 |
| **High** | 2000 | Level 1 | On | 8192 × 8192 | ~1,000,000 |

### 8 GB VRAM Rules
- Concurrency limit is **strictly 1 GPU job at a time**.
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

