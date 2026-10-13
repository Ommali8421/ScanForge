#!/usr/bin/env python3
"""
ScanForge End-to-End Smoke Test (scripts/e2e_smoke.py)
Exercises the full reconstruction lifecycle against the live Compose stack via Nginx port 3000:
1. Validates /api/health and /api/capabilities
2. Uploads a generated test video
3. Consumes real-time SSE stream through Nginx until completion
4. Asserts progress events arrived live (incremental progression)
5. Verifies binary artifact downloads (GLB and OBJ)
6. Runs two consecutive scale calibrations asserting cumulative scaling
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
import requests

BASE_URL = os.environ.get("SCANFORGE_BASE_URL", "http://localhost:3000/api")


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def ensure_test_video(path: Path) -> Path:
    if path.exists() and path.stat().st_size > 1000:
        return path

    log(f"Test video not found at {path}, generating 5s synthetic test video...")
    cmd = [
        "docker", "compose", "exec", "api",
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=30",
        "-pix_fmt", "yuv420p", "/tmp/smoke_test.mp4"
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["docker", "cp", "scanforge-api-1:/tmp/smoke_test.mp4", str(path)])
    log(f"Test video generated successfully ({path.stat().st_size} bytes).")
    return path


def main():
    log("============================================================")
    log(" ScanForge Live E2E Smoke Test (Nginx Port 3000)")
    log("============================================================")

    # 1. Health check
    log("1. Checking system health through Nginx reverse proxy...")
    health_res = requests.get(f"{BASE_URL}/health", timeout=5)
    assert health_res.status_code == 200, f"Health check failed: {health_res.status_code}"
    health_data = health_res.json()
    log(f"   Health OK: engine={health_data.get('engine')}, db={health_data.get('db')}, redis={health_data.get('redis')}")

    # 2. Capabilities check
    log("2. Checking capabilities matrix...")
    cap_res = requests.get(f"{BASE_URL}/capabilities", timeout=5)
    assert cap_res.status_code == 200, f"Capabilities check failed: {cap_res.status_code}"
    cap_data = cap_res.json()
    log(f"   Available scan types: {cap_data.get('scan_types')}")
    log(f"   Photo output formats: {cap_data.get('format_matrix', {}).get('photo')}")

    # 3. Ensure test video
    video_path = ensure_test_video(Path("test_room.mp4"))

    # 4. Upload and create scan job
    log("3. Submitting reconstruction job via multipart upload...")
    with open(video_path, "rb") as vf:
        create_res = requests.post(
            f"{BASE_URL}/jobs",
            files={"file": (video_path.name, vf, "video/mp4")},
            data={
                "scan_type": "photo",
                "quality": "standard",
                "output_formats": json.dumps(["glb", "obj"]),
                "options": json.dumps({"include_mesh": True})
            },
            timeout=10
        )
    assert create_res.status_code == 202, f"Job creation failed ({create_res.status_code}): {create_res.text}"
    job_id = create_res.json()["job_id"]
    log(f"   Job enqueued: {job_id}")

    # 5. Consume live SSE stream through Nginx
    log("4. Subscribing to live SSE event stream through Nginx proxy...")
    sse_events = []
    sse_stages = []
    sse_done = threading.Event()
    start_time = time.time()

    def sse_reader():
        try:
            url = f"{BASE_URL}/jobs/{job_id}/events"
            resp = requests.get(url, stream=True, timeout=30)
            current_event = None
            for line in resp.iter_lines(decode_unicode=True):
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and current_event:
                    data_str = line.split(":", 1)[1].strip()
                    recv_time = time.time() - start_time
                    sse_events.append((current_event, data_str, recv_time))

                    if current_event == "stage":
                        try:
                            stage_json = json.loads(data_str)
                            stage_name = stage_json.get("stage")
                            pct = stage_json.get("progress")
                            sse_stages.append((stage_name, pct, recv_time))
                            log(f"   [SSE LIVE STAGE] {stage_name} ({pct}%) at t={recv_time:.2f}s")
                        except Exception:
                            pass
                    elif current_event == "completed":
                        log(f"   [SSE LIVE COMPLETED] Job finished at t={recv_time:.2f}s")
                        break
                    elif current_event in {"failed", "cancelled"}:
                        log(f"   [SSE TERMINATED] Received {current_event}: {data_str}")
                        break
        except Exception as e:
            log(f"   [SSE ERROR] {e}")
        finally:
            sse_done.set()

    sse_thread = threading.Thread(target=sse_reader, daemon=True)
    sse_thread.start()

    sse_done.wait(timeout=25)
    assert len(sse_events) > 0, "No SSE events received from server."

    event_types = [e[0] for e in sse_events]
    assert "completed" in event_types, f"Job did not emit completed event over SSE: {event_types}"

    # Assert progress events arrived live (at least 4 distinct progress percentages across time)
    distinct_progresses = set(s[1] for s in sse_stages)
    log(f"   Distinct progress states observed: {sorted(distinct_progresses)}")
    assert len(distinct_progresses) >= 4, f"Insufficient live progress updates: {distinct_progresses}"

    # Verify status in database
    job_res = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=5).json()
    assert job_res.get("status") == "completed", f"Job status is not completed: {job_res}"
    assert job_res.get("progress") == 100, f"Job progress is not 100: {job_res}"
    log("   Job verification confirmed in database (status=completed, progress=100%).")

    # 6. Verify binary artifact downloads
    log("5. Verifying artifact downloads through Nginx...")
    glb_res = requests.get(f"{BASE_URL}/jobs/{job_id}/download/glb", timeout=5)
    assert glb_res.status_code == 200, f"GLB download failed: {glb_res.status_code}"
    assert len(glb_res.content) > 500, f"GLB file unexpectedly small: {len(glb_res.content)} bytes"
    log(f"   GLB artifact OK ({len(glb_res.content)} bytes)")

    obj_res = requests.get(f"{BASE_URL}/jobs/{job_id}/download/obj", timeout=5)
    assert obj_res.status_code == 200, f"OBJ download failed: {obj_res.status_code}"
    assert len(obj_res.content) > 300, f"OBJ file unexpectedly small: {len(obj_res.content)} bytes"
    log(f"   OBJ artifact OK ({len(obj_res.content)} bytes)")

    # 7. Scale calibration 1
    log("6. Performing first scale calibration (distance 2.0m -> real 3.0m, factor=1.5)...")
    cal1_res = requests.post(
        f"{BASE_URL}/jobs/{job_id}/calibrate",
        json={"point_a": [0.0, 0.0, 0.0], "point_b": [2.0, 0.0, 0.0], "real_distance": 3.0},
        timeout=5
    )
    assert cal1_res.status_code == 202, f"Calibration 1 failed: {cal1_res.text}"
    cal1_data = cal1_res.json()
    assert cal1_data["applied_factor"] == 1.5, f"Wrong factor 1: {cal1_data}"
    assert cal1_data["cumulative_scale"] == 1.5, f"Wrong cumulative 1: {cal1_data}"
    log(f"   Calibration 1 accepted: applied={cal1_data['applied_factor']}, cumulative={cal1_data['cumulative_scale']}")

    # Wait for recalibration export
    for _ in range(20):
        time.sleep(0.5)
        status_check = requests.get(f"{BASE_URL}/jobs/{job_id}", timeout=5).json()
        if status_check.get("status") == "completed" and status_check.get("progress") == 100:
            break

    # 8. Scale calibration 2
    log("7. Performing second scale calibration (distance 1.0m -> real 2.0m, factor=2.0)...")
    cal2_res = requests.post(
        f"{BASE_URL}/jobs/{job_id}/calibrate",
        json={"point_a": [0.0, 0.0, 0.0], "point_b": [1.0, 0.0, 0.0], "real_distance": 2.0},
        timeout=5
    )
    assert cal2_res.status_code == 202, f"Calibration 2 failed: {cal2_res.text}"
    cal2_data = cal2_res.json()
    assert cal2_data["applied_factor"] == 2.0, f"Wrong factor 2: {cal2_data}"
    # Cumulative must be 1.5 * 2.0 = 3.0
    assert cal2_data["cumulative_scale"] == 3.0, f"Wrong cumulative 2 (expected 3.0): {cal2_data}"
    log(f"   Calibration 2 accepted: applied={cal2_data['applied_factor']}, cumulative={cal2_data['cumulative_scale']}")

    log("============================================================")
    log(" E2E Smoke Test PASSED successfully!")
    log("============================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
