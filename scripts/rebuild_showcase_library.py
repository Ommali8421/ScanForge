#!/usr/bin/env python3
"""
ScanForge Showcase Library Orchestrator
Submits showcase reconstruction jobs strictly one-at-a-time (concurrency = 1),
polls live progress, logs GPU VRAM telemetry, runs programmatic invariant audits,
renders 4-view proof sheets, and manages error retry limits (max 2 attempts).
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional

API_BASE = "http://localhost:8000/api"

def get_gpu_vram_mb() -> float:
    """Reads current GPU memory used via nvidia-smi."""
    try:
        cmd = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip().split("\n")[0])
    except Exception:
        pass
    return 0.0

def submit_job(
    video_path: Path,
    scan_type: str = "gaussian_splat",
    quality: str = "standard",
    output_formats: Optional[List[str]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Submits a job via POST /api/jobs using multipart form data."""
    if output_formats is None:
        if scan_type == "gaussian_splat":
            output_formats = ["ply", "splat", "spz"]
        else:
            output_formats = ["glb", "obj", "ply", "stl", "xyz", "fbx", "usdz"]

    if options is None:
        options = {}

    print(f"\n[ORCHESTRATOR] Submitting job for {video_path.name} ({scan_type}, quality='{quality}')...")
    
    # We use curl directly to avoid python memory buffer issues for multi-GB files
    cmd = [
        "curl", "-s", "-X", "POST", f"{API_BASE}/jobs",
        "-F", f"file=@{str(video_path)}",
        "-F", f"scan_type={scan_type}",
        "-F", f"quality={quality}",
        "-F", f"output_formats={json.dumps(output_formats)}",
        "-F", f"options={json.dumps(options)}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Job submission failed: {res.stderr}")

    try:
        data = json.loads(res.stdout)
    except Exception:
        raise RuntimeError(f"Unexpected response from API: {res.stdout}")

    if "job_id" not in data:
        raise RuntimeError(f"API rejected job: {data}")

    job_id = data["job_id"]
    print(f"[ORCHESTRATOR] Job created: {job_id} (Status: {data.get('status')})")
    return job_id

def poll_job_until_done(job_id: str, scene_name: str) -> Dict[str, Any]:
    """Polls a job until completed or failed, logging stage progress, elapsed time, and peak VRAM."""
    start_time = time.time()
    last_stage = None
    last_progress = -1
    peak_vram = 0.0

    while True:
        req = urllib.request.Request(f"{API_BASE}/jobs/{job_id}")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        status = data.get("status")
        stage = str(data.get("current_stage") or "queued")
        progress = int(data.get("progress") or 0)
        elapsed = time.time() - start_time
        cur_vram = get_gpu_vram_mb()
        if cur_vram > peak_vram:
            peak_vram = cur_vram

        if stage != last_stage or progress != last_progress:
            print(
                f"[ORCHESTRATOR] [{scene_name}] Job {job_id[:8]} -> Stage: {stage:<20} "
                f"({progress:>3}%) | Elapsed: {elapsed:>5.1f}s | VRAM: {cur_vram:.0f} MB (Peak: {peak_vram:.0f} MB)"
            )
            last_stage = stage
            last_progress = progress

        if status in ("completed", "failed", "cancelled"):
            data["runtime_seconds"] = round(elapsed, 1)
            data["peak_vram_mb"] = round(peak_vram, 1)
            return data

        time.sleep(4)

def run_job_with_retries(
    scene_name: str,
    video_path: Path,
    scan_type: str,
    quality: str = "standard",
    output_formats: Optional[List[str]] = None,
    options: Optional[Dict[str, Any]] = None,
    max_attempts: int = 2,
) -> Optional[Dict[str, Any]]:
    """Runs a single job with up to max_attempts attempts. Audits on completion."""
    for attempt in range(1, max_attempts + 1):
        print(f"\n=======================================================")
        print(f"[RUN] {scene_name.upper()} — Attempt {attempt}/{max_attempts} ({scan_type})")
        print(f"=======================================================")
        try:
            job_id = submit_job(video_path, scan_type, quality, output_formats, options)
            result = poll_job_until_done(job_id, scene_name)
            
            if result.get("status") == "completed":
                print(f"[RUN] Job {job_id} COMPLETED in {result['runtime_seconds']}s (Peak VRAM: {result['peak_vram_mb']} MB).")
                
                # Execute audit and proof rendering inside worker-gpu container
                print(f"[ORCHESTRATOR] Running audit and proof renders inside worker-gpu for {job_id}...")
                audit_cmd = [
                    "docker", "compose", "exec", "-T", "worker-gpu",
                    "python3", "/workspace/scripts/audit_and_render_showcase.py",
                    job_id, scan_type, scene_name
                ]
                audit_proc = subprocess.run(audit_cmd, capture_output=True, text=True)
                print(audit_proc.stdout)
                if audit_proc.returncode != 0:
                    print(f"[AUDIT ERROR] Audit or proof render failed:\n{audit_proc.stderr}")
                    raise RuntimeError(f"Audit/render failed with code {audit_proc.returncode}: {audit_proc.stdout}")

                # Proof sheets are written to /workspace/outputs/ or backend/outputs/
                out_dir = Path("outputs")
                out_dir.mkdir(parents=True, exist_ok=True)
                for f in Path("backend/outputs").glob(f"*{scene_name.lower()}*"):
                    dest = out_dir / f.name
                    if not dest.exists():
                        shutil.copy2(f, dest)

                if scan_type == "gaussian_splat":
                    out_proof = f"outputs/showcase_splat_{scene_name.lower()}.png"
                else:
                    out_proof = f"outputs/showcase_mesh_{scene_name.lower()}.png"

                result["proof_sheet"] = out_proof
                return result
            else:
                print(f"[RUN ERROR] Job {job_id} finished with status '{result.get('status')}': {result.get('error')}")
                if attempt < max_attempts:
                    print(f"[RUN] Retrying job for {scene_name}...")
                    time.sleep(5)
                else:
                    print(f"[RUN] Max attempts ({max_attempts}) reached for {scene_name}. Logging failure.")
                    return result
        except Exception as e:
            print(f"[RUN EXCEPTION] Attempt {attempt} failed: {e}")
            if attempt >= max_attempts:
                return {"status": "failed", "error": str(e), "scene_name": scene_name}
            time.sleep(5)
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ScanForge Showcase Library Rebuild")
    parser.add_argument("--skip_smoke", action="store_true", help="Skip smoke test and proceed directly to waves")
    parser.add_argument("--smoke_only", action="store_true", help="Run smoke test on house_test_30s only")
    parser.add_argument("--wave", choices=["1", "2", "all"], default="1", help="Which wave to run (1: 3DGS, 2: Meshes, all: both)")
    args = parser.parse_args()

    showcase_dir = Path("/home/om_mali/datasets/showcase_inputs")
    t2_4k_dir = Path("/home/om_mali/datasets/tanks_and_temples/videos")

    # Helper to resolve best video (4K preferred over 1080p)
    def resolve_video(scene: str, fallback_1080: str) -> Path:
        cand_4k = t2_4k_dir / f"{scene}.mp4"
        if cand_4k.exists() and cand_4k.stat().st_size > 1024 * 1024:
            return cand_4k
        cand_input = showcase_dir / fallback_1080
        if cand_input.exists():
            return cand_input
        cand_lower = showcase_dir / f"{scene.lower()}_1080p.mp4"
        if cand_lower.exists():
            return cand_lower
        cand_scanforge = Path(f"/home/om_mali/scanforge/{fallback_1080}")
        if cand_scanforge.exists():
            return cand_scanforge
        raise FileNotFoundError(f"Could not find video for {scene} (checked {cand_4k} and {cand_input})")

    completed_jobs = []
    failed_jobs = []

    # 1. SMOKE TEST (if not skipped)
    if not args.skip_smoke:
        print("\n*******************************************************")
        print("[PHASE 1] RUNNING END-TO-END SMOKE TEST (house_test_30s)...")
        print("*******************************************************")
        house_vid = resolve_video("House", "house_test_30s.mp4")
        smoke_res = run_job_with_retries(
            scene_name="house_smoke",
            video_path=house_vid,
            scan_type="gaussian_splat",
            quality="standard",
            max_attempts=2,
        )
        if not smoke_res or smoke_res.get("status") != "completed":
            print(f"[FATAL] Smoke test failed! Aborting showcase rebuild.\nResult: {smoke_res}")
            sys.exit(1)

        print("\n[SMOKE TEST PASS] house_test_30s passed all audit invariants and generated proof render.")
        completed_jobs.append(smoke_res)
        if args.smoke_only:
            print("[SMOKE ONLY] Finished smoke test.")
            return

    # 2. WAVE 1: 3DGS
    wave1_scenes = [
        ("ballroom", resolve_video("Ballroom", "ballroom_1080p.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
        ("courtroom", resolve_video("Courtroom", "courtroom_1080p.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
        ("meetingroom", resolve_video("Meetingroom", "meetingroom_1080p.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
        ("auditorium", resolve_video("Auditorium", "auditorium_1080p.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
        ("ignatius", resolve_video("Ignatius", "ignatius_1080p.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
        ("enhanced_interior_tour", resolve_video("Tour", "enhanced_interior_tour_1080p.mp4"), "gaussian_splat", {"include_mesh": True, "use_bilateral_grid": True}),
        ("house_test_30s", resolve_video("House", "house_test_30s.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
        ("bedroom_vid", resolve_video("Bedroom", "bedroom_vid.mp4"), "gaussian_splat", {"use_bilateral_grid": True}),
    ]

    # 3. WAVE 2: PBR Meshes via Depth Fusion
    wave2_scenes = [
        ("ballroom_mesh", resolve_video("Ballroom", "ballroom_1080p.mp4"), "photo", {"mesh_route": "depth_fusion"}),
        ("courtroom_mesh", resolve_video("Courtroom", "courtroom_1080p.mp4"), "photo", {"mesh_route": "depth_fusion"}),
        ("meetingroom_mesh", resolve_video("Meetingroom", "meetingroom_1080p.mp4"), "photo", {"mesh_route": "depth_fusion"}),
        ("house_mesh", resolve_video("House", "house_test_30s.mp4"), "photo", {"mesh_route": "depth_fusion"}),
    ]

    if args.wave in ("1", "all"):
        print("\n*******************************************************")
        print("[PHASE 2] EXECUTING WAVE 1 — 3D GAUSSIAN SPLATTING")
        print("*******************************************************")
        for sname, vpath, stype, opts in wave1_scenes:
            res = run_job_with_retries(
                scene_name=sname,
                video_path=vpath,
                scan_type=stype,
                quality="standard",
                options=opts,
                max_attempts=2,
            )
            if res and res.get("status") == "completed":
                completed_jobs.append(res)
            else:
                failed_jobs.append({"scene": sname, "result": res})

    if args.wave in ("2", "all"):
        print("\n*******************************************************")
        print("[PHASE 3] EXECUTING WAVE 2 — PBR DEPTH FUSION MESHES")
        print("*******************************************************")
        for sname, vpath, stype, opts in wave2_scenes:
            res = run_job_with_retries(
                scene_name=sname,
                video_path=vpath,
                scan_type=stype,
                quality="standard",
                options=opts,
                max_attempts=2,
            )
            if res and res.get("status") == "completed":
                completed_jobs.append(res)
            else:
                failed_jobs.append({"scene": sname, "result": res})

    # Summary
    print("\n=======================================================")
    print("SHOWCASE BATCH EXECUTION SUMMARY")
    print("=======================================================")
    print(f"Completed Jobs: {len(completed_jobs)}")
    for j in completed_jobs:
        print(f" - {j.get('id', 'N/A')[:8]} | Scene: {j.get('original_filename', 'N/A')} | Runtime: {j.get('runtime_seconds')}s | Peak VRAM: {j.get('peak_vram_mb')} MB | Proof: {j.get('proof_sheet')}")

    if failed_jobs:
        print(f"\nFailed / Skipped Jobs: {len(failed_jobs)}")
        for f in failed_jobs:
            print(f" - Scene: {f['scene']} | Result: {f['result']}")

if __name__ == "__main__":
    main()
