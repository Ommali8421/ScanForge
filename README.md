# ScanForge

> Self-hostable 3D-scanning web application turning room walk-through videos and RGB-D captures into clean, textured interior meshes and 3D Gaussian Splats.

---

## Features

- **Three Scan Modes**:
  - **Photo Scan**: High-fidelity interior photogrammetry pipeline (COLMAP + OpenMVS) and depth-fusion pipeline.
  - **3DGS Scan**: Fast, photorealistic 3D Gaussian Splatting (`splatfacto` / `gsplat`) with mesh extraction.
  - **LiDAR Scan (Beta)**: Direct RGB-D / `.r3d` TSDF integration for metric-accurate rooms.
- **Interior-Tuned Reconstruction**:
  - Dominant plane extraction (floors, walls, ceilings) via RANSAC.
  - Automated floor leveling and upright orientation alignment.
  - Interactive two-point scale calibration and metric room measurements.
- **Pluggable Architecture**:
  - **Mock Mode**: Lightweight procedural room mesh & synthetic splat generator for rapid local development without GPU requirements.
  - **GPU Mode**: Optimized 8 GB VRAM execution (Ada Lovelace RTX 4060 compatible) with resolution scaling and automated OOM recovery.
- **Export Formats**:
  - Meshes: GLB, OBJ + MTL + PNG, PLY, STL, XYZ.
  - Splats: PLY (Gaussian splat), `.splat`.
  - DCC / CAD: FBX, USDZ (via Blender).

---

## Quick Start

### 1. Prerequisites
- Docker Engine & Docker Compose (v2.20+)
- For GPU Mode: NVIDIA Container Toolkit + NVIDIA Drivers (RTX 4060 or compatible)

### 2. Environment Setup
Copy the sample environment file:
```bash
cp .env.example .env
```

### 3. Run with Mock Engine (No GPU Required)
Mock mode simulates processing with procedural interior geometry and synthetic splats:
```bash
docker compose up -d --build
```
- Web UI: [http://localhost:3000](http://localhost:3000)
- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 4. Run with GPU Engine (NVIDIA RTX 4060 / CUDA)
Set `SCANFORGE_ENGINE=real` in `.env`, then launch:
```bash
docker compose --profile gpu up -d --build
```

Run the system diagnostics tool to verify GPU, CUDA, and tooling dependencies:
```bash
python scripts/doctor.py
# Or inside the GPU worker container:
docker compose --profile gpu exec worker-gpu python scripts/doctor.py
```

---

## Project Structure

```
scanforge/
├── AGENTS.md               # Development conventions & agent instructions
├── README.md               # Project guide and quickstart
├── docker-compose.yml      # Service orchestration (mock and gpu profiles)
├── .env.example            # Environment configuration template
├── Makefile                # Operational shortcuts
├── docs/                   # Authoritative specifications and documentation
│   ├── SPEC.md             # Authoritative technical specification
│   ├── API.md              # OpenAPI contract specification
│   ├── ARCHITECTURE.md     # System architecture & data flow diagrams
│   ├── PIPELINES.md        # Pipeline definitions & quality presets
│   ├── MESH_ROUTES_COMPARISON.md # Route A vs Route B analysis
│   ├── LIDAR_INPUT_FORMAT.md # RGB-D input specification
│   ├── LICENSES.md         # Component license audits
│   ├── VERSIONS.md         # Pinned software versions
│   └── TROUBLESHOOTING.md  # Common troubleshooting workflows
├── backend/                # FastAPI backend & reconstruction pipelines
│   ├── Dockerfile          # Mock / API container
│   └── app/
├── frontend/               # React + TypeScript + Tailwind web application
│   ├── Dockerfile
│   └── src/
├── docker/                 # Nginx proxy and GPU worker Dockerfiles
└── scripts/                # Diagnostic and utility scripts
```

---

## License & Compliance

All third-party dependencies and licensing terms are detailed in [docs/LICENSES.md](docs/LICENSES.md). Note that OpenMVS is AGPL-3.0; verify licensing obligations before commercial deployment.
