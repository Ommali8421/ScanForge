# Mesh Reconstruction Routes Comparison (docs/MESH_ROUTES_COMPARISON.md)

Detailed comparison of ScanForge Route A (Photogrammetry) and Route B (Depth Fusion) for interior spaces.

---

## 1. Comparison Matrix

| Attribute | Route A: Photogrammetry (COLMAP + OpenMVS) | Route B: Depth Fusion (SfM + Monocular Depth + TSDF) |
|---|---|---|
| **Primary Engines** | COLMAP sequential matcher + OpenMVS | COLMAP SfM + Depth Anything V2 Small + Open3D TSDF |
| **Blank Wall Handling** | May develop holes on textureless drywall; mitigated by Planar RANSAC stage | Smooth, continuous planar surfaces derived from monocular depth priors |
| **Edge & Detail Sharpness** | High sharpness on textured objects and corners | Softer corners due to TSDF voxel discretization (1–2 cm voxels) |
| **VRAM Consumption** | Moderate to High (scaled via OpenMVS resolution levels) | Very Low (Depth Anything V2 Small fits comfortably in ~2 GB VRAM) |
| **Processing Speed** | 10–25 minutes for standard 2-minute video | 4–8 minutes |
| **Recommended Use Case** | Detailed furniture, ornate rooms, high texture density | Plain modern apartments, white drywall rooms, rapid draft models |

---

## 2. Auto-Selection Heuristic

When the user selects `mesh_route: "auto"`:
1. Sample 20 extracted keyframes.
2. Calculate average gradient magnitude (Laplacian variance) across images to gauge texture density.
3. If texture variance is below threshold ($\tau < 120.0$), Route B (Depth Fusion) is selected to prevent hole formation on plain surfaces.
4. Otherwise, Route A (Photogrammetry) is selected for maximum geometric fidelity.
5. The chosen route and reasoning are recorded in the job report JSON.
