# ScanForge Component Licensing & Compliance Audit (docs/LICENSES.md)

> **Repository Status**: This repository is **PUBLIC** (`https://github.com/Ommali8421/ScanForge.git`).
> **Audit Policy**: Each license below is verified by reading the actual LICENSE file from the upstream repository. Entries that could not be confirmed are marked **UNVERIFIED**.

---

## 1. Third-Party Component Audit

| Component | Repository / Source | Confirmed License | Status | Verification Source | Compliance Notes |
|---|---|---|---|---|---|
| **COLMAP** | `colmap/colmap` | BSD-3-Clause | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/colmap/colmap/blob/main/LICENSE) — "The COLMAP library is licensed under the new BSD license." | Permissive. Note: COLMAP's dependencies (e.g., SuiteSparse, Ceres, FLANN) carry their own licenses; building with them may affect the combined binary license. |
| **OpenMVS** | `cdcseacave/openMVS` | AGPL-3.0 | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/cdcseacave/openMVS/blob/master/LICENSE) — Full text of GNU Affero General Public License v3 | **AGPL-AFFECTED**: Running OpenMVS in an isolated container does NOT resolve AGPL network-use obligations. Any hosted deployment exposing OpenMVS functionality over a network API triggers source disclosure requirements. Must be evaluated before any hosted, SaaS, or commercial offering. |
| **VCGLib** | `cdcseacave/VCG` | GPL-3.0 (claimed) | **UNVERIFIED** | No `LICENSE` file found in `cdcseacave/VCG` fork (404). The upstream VCG library by ISTI-CNR is GPL-3.0, but the specific fork used by OpenMVS does not contain a LICENSE file. | Treat as GPL-3.0 per upstream; confirm with fork maintainer if possible. Copyleft geometry library required by OpenMVS. |
| **nerfstudio** | `nerfstudio-project/nerfstudio` | Apache-2.0 | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/nerfstudio-project/nerfstudio/blob/main/LICENSE) — Full Apache License 2.0 text | Permissive; evaluate sub-dependencies (e.g., CUDA kernels). |
| **gsplat** | `nerfstudio-project/gsplat` | Apache-2.0 | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/nerfstudio-project/gsplat/blob/main/LICENSE) — Full Apache License 2.0 text | Permissive CUDA rasterizer. |
| **Depth Anything V2 Small** | `DepthAnything/Depth-Anything-V2` | Apache-2.0 (code) | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/DepthAnything/Depth-Anything-V2/blob/main/LICENSE) — Full Apache License 2.0 text | Code is Apache-2.0. **Note**: Base/Large/Giant model weights are CC-BY-NC-4.0 and strictly prohibited from ScanForge. Only the Small model weights (Apache-2.0) may be used. |
| **Open3D** | `isl-org/Open3D` | MIT | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/isl-org/Open3D/blob/main/LICENSE) — "The MIT License (MIT), Copyright (c) 2018-2026 www.open3d.org" | Permissive 3D geometry library. |
| **Trimesh** | `mikedh/trimesh` | MIT | **VERIFIED** (2026-10-15) | [`LICENSE.md`](https://github.com/mikedh/trimesh/blob/main/LICENSE.md) — "The MIT License (MIT), Copyright (c) 2023 Michael Dawson-Haggerty" | Permissive mesh processing. |
| **FastAPI** | `tiangolo/fastapi` | MIT | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/tiangolo/fastapi/blob/master/LICENSE) — "The MIT License (MIT), Copyright (c) 2018 Sebastián Ramírez" | Permissive backend framework. |
| **@mkkellogg/gaussian-splats-3d** | `mkkellogg/GaussianSplats3D` | MIT | **VERIFIED** (2026-10-15) | [`LICENSE`](https://github.com/mkkellogg/GaussianSplats3D/blob/main/LICENSE) — "The MIT License (MIT), Copyright (c) 2023 Mark Kellogg" | Permissive client-side WebGL/Three.js splat viewer. |
| **Blender (Headless)** | `blender/blender` | GPL-2.0+ | **VERIFIED** (2026-10-15) | [`COPYING`](https://github.com/blender/blender/blob/main/COPYING) — "Blender uses the GNU General Public License" + `doc/license/GPL-license.txt` | Used as an external CLI subprocess for FBX/USDZ conversions. Subprocess invocation (not linking) generally does not create a derivative work, but consult legal counsel for commercial deployment. |

---

## 2. Policy for Commercial Use

1. **OpenMVS**: Any hosted deployment exposing OpenMVS functionality over an API triggers AGPL-3.0 source disclosure requirements for the complete network solution unless a proprietary license is acquired or an alternative MVS engine is substituted.
2. **Depth Models**: Only Depth Anything V2 Small may be downloaded or loaded. Base, Large, and Giant weights are excluded by policy (CC-BY-NC-4.0).
3. **Inria 3DGS Original Code**: Inria's original reference code carries a Non-Commercial research clause. ScanForge uses the Apache-2.0 `gsplat` / `splatfacto` implementation rather than Inria reference code.
4. **VCGLib**: Treat as GPL-3.0 per upstream ISTI-CNR licensing. The specific cdcseacave/VCG fork's LICENSE file could not be located — verify directly if needed.
