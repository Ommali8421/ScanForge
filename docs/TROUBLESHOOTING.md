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

---

## 4. Docker CLI and WSL2 Integration Pitfall: Never Wrapper docker.exe

**Symptom**: `docker` commands hang, fail to pass environment variables (`SCANFORGE_ENGINE`, `COMPOSE_PROFILES`), or corrupt WSL file path translations.

**Root Cause**:
Creating a wrapper script (e.g. `~/.local/bin/docker`) that invokes Windows `docker.exe` (`/mnt/c/.../docker.exe "$@"`) shadows the native Linux Docker client. Because Windows executables running under WSL cannot natively interpret POSIX signal trees, Linux file descriptors, or Linux environment variables without explicit `WSLENV` declarations, compose commands and container management become brittle.

**Rules & Resolution**:
1. **Never create a wrapper script for `docker.exe` inside WSL.**
2. Native Docker CLI in WSL is provided directly by Docker Desktop's WSL integration via `/usr/bin/docker -> /mnt/wsl/docker-desktop/cli-tools/usr/bin/docker`.
3. If `/usr/bin/docker` reports `No such file or directory`, **Docker Desktop is not running** or the WSL distro integration is disabled in Docker Desktop settings (*Settings -> Resources -> WSL Integration*). Launch Docker Desktop on Windows; the integration mount will appear automatically.
4. Ensure `which docker` resolves strictly to `/usr/bin/docker`. If any wrapper was placed in `~/.local/bin/docker` or `~/bin/docker`, remove or back it up (`mv ~/.local/bin/docker ~/.local/bin/docker.wrapper.bak`).

---

## 5. Web UI Upload Error: "Network error during upload" (Nginx 502 Bad Gateway)

**Symptom**: Large video uploads fail immediately with "Network error during upload" or Nginx returns `502 Bad Gateway`.

**Resolution**:
1. Check available disk space (`SCANFORGE_MIN_FREE_DISK_GB=5.0`). If disk is full, the API returns HTTP `507 Insufficient Storage`. Clean up old jobs via `DELETE /api/jobs/{id}` or run scratch purge `POST /api/jobs/{id}/cleanup-scratch`.
2. Ensure `client_max_body_size` in nginx config is set to at least `2048M`.
3. Check `docker compose logs api` to inspect upload stream errors.

---

## 6. Actionable Error Diagnostics (Milestone P5)

ScanForge maps failure tracebacks into structured, user-facing error codes with guided recovery steps:

| Error Code | Title | Root Cause | Actionable Remediation |
|---|---|---|---|
| `ERR_LOW_SFM_REGISTRATION` | Insufficient Camera Registration | SfM registered $< 60\%$ of video frames due to poor feature matches or low overlap. | • Aim for $> 70\%$ frame overlap.<br>• Walk in a slow, continuous perimeter loop around the room.<br>• Ensure even lighting; avoid featureless blank walls by including corners or furniture in view. |
| `ERR_MOTION_BLUR` | Excessive Motion Blur | Keyframe sharpness metric failed (Laplacian variance $< 15.0$) due to rapid camera movement. | • Walk slower, particularly when turning corners.<br>• Use a handheld smartphone stabilizer or gimbal.<br>• Record at 60 fps with ample lighting. |
| `ERR_PURE_ROTATION` | Pure Rotational Motion (Zero Baseline) | Camera was spun around a fixed point (tripod panning) without spatial translation. | • Walk a perimeter path through the room; do NOT spin in place.<br>• Maintain $\ge 0.5\text{m}$ of baseline between different viewing angles. |
| `ERR_CUDA_OOM` | GPU Memory Exhausted | Reconstruction exceeded the 8 GB GPU VRAM budget. | • Switch quality preset to 'Standard' or 'Draft'.<br>• Downscale input video to 1080p.<br>• Select 'Route B (Depth Fusion)' under Advanced Options for low-memory TSDF meshing.<br>• Click 'Resume Job' to re-try with automatic memory reduction. |
| `ERR_CORRUPT_INPUT` | Corrupted Input Media | Uploaded video or archive was corrupted or missing valid video streams. | • Verify the video plays cleanly in VLC before uploading.<br>• Transcode to standard H.264 / AAC MP4 format.<br>• Ensure upload completed without network interruption. |
| `ERR_GENERIC_FAILURE` | Reconstruction Processing Error | An unexpected exception occurred during stage execution. | • Inspect the execution log drawer for traceback details.<br>• Click 'Resume Job' to retry from the last cached stage checkpoint.<br>• Re-process with 'Standard' quality preset. |

**Symptom**: When attempting to upload a video or photo archive from the web UI (`/new`), the upload fails immediately or during transmission with the red banner error: `"Network error during upload"`.

**Root Cause**:
The frontend container uses Nginx to reverse-proxy `/api/*` requests to the `api` container (`http://api:8000`). By default, Nginx evaluates static upstream hostnames (`proxy_pass http://api:8000;`) only once at container startup. When the `api` container is restarted or recreated by Docker Compose, Docker assigns it a new internal IP address on the bridge network. Because Nginx retains the defunct IP in its internal cache, upstream connections fail with `502 Bad Gateway (111: Connection refused)`. The browser's `XMLHttpRequest` connection is reset/severed, triggering `xhr.onerror` which the UI surfaces as `"Network error during upload"`.

**Resolution**:
1. `frontend/nginx.conf` is configured with Docker's internal DNS resolver (`resolver 127.0.0.11 valid=10s ipv6=off;`) and dynamic upstream variable binding (`set $api_backend http://api:8000; proxy_pass $api_backend;`). This forces Nginx to periodically re-resolve the container IP.
2. If encountering this in a modified environment, reload or restart the frontend container:
   ```bash
   docker compose restart frontend
   ```
3. Verify backend connectivity through the proxy:
   ```bash
   curl -i http://localhost:3000/api/health
   ```


