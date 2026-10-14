# ScanForge Software Version Pins (docs/VERSIONS.md)

Pinned versions for all ScanForge external tools, Docker base images, Python packages, and frontend libraries.

---

## 1. System & Docker Images

| Tool / Layer | Version / Tag | Architecture |
|---|---|---|
| Ubuntu Base | `ubuntu:22.04` | x86_64 |
| CUDA Devel | `nvidia/cuda:12.1.1-devel-ubuntu22.04` | Ada Lovelace (sm_89) |
| CUDA Runtime | `nvidia/cuda:12.1.1-runtime-ubuntu22.04`| Ada Lovelace (sm_89) |
| Python | `3.11.17` | x86_64 |
| Node.js | `20.12.2-alpine` | x86_64 |
| Redis | `7.4-alpine` | x86_64 |
| Nginx | `1.27-alpine` | x86_64 |

---

## 2. External Tools & Reconstruction Engines

| Component | Pinned Version | Verification Command |
|---|---|---|
| COLMAP | `3.9.1` (CUDA sm_89) | `colmap --help` |
| OpenMVS | `v2.2.0` (CUDA sm_89) | `InterfaceCOLMAP --help` |
| VCGLib | `cdcseacave/VCG` | OpenMVS geometry library dependency |
| FFmpeg | `4.4.2` | `ffmpeg -version` |
| Blender | `4.1.0` | `blender --version` |

---

## 3. Python Packages

| Package | Pinned Version | Note |
|---|---|---|
| `torch` | `2.5.1+cu121` | PyTorch with CUDA 12.1 runtime |
| `torchvision` | `0.20.1+cu121` | Vision models & transforms |
| `fastapi` | `0.143.0` | Backend REST API |
| `pydantic` | `2.14.1` | Data validation (Pydantic v2) |
| `sqlmodel` | `0.0.48` | Database ORM |
| `rq` | `2.12.0` | Job queue |
| `sse-starlette` | `3.5.0` | Real-time SSE streaming |
| `open3d` | `0.20.0` | Mesh processing / RANSAC / TSDF |
| `trimesh` | `5.1.1` | 3D format conversion & analysis |
| `gsplat` | `1.0.0` | 3D Gaussian Splatting rasterizer (planned P3) |
| `nerfstudio` | `1.1.0` | splatfacto model training (planned P3) |

---

## 4. Frontend Libraries

| Package | Pinned Version | Note |
|---|---|---|
| `react` | `18.3.1` | UI Library |
| `vite` | `5.2.11` | Bundler & dev server |
| `three` | `0.164.1` | WebGL 3D rendering |
| `@react-three/fiber` | `8.16.6` | React Three renderer |
| `@react-three/drei` | `9.105.6` | 3D utilities and controls |
| `@mkkellogg/gaussian-splats-3d` | `0.4.5` | Gaussian Splat WebGL viewer |
| `tailwindcss` | `3.4.3` | Utility styling |
| `lucide-react` | `0.378.0` | Clean minimalist UI icons |
