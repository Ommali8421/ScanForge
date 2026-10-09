# ScanForge Component Licensing & Compliance Audit (docs/LICENSES.md)

> **Important**: In accordance with ScanForge Agent Conventions, all licenses below are designated **UNVERIFIED** until the actual repository `LICENSE` file is confirmed directly.

---

## 1. Third-Party Component Audit

| Component | Repository / Source | Claimed License | Status | Compliance Notes |
|---|---|---|---|---|
| **COLMAP** | `colmap/colmap` | BSD-2-Clause / BSD-3-Clause | UNVERIFIED | Permissive for commercial and non-commercial usage. |
| **OpenMVS** | `cdcseacave/openMVS` | AGPL-3.0 | UNVERIFIED | **AGPL-AFFECTED**: Containerization does NOT isolate network-triggered AGPL obligations. Must be evaluated before any hosted, SaaS, or commercial offering. |
| **nerfstudio** | `nerfstudio-project/nerfstudio` | Apache-2.0 | UNVERIFIED | Permissive; evaluate sub-dependencies (e.g. CUDA kernels). |
| **gsplat** | `nerfstudio-project/gsplat` | Apache-2.0 | UNVERIFIED | Permissive CUDA rasterizer. |
| **Depth Anything V2 Small** | `DepthAnything/Depth-Anything-V2` | Apache-2.0 | UNVERIFIED | Permissive. **Note**: Base/Large/Giant models are CC-BY-NC-4.0 and strictly prohibited from ScanForge. |
| **Open3D** | `isl-org/Open3D` | MIT | UNVERIFIED | Permissive 3D geometry library. |
| **Trimesh** | `mikedh/trimesh` | MIT | UNVERIFIED | Permissive mesh processing. |
| **FastAPI** | `tiangolo/fastapi` | MIT | UNVERIFIED | Permissive backend framework. |
| **@mkkellogg/gaussian-splats-3d**| npm / GitHub | MIT | UNVERIFIED | Permissive client-side WebGL/Three.js splat viewer. |
| **Blender (Headless)** | `blender/blender` | GPL-2.0+ / GPL-3.0 | UNVERIFIED | External CLI subprocess for DCC conversions (FBX/USDZ). |

---

## 2. Policy for Commercial Use

1. **OpenMVS**: Any hosted deployment exposing OpenMVS functionality over an API triggers AGPL-3.0 source disclosure requirements for the complete network solution unless a proprietary license is acquired or an alternative MVS engine is substituted.
2. **Depth Models**: Only Depth Anything V2 Small may be downloaded or loaded. Base, Large, and Giant weights are excluded by policy.
3. **Inria 3DGS Original Code**: Inria's original reference code carries a Non-Commercial research clause. ScanForge uses the Apache-2.0 `gsplat` / `splatfacto` implementation rather than Inria reference code.
