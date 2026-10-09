# ScanForge Software Version Pins (docs/VERSIONS.md)

Pinned versions for all ScanForge external tools, Docker base images, Python packages, and frontend libraries.

---

## 1. System & Docker Images

| Tool / Layer | Version / Tag | Architecture |
|---|---|---|
| Ubuntu Base | `ubuntu:22.04` | x86_64 |
| CUDA Devel | `nvidia/cuda:12.1.1-devel-ubuntu22.04` | Ada Lovelace (sm_89) |
| CUDA Runtime | `nvidia/cuda:12.1.1-runtime-ubuntu22.04`| Ada Lovelace (sm_89) |
| Python | `3.11.8` | x86_64 |
| Node.js | `20.12.2-alpine` | x86_64 |
| Redis | `7.4-alpine` | x86_64 |
| Nginx | `1.27-alpine` | x86_64 |

---

## 2. External Tools & Reconstruction Engines

| Component | Pinned Version | Verification Command |
|---|---|---|
| COLMAP | `3.9.1` | `colmap --help` |
| OpenMVS | `v2.2.0` | `InterfaceCOLMAP --help` |
| FFmpeg | `6.1.1` | `ffmpeg -version` |
| Blender | `4.1` | `blender --version` |

---

## 3. Python Packages

| Package | Pinned Version | Note |
|---|---|---|
| `fastapi` | `0.111.0` | Backend REST API |
| `pydantic` | `2.7.4` | Data validation |
| `sqlmodel` | `0.0.19` | Database ORM |
| `rq` | `1.16.2` | Job queue |
| `sse-starlette` | `2.1.2` | Real-time SSE streaming |
| `open3d` | `0.18.0` | Mesh processing / RANSAC |
| `trimesh` | `4.3.2` | 3D format conversion |
| `gsplat` | `1.0.0` | 3D Gaussian Splatting rasterizer |
| `nerfstudio` | `1.1.0` | splatfacto model training |

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
