# ScanForge Troubleshooting Guide (docs/TROUBLESHOOTING.md)

Common operational issues, diagnosis steps, and remediation strategies.

---

## 1. Out of VRAM (CUDA OOM)

**Symptom**: Job status moves to `failed` during OpenMVS Densify or Nerfstudio Splatfacto training with `CUDA out of memory`.

**Resolution**:
1. Check available VRAM with `python scripts/doctor.py`.
2. Ensure no secondary GPU tasks are running on the RTX 4060.
3. For photogrammetry, decrease the quality preset from `High` to `Standard` or `Draft` (which forces `resolution-level 2`).
4. In `splatfacto`, ScanForge automatically caps input image resolution to 1080p and reduces max Gaussian budget upon encountering an initial OOM.

---

## 2. Windows / WSL2 Disk Space Issues

**Symptom**: Subprocess exits with `No space left on device` during extraction or dense matching.

**Resolution**:
1. Verify storage with `python scripts/doctor.py`.
2. Prune old Docker images: `docker system prune -a --volumes`.
3. Clear completed ScanForge jobs via `DELETE /api/jobs/{id}` or adjust `SCANFORGE_JOB_TTL_DAYS`.

---

## 3. SSE Connection Disconnections

**Symptom**: Web UI shows reconnection spinner or missing progress updates.

**Resolution**:
1. Ensure reverse proxy has buffering disabled:
   ```nginx
   proxy_buffering off;
   proxy_request_buffering off;
   ```
2. ScanForge SSE endpoints replay recent progress and logs upon reconnection, ensuring zero state loss on network hiccup.
