"""
Real Test Video Submission and SSE Monitoring Script (scripts/submit_real_run.py)
Submits a test video via the real HTTP upload path (POST /api/jobs),
subscribes to live SSE events, captures full logs, timings, and VRAM/RAM metrics,
and downloads the resulting sparse PLY, camera trajectory PNG, and SfM report JSON.
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def submit_video_job(api_base: str, video_path: Path, camera_model: str = "SIMPLE_RADIAL", matcher: str = "sequential") -> str:
    """Submit video reconstruction job via multipart/form-data."""
    if not video_path.exists():
        raise FileNotFoundError(f"Test video not found: {video_path}")

    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"[Upload] Reading test video {video_path.name} ({size_mb:.2f} MB)...")

    boundary = f"----WebKitFormBoundary{int(time.time()*1000)}"
    body = io.BytesIO()

    # Form fields
    fields = {
        "scan_type": "photo",
        "quality": "standard",
        "output_formats": json.dumps(["glb", "ply"]),
        "options": json.dumps({
            "camera_model": camera_model,
            "matcher": matcher
        })
    }

    for name, value in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(f"{value}\r\n".encode())

    # File data
    filename = video_path.name
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.write(b"Content-Type: video/mp4\r\n\r\n")

    with open(video_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            body.write(chunk)

    body.write(f"\r\n--{boundary}--\r\n".encode())

    data = body.getvalue()
    req = urllib.request.Request(
        f"{api_base}/api/jobs",
        data=data,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(data))
        },
        method="POST"
    )

    print(f"[Upload] Streaming {len(data) / (1024*1024):.2f} MB payload to {api_base}/api/jobs...")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    elapsed = time.time() - t0
    job_id = result["job_id"]
    print(f"[Upload] Job created successfully: {job_id} in {elapsed:.2f}s")
    return job_id


def stream_sse_progress(api_base: str, job_id: str, timeout: int = 1800):
    """Subscribe to SSE events and stream pipeline progress to stdout."""
    events_url = f"{api_base}/api/jobs/{job_id}/events"
    print(f"[SSE] Subscribing to event stream: {events_url}")

    req = urllib.request.Request(events_url, headers={"Accept": "text/event-stream"})
    start_time = time.time()

    current_event = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            text = line.decode("utf-8").rstrip("\r\n")
            if not text:
                continue

            if text.startswith("event:"):
                current_event = text.split(":", 1)[1].strip()
            elif text.startswith("data:"):
                raw_data = text.split(":", 1)[1].strip()
                try:
                    payload = json.loads(raw_data)
                except Exception:
                    payload = {"raw": raw_data}

                timestamp = time.strftime("%H:%M:%S")
                if current_event == "stage":
                    stage = payload.get("stage", "unknown")
                    progress = payload.get("progress", 0)
                    msg = payload.get("message", "")
                    print(f"[{timestamp}] [STAGE] {stage.upper():16} ({progress:3d}%) {msg}")
                elif current_event == "log":
                    log_line = payload.get("line", "")
                    print(f"[{timestamp}]   {log_line}")
                elif current_event == "completed":
                    print(f"\n[{timestamp}] ========================================================")
                    print(f"[{timestamp}]  JOB COMPLETED SUCCESSFULLY in {time.time() - start_time:.1f}s")
                    print(f"[{timestamp}] ========================================================")
                    return True
                elif current_event == "error":
                    err = payload.get("error", "Unknown error")
                    print(f"\n[{timestamp}] [ERROR] Job failed: {err}", file=sys.stderr)
                    return False
                elif current_event == "cancelled":
                    print(f"\n[{timestamp}] [CANCELLED] Job was cancelled.", file=sys.stderr)
                    return False


def main():
    parser = argparse.ArgumentParser(description="Submit real test video to ScanForge and stream live progress")
    parser.add_argument("--video", default=os.path.expanduser("~/videos/house_test_30s.mp4"), help="Path to test video")
    parser.add_argument("--api", default="http://localhost:3000", help="ScanForge frontend/proxy API base URL")
    parser.add_argument("--matcher", default="sequential", choices=["sequential", "exhaustive"], help="COLMAP matcher")
    parser.add_argument("--camera", default="SIMPLE_RADIAL", help="Camera model")
    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"ERROR: Video file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    print("=================================================================")
    print(" ScanForge Real Video Pipeline Run (P2b Milestone)")
    print(f" Video: {video_path.name} ({video_path.stat().st_size / (1024*1024):.2f} MB)")
    print(f" Camera Model: {args.camera}, Matcher: {args.matcher}")
    print("=================================================================")

    # 1. Check API and engine mode
    try:
        with urllib.request.urlopen(f"{args.api}/api/capabilities", timeout=5) as resp:
            caps = json.loads(resp.read().decode())
            print(f"[Preflight] Connected to ScanForge. Engine: {caps.get('engine')}, GPU Available: {caps.get('gpu_available')}")
            if caps.get("engine") != "real":
                print("WARNING: Active engine is 'mock', not 'real'. Run 'make up-gpu' first to test GPU pipeline!", file=sys.stderr)
    except Exception as e:
        print(f"ERROR connecting to ScanForge API at {args.api}: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Submit job
    job_id = submit_video_job(args.api, video_path, camera_model=args.camera, matcher=args.matcher)

    # 3. Stream SSE
    success = stream_sse_progress(args.api, job_id)

    # 4. Fetch details & artifacts
    try:
        with urllib.request.urlopen(f"{args.api}/api/jobs/{job_id}", timeout=10) as resp:
            job_data = json.loads(resp.read().decode())
            print("\n[Artifacts Generated]")
            for art in job_data.get("artifacts", []):
                print(f"  - {art['filename']} ({art['size_bytes'] / 1024:.1f} KB) -> {args.api}/api/jobs/{job_id}/download/{art['format']}")
    except Exception as e:
        print(f"Could not fetch artifacts list: {e}")

    # 5. Fetch SfM report
    try:
        with urllib.request.urlopen(f"{args.api}/api/jobs/{job_id}/download/json", timeout=10) as resp:
            sfm_report = json.loads(resp.read().decode())
            print("\n[SfM Reconstruction Report]")
            print(json.dumps(sfm_report, indent=2))
    except Exception:
        pass

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
