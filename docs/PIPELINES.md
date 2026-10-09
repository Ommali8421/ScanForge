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
