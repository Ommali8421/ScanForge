# ScanForge

> Self-hostable 3D-scanning web application turning interior walk-through videos and RGB-D captures into clean, textured interior meshes and 3D Gaussian Splats.

[![License](https://img.shields.io/badge/license-MIT%20%2F%20AGPL--3.0-blue.svg)](docs/LICENSES.md)
[![Hardware](https://img.shields.io/badge/GPU-RTX%204060%20(8%20GB%20VRAM)-green.svg)](AGENTS.md)
[![Status](https://img.shields.io/badge/Milestone-P2c%20Phase%202%20Verified-brightgreen.svg)](progress.md)
[![Tests](https://img.shields.io/badge/tests-50%2F50%20passing-success.svg)](progress.md)

---

## Authoritative Documentation & Progress Tracking

ScanForge enforces strict verification honesty and living project tracking. Before contributing, running, or reviewing, consult these two core living documents:

- **[progress.md](progress.md)** — **Single Source of Truth** for real-time project status across all agent and developer sessions. Contains the living milestone tracker, verified vs. unverified feature matrix, empirical hardware benchmarks, inlier support tables, and session resumption guides.
- **[AGENTS.md](AGENTS.md)** — **Authoritative Developer & Agent Conventions**. Defines strict guidelines on planning and approval workflows, verification honesty ("never claim something works unless you ran it"), 8 GB VRAM budget enforcement, interior mesh priority, tool isolation via `ToolRunner`, and Git security rules.

---

## Current Project Condition & Milestone Status

| Milestone | Scope | Status | Verification & Evidence |
|---|---|---|---|
| **P0** | Repo skeleton, Docker Compose (mock profile), `doctor.py`, `AGENTS.md`, OpenAPI contract, pinned versions | **Done** | Verified via `doctor.py` and Compose healthchecks (`cf97f7c`) |
| **P1** | Job system + multipart upload + live SSE streaming + full React frontend on MOCK engine | **Accepted** | Verified end-to-end with procedural interior room generation (`e113930`) |
| **P2a** | GPU Worker Build (CUDA 12.1.1, COLMAP 3.9.1 sm_89, OpenMVS v2.2.0 sm_89, Blender 4.1.0, PyTorch 2.5.1+cu121) | **Done** | Container passes `doctor.py` and GPU passthrough sanity checks |
| **P2b** | Video ingest + letterbox auto-crop + interior-tuned COLMAP SfM (GPU) + 4-panel diagnostic trajectory plot + cut validation | **Done** | Verified on RTX 4060 GPU with real interior video captures (`house_test_30s.mp4`, `bedroom_vid.mp4`) |
| **P2c Phase 1/1b** | Route A mesh: OpenMVS DensifyPointCloud, ReconstructMesh, KDTree color transfer, TextureMesh UV atlas, camera up-vector alignment ($\bar{\mathbf{u}} \to +Y$), 4-view offscreen Blender renders | **Done** | Verified on RTX 4060 GPU on reference house and tour captures |
| **P2c Phase 2** | Mesh cleanup (floater pruning), room analysis in SfM frame, relative floor support detection, normal-aware plane snapping, conservative camera bbox enveloping, quadric decimation, UV texturing, Poisson vs Delaunay A/B | **Hardened & VERIFIED** | **100% verified on real hardware** (`house_test_30s.mp4` Job `f0e89d25` and `enhanced_interior_tour_1080p.mp4` Job `2b7b3bcc`). All 6 review items resolved, 50/50 tests passing with test DB isolation. |
| **P2c Phase 3** | Floor leveling ($Y=0$), zero-retexturing scale calibration seam, multi-format exporters (GLB, OBJ, PLY, STL, XYZ, FBX, USDZ), quality report | **Next Milestone** | Awaiting user review of Phase 2 evidence |
| **P3** | 3DGS training (`splatfacto` / `gsplat`) + floater cleanup + splat formats + splat viewer | **Not Started** | Blocked on P2c |
| **P4** | Route B (depth-fusion mesh) + mesh-inclusive 3DGS + Auto heuristic + floor plan + room dimensions | **Not Started** | Blocked on P3 |
| **P5** | Hardening: cancel, resume, disk cleanup, error messaging, comprehensive docs, full test suite | **Not Started** | Blocked on P4 |
| **P6** | LiDAR / RGB-D pipeline (feature-flagged `ENABLE_LIDAR=false`) + synthetic test data | **Not Started** | Blocked on P5 |

---

## Hardware Target & 8 GB VRAM Optimization Rules

ScanForge is purpose-built and validated on consumer GPU hardware under strict memory constraints:

| Parameter | Target Specification |
|---|---|
| **Host OS** | Windows 11 + WSL2 (Ubuntu 22.04 LTS) |
| **GPU** | NVIDIA GeForce RTX 4060 Laptop GPU (**8 GB VRAM**, Ada Lovelace sm_89) |
| **CUDA Arch** | `TORCH_CUDA_ARCH_LIST=8.9`, CMake `CUDA_ARCHITECTURES=89` |
| **RAM Budget** | 11 GB WSL2 memory allocation, 16 GB swap file |
| **COLMAP Cap** | Downscales max image size to $\approx 2000\text{ px}$ to fit 8 GB VRAM budget |
| **OpenMVS Resolution** | Resolution-level 2 (Standard/Draft), Level 1 (High) with automated low-memory retry |
| **Concurrency** | Strictly **1 GPU job at a time**; memory cleared between pipeline stages in separate subprocesses |

---

## Verified Visual Evidence & Benchmark Outputs

All reconstructions are validated with offscreen Blender renders across 4 canonical views (Perspective 1, Perspective 2, Top-Down Plan, Side Profile) saved directly under [`outputs/`](outputs/):

### 1. Progression Contact Sheets (Raw $\to$ Cleaned $\to$ Repaired $\to$ Decimated $\to$ Textured)
- **Reference House Clip** (`outputs/house_phase2_sheet.png`): Complete 6-stage progression from 1.21M dense points to 200k textured faces in 3m 27s total wall-clock time.
- **Enhanced Interior Tour** (`outputs/tour_phase2_sheet.png`): 2.80M dense points to 200k textured faces in 6m 15s; completely pruned external blue-grey slab and window reflection ghosts.

### 2. Over-Pruning Resolution Sheets (Before vs. After Conservative Enveloping)
- **House Over-Pruning Analysis** (`outputs/house_overpruning_analysis.png`): Demonstrates reduction of below-floor over-pruning from **79,759 faces (22.4%)** down to **0 faces (0.00%)** by selecting the true ground floor candidate (3,163 inliers) and applying camera trajectory bounding box protection.
- **Tour Over-Pruning Analysis** (`outputs/tour_overpruning_analysis.png`): Demonstrates elimination of outside-wall over-pruning from **88,914 faces (12.1%)** down to **0 faces (0.00%)** by disabling single-plane half-space wall clipping.

### 3. Interior Wall Texture Close-Ups (Seam-Free Verification)
- **House Wall Close-Up** (`outputs/house_wall_closeup.png`): High-resolution view of living room wall texture.
- **Tour Wall Close-Up** (`outputs/tour_wall_closeup.png`): High-resolution view of bedroom wall texture.
- **True UV Texture Coverage**: **99.98%** (House) and **99.99%** (Tour) valid photo pixel coverage across all triangles.

### 4. Reconstruction A/B Comparison (Delaunay vs. Screened Poisson)
- **House Comparison** (`outputs/house_poisson_vs_delaunay.png`): Delaunay (272k faces, faithful boundaries) vs Poisson (640k faces).
- **Tour Comparison** (`outputs/tour_poisson_vs_delaunay.png`): Demonstrates that Delaunay accurately preserves the 10.9-unit interior room height, whereas Screened Poisson inflates an unobserved ceiling balloon to a height of 34.8 units (>3x actual room height). **Delaunay is the recommended default**.

---

## Quick Start & Operations

### 1. Prerequisites
- Docker Engine & Docker Compose (v2.20+)
- For GPU Mode: NVIDIA Container Toolkit + NVIDIA Drivers (Ada Lovelace / RTX 4060 compatible)

### 2. Configuration
Copy the configuration template:
```bash
cp .env.example .env
```

### 3. Run in Mock Mode (No GPU Required)
Ideal for CI, frontend development, and automated testing:
```bash
make up-mock
# Or manually:
SCANFORGE_ENGINE=mock COMPOSE_PROFILES=mock docker compose up -d --build
```
- **Web UI**: [http://localhost:3000](http://localhost:3000)
- **API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 4. Run in GPU Mode (NVIDIA RTX 4060 / CUDA)
Activates the heavy CUDA image with COLMAP, OpenMVS, and PyTorch:
```bash
make up-gpu
# Or manually:
SCANFORGE_ENGINE=real COMPOSE_PROFILES=gpu docker compose up -d --build
```

Verify GPU container health and tool installations:
```bash
make doctor
# Or inside the GPU worker container:
docker compose --profile gpu exec worker-gpu python scripts/doctor.py
```

### 5. Running the Test Suite
ScanForge features an isolated test database architecture: pytest runs against an ephemeral SQLite database and temporary storage directory, completely protecting `/data/scanforge.db`:

```bash
# Run backend test suite (FastAPI, job queues, ingestion, SIFT, calibration):
make test-backend

# Run full test suite inside worker-gpu (includes Open3D and mesh pipeline tests):
docker compose --profile gpu exec worker-gpu pytest /workspace/backend/tests/

# Run live end-to-end smoke test through Nginx port 3000:
make smoke
```

---

## Repository Structure

```
scanforge/
├── AGENTS.md               # Authoritative engineering conventions & agent rules
├── progress.md             # Single source of truth for living status & verification
├── README.md               # Project guide, architecture overview, and quickstart
├── Makefile                # Operational shortcuts (up-mock, up-gpu, smoke, test)
├── docker-compose.yml      # Service orchestration (profiles: mock, gpu, test)
├── .env.example            # Environment configuration template
│
├── docs/                   # Authoritative specifications and architectural blueprints
│   ├── SPEC.md             # Master technical specification
│   ├── API.md              # OpenAPI contract specification
│   ├── ARCHITECTURE.md     # Architecture & data flow diagrams
│   ├── PIPELINES.md        # Pipeline stages & quality preset matrices
│   ├── MESH_ROUTES_COMPARISON.md # Route A vs Route B comparative analysis
│   ├── LIDAR_INPUT_FORMAT.md # RGB-D / Record3D input specification
│   ├── LICENSES.md         # Component license audits (Apache, AGPL, MIT)
│   ├── VERSIONS.md         # Pinned software versions
│   └── TROUBLESHOOTING.md  # Common failure modes and diagnostics
│
├── backend/                # FastAPI backend & reconstruction pipelines
│   ├── app/
│   │   ├── api/            # REST API route handlers
│   │   ├── core/           # ToolRunner & stage execution framework
│   │   ├── db/             # SQLModel session & engine management
│   │   ├── models/         # Pydantic v2 data models
│   │   ├── pipelines/      # Reconstruction stages (SfM, OpenMVS, Mesh, 3DGS)
│   │   │   ├── mesh/       # Cleanup, RoomAnalysis, PlaneRepair, Decimate
│   │   │   └── photo/      # COLMAP SfM & OpenMVS stages
│   │   ├── queue/          # RQ Redis queue worker & job dispatch
│   │   └── services/       # Job, storage, and event streaming services
│   ├── scripts/            # Blender headless rendering & composite sheet scripts
│   └── tests/              # Pytest unit & integration test suite (50 tests)
│
├── frontend/               # React + TypeScript + Vite + Tailwind web application
│   ├── src/
│   │   ├── components/     # Viewer, MeasureTool, QualityReport, FormatPicker
│   │   └── services/       # SSE streaming & API client
│   └── nginx.conf          # Reverse proxy with chunked SSE streaming
│
├── docker/                 # Production Dockerfiles (worker-gpu, api, frontend)
├── outputs/                # Rendered evidence sheets, close-ups, and comparison PNGs
└── scripts/                # Utility scripts (doctor.py, e2e_smoke.py, submit_real_run.py)
```

---

## Licensing & Compliance

All third-party dependencies, licenses, and restrictions are audited in [docs/LICENSES.md](docs/LICENSES.md). Key licensing notices:
- **OpenMVS** is licensed under **AGPL-3.0**. Running it inside an isolated container does not eliminate AGPL copyleft obligations for hosted network applications. Commercial and hosted deployments must review these obligations.
- **Depth Anything V2**: Only the **Small** variant (Apache-2.0) is permitted. Base, Large, and Giant variants are non-commercial (CC-BY-NC-4.0) and must not be used.
- **Original Inria 3DGS code**: Non-commercial; ScanForge uses Apache-2.0 / MIT clean-room alternatives (`gsplat` / `nerfstudio`).
