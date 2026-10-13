# ScanForge — Agent Conventions (AGENTS.md)

> **Authoritative spec:** `docs/SPEC.md`. If this file and the spec conflict, the spec wins.

---

## 1. Product Identity

- Product name: **ScanForge**. Never use "KIRI", "Polycam", or any third-party name/logo/branding.
- Three scan types: **Photo Scan**, **3DGS Scan**, **LiDAR Scan** (Beta, feature-flagged).

---

## 2. Target Environment

| Item | Value |
|---|---|
| OS | Windows 11 + WSL2 (Ubuntu 22.04) + Docker Desktop w/ GPU passthrough |
| GPU | NVIDIA RTX 4060, **8 GB VRAM**, Ada arch, compute capability 8.9 |
| CUDA arch | `TORCH_CUDA_ARCH_LIST=8.9`, CMake `CUDA_ARCHITECTURES=89` |
| Project files | Inside WSL filesystem (`~/scanforge`), **never** under `/mnt/c` |
| Concurrency | **1 GPU job at a time**; free VRAM between stages (separate subprocesses) |

---

## 3. Working Rules

### Planning & Approval
- Always start in **Planning mode**: produce an Implementation Plan artifact, wait for explicit user approval before writing code.
- After each milestone (P0–P6): run tests, produce a walkthrough artifact (screenshots/logs of real UI), list verified vs. unverified items.

### Research Before Code
- **NEVER** guess CLI flags, package versions, or API signatures from memory.
- Run `<tool> --help`, read installed package docs, or browse official docs first.
- Pin every version used in `docs/VERSIONS.md`.

### Mock Mode
- If GPU/tool is unavailable, use the **MOCK engine** (`SCANFORGE_ENGINE=mock`).
- Mock mode generates a procedural interior room mesh + small synthetic splat (no binary assets).
- Finish everything else and clearly list what needs real-hardware verification.

### Code Quality
- Typed Python (Pydantic v2, type hints everywhere).
- Typed TypeScript (strict mode).
- Every external tool invocation goes through `ToolRunner` — no raw `subprocess` calls elsewhere.
- Never shell-interpolate user input; use argument lists.
- Safe zip extraction (no path traversal, zip-bomb limits).

### Parallelism
- Work can be split across agents: (A) backend + job system, (B) frontend, (C) reconstruction pipelines, (D) Docker/infra/tests.
- All agents share the **API contract** defined in `docs/API.md` as the single source of truth.

### Verification Honesty
- **Never claim something works unless you ran it.**
- If a feature, pipeline stage, or integration has not been executed and verified, mark it as **UNVERIFIED** in the walkthrough and any related documentation.
- Walkthroughs must clearly separate verified items (with evidence: screenshots, logs, test output) from unverified items.

### Living Status & Progress (progress.md)
- `progress.md` in the repo root is the **single source of truth** for project status across all agent sessions.
- **Mandatory updates**: `progress.md` MUST be updated on every behavior change, milestone completion, bug fix, or verification state change. Never leave it stale.
- Any agent resuming work must inspect `progress.md` first to orient itself on milestones, verified status, fixed bugs, and next steps before taking action.

### Public GitHub Repository & Backups
- The repo is public (`https://github.com/Ommali8421/ScanForge.git`).
- Run `git push` at the end of every milestone or sub-milestone.
- **Never force-push** (`git push --force`).
- **Never commit** `.env`, secrets, tokens, personal paths, or test videos.

---

## 4. Priority Order (Final)

1. **Mesh quality for interiors** — primary deliverable.
2. **3DGS** — mesh-inclusive mode is a **core** feature (not experimental).
3. **LiDAR / RGB-D** — last, behind `ENABLE_LIDAR=false` feature flag.

If any older text conflicts with this order, this order wins.

---

## 5. 8 GB VRAM Budget Rules

- COLMAP: cap `max_image_size ≈ 2000 px`.
- OpenMVS: `resolution-level 2` for Draft and Standard; `resolution-level 1` for High; expose `low-memory` retry that automatically drops resolution level on OOM.
- 3DGS: plain `splatfacto` (not splatfacto-big), downscale to ≤ 1080 p, cap max Gaussians, auto-retry on CUDA OOM at lower settings.
- Mesh-inclusive 3DGS: prefer 2DGS + TSDF at reduced resolution; Gaussian Opacity Fields stays optional.
- Monocular depth: use **Small** model variant (Depth Anything V2 Small — Apache-2.0). Larger variants are CC-BY-NC; do not use them.
- One GPU job at a time; free GPU memory between stages via separate subprocesses.

---

## 6. Milestones (stop and report after each)

| Milestone | Scope | Done When |
|---|---|---|
| **P0** | Repo skeleton, Docker Compose (mock profile only), `doctor.py`, AGENTS.md, API contract | `docker compose up` serves UI + health |
| **P1** | Job system + upload + SSE + full frontend on MOCK engine | Upload, watch progress, preview, download (all 3 scan types) |
| **P2** | Interior-tuned SfM + Route A mesh + mesh post-processing + scale calibration + floor alignment + mesh exporters + mesh viewer (incl. measurement tool) | **Stop for user review on a real room video** |
| **P3** | 3DGS training + floater cleanup + splat formats + splat viewer | Splat preview + downloads work |
| **P4** | Route B (depth-fusion mesh) + mesh-inclusive 3DGS + Auto heuristic + floor plan + room dimensions | Both routes compared in `docs/MESH_ROUTES_COMPARISON.md` |
| **P5** | Hardening: cancel, resume, cleanup, error messages, docs, tests | All tests pass, docs complete |
| **P6** | LiDAR / RGB-D pipeline (feature-flagged) + synthetic-data tests + estimated-depth fallback | LiDAR card works end-to-end |

**Delivery order:** Plan → P0–P2 → user review on real video → P3 onward.

---

## 7. File Structure

Follow exactly the structure in `docs/SPEC.md` § FILE STRUCTURE, plus:
- `backend/app/pipelines/mesh/` — shared mesh post-processing stages.
- `frontend/src/components/MeasureTool.tsx` — two-point distance measurement (also used for scale calibration).
- `frontend/src/components/QualityReport.tsx` — mesh quality report display.
- `frontend/src/components/FloorPlanView.tsx` — floor-plan visualization.
- `docs/MESH_ROUTES_COMPARISON.md` — Route A vs Route B comparison on the same capture.

Deviate from the spec's structure only with justification stated in the plan.

---

## 8. Tech Stack (planned; versions get pinned in `docs/VERSIONS.md`)

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLModel + SQLite (Postgres-ready), Redis + RQ, SSE, Uvicorn |
| Frontend | React + TypeScript + Vite + Tailwind, three.js (react-three-fiber), `@mkkellogg/gaussian-splats-3d` (MIT) |
| Infra | Docker Compose with profiles: `mock` (slim worker) and `gpu` (heavy COLMAP/OpenMVS image); `.env`-driven config; health checks |
| Tooling | ffmpeg, COLMAP (CUDA), OpenMVS, nerfstudio (splatfacto/gsplat), Open3D, trimesh, pygltflib, xatlas, Blender (headless), optional rembg |

---

## 9. API Contract

Defined in `docs/API.md`. Key endpoints (see spec for full details):

- `POST /api/jobs` — create scan job (multipart upload)
- `GET /api/jobs`, `GET /api/jobs/{id}` — list / detail
- `GET /api/jobs/{id}/events` — SSE progress stream
- `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}`
- `GET /api/jobs/{id}/artifacts`, `/download/{format}`, `/download-all`
- `POST /api/jobs/{id}/calibrate` — scale calibration (two 3D points + real distance)
- `GET /api/jobs/{id}/report` — mesh quality + room dimensions JSON
- `GET /api/capabilities` — scan types, presets, format matrix, limits, engine mode
- `GET /api/health`

---

## 10. Security

- **Upload size cap**: configurable maximum upload size; stream uploads to disk, reject if exceeded.
- **Filename sanitising**: strip path components, replace unsafe characters, enforce allowlisted extensions.
- **CORS**: limited to the frontend origin only.
- **Auto-delete**: jobs older than N days are automatically deleted (N is configurable).
- **Safe zip extraction**: guard against path traversal and zip bombs (size and entry-count limits).
- **No shell interpolation**: all subprocess invocations use argument lists, never string interpolation.

---

## 11. Pipeline Architecture

Core abstractions (see `docs/SPEC.md` § ARCHITECTURE for full detail):

- **`Stage`**: named unit of work with `run(ctx) → StageResult`, declared inputs/outputs, a `weight` for progress calculation. Stages are **idempotent and cached**: skip if outputs exist and the params hash is unchanged. This enables **resume after crash**.
- **`Pipeline`**: ordered list of Stages for a scan type, built by a registry keyed by `ScanType`.
- **`JobContext`**: job ID, workdir, params, logger, progress callback, cancel token (checked between stages; kills subprocesses on cancel).
- **`ToolRunner`**: single wrapper around `subprocess` that streams stdout/stderr into the job log, parses progress where possible, enforces timeouts, and raises typed errors with the last 50 log lines. All external tool invocations go through `ToolRunner`.

### Pluggable Engine Interfaces

| Interface | Default Implementation | Purpose |
|---|---|---|
| `SfMEngine` | `ColmapSfM` | Feature extraction + matching + mapping |
| `MVSEngine` | `OpenMVSDense` | Dense reconstruction + texturing |
| `SplatTrainer` | `NerfstudioSplatfacto` | 3DGS training |
| `SplatMesher` | `TSDFSplatMesher` | Depth from splat → TSDF → mesh |
| `DepthSource` | `MonocularDepth` / `SplatDepthRenderer` | Per-frame depth maps |
| `Exporter` | `MultiFormatExporter` | Canonical → selected output formats |

The `MOCK` engine (`SCANFORGE_ENGINE=mock`) replaces all interfaces with mock implementations that sleep, emit realistic progress, and output procedurally generated sample data.

---

## 12. Interiors

ScanForge is optimised for **interior scanning** (rooms, apartments, houses). See `docs/SPEC.md` § USE CASE: INTERIORS for the full rules. Key conventions:

- **Plane-aware mesh repair**: after meshing, detect dominant planes via RANSAC (Open3D), fill holes on those planes, regularize planar regions, remove ghost surfaces behind windows/mirrors.
- **Scale calibration**: Photo/3DGS results have arbitrary scale. The user picks two points in the viewer and enters a real-world distance; the backend rescales all outputs. LiDAR results are already metric.
- **Floor alignment**: RANSAC-fit the lowest dominant plane → rotate to Y=0 (or Z=0 per up-axis setting), level walls to vertical.
- **Two mesh routes**, both compared on the same test capture in `docs/MESH_ROUTES_COMPARISON.md`:
  - **Route A (Photogrammetry)**: COLMAP → OpenMVS (Densify → ReconstructMesh → optional Refine → Texture).
  - **Route B (Depth fusion)**: per-frame monocular depth aligned to sparse SfM points → Open3D TSDF fusion → mesh.
  - User selects Auto / Photogrammetry / Depth fusion under Advanced; Auto chooses by heuristic and records the reason.
- **Mesh post-processing** is split into separate cached stages (cleanup → plane repair → floor align → scale → decimate → UV/texture bake) so that `/calibrate` re-runs only from the scale stage onward without repeating earlier work.

---

## 13. Testing Requirements

- **Unit**: frame extraction, sharpness, zip safety, `.r3d`/RGB-D parsers, TSDF on synthetic scene, each exporter round-trip, capability-matrix consistency.
- **Integration**: full pipeline in MOCK mode (CI-friendly); real `@gpu`-marked smoke tests per scan type on small public sample data.
- **Frontend**: component tests for FormatPicker filtering; Playwright E2E (upload → progress → download). Frontend tests run in a separate Node container.
- **Browser verification**: use the Antigravity browser to exercise UI and attach screenshots to walkthroughs.

---

## 14. Documentation Requirements

| File | Purpose |
|---|---|
| `README.md` | Setup steps for GPU and no-GPU (mock) modes |
| `docs/API.md` | OpenAPI contract (written first) |
| `docs/ARCHITECTURE.md` | System architecture |
| `docs/PIPELINES.md` | Pipeline details, quality preset tables |
| `docs/MESH_ROUTES_COMPARISON.md` | Route A vs Route B comparison on the same capture |
| `docs/LIDAR_INPUT_FORMAT.md` | RGB-D input format spec with sample |
| `docs/LICENSES.md` | License of every component — **all unverified until confirmed from each repo's LICENSE file** |
| `docs/VERSIONS.md` | Pinned versions of all tools and libraries |
| `docs/TROUBLESHOOTING.md` | Common issues and fixes |

---

## 15. Licensing Awareness

> **All licenses below are unverified until confirmed from each repository's actual LICENSE file.** Before using any component, read its LICENSE file and record the confirmed license in `docs/LICENSES.md`.

- **Apache-2.0 (unverified)**: gsplat, nerfstudio, Depth Anything V2 Small.
- **AGPL-3.0 (unverified)**: OpenMVS. **Treat OpenMVS as AGPL-affected.** Running it in an isolated container does **not** resolve AGPL obligations. Flag this dependency before any hosted or commercial use, and document the implications clearly in `docs/LICENSES.md`.
- **CC-BY-NC-4.0 (unverified)**: Depth Anything V2 Base/Large/Giant — **do not use** these variants; use Small only.
- **Non-commercial (unverified)**: original Inria 3DGS code and derivatives (2DGS) — document clearly, flag before any commercial use.
- Record all confirmed licenses in `docs/LICENSES.md` with the date verified and a link to the source LICENSE file.

---

## 16. Definition of Done

Upload a room walk-through video → get a clean, textured, correctly-scaled interior mesh in several selected formats that open correctly in Blender, plus the splat. LiDAR is documented follow-up if P6 not reached. README has exact setup steps. `docs/LICENSES.md` and `docs/VERSIONS.md` are accurate. Final report lists what was verified on real hardware vs. mock mode, with unverified items clearly marked as **UNVERIFIED**.
