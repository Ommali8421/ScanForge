#!/usr/bin/env python3
"""
Run Milestone P2c Phase 1 (OpenMVS Interface, Densify, ReconstructMesh)
on the real enhanced tour job (dde47794-b416-4730-9b46-60aed5299c30).
"""

import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, "/workspace/backend")

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.photo.openmvs import (
    OpenMVSInterfaceStage,
    OpenMVSDensifyStage,
    OpenMVSRMeshStage,
)

def log_cb(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def prog_cb(stage: str, pct: int, msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] [PROGRESS {pct}%] {stage}: {msg}", flush=True)

def main():
    workdir = Path("/data/jobs/dde47794-b416-4730-9b46-60aed5299c30")
    if not workdir.exists():
        print(f"Error: workdir {workdir} does not exist!", flush=True)
        return 1

    ctx = JobContext(
        job_id="dde47794-b416-4730-9b46-60aed5299c30",
        workdir=workdir,
        params={"quality": "standard"},
        cancel_token=CancelToken(),
        progress_cb=prog_cb,
        log_cb=log_cb,
    )

    print("=" * 65, flush=True)
    print(" ScanForge P2c Phase 1 Real Execution: Enhanced Interior Tour", flush=True)
    print("=" * 65, flush=True)

    # 1. Interface Stage
    t0 = time.time()
    s1 = OpenMVSInterfaceStage()
    res1 = s1.run(ctx)
    t1 = time.time()
    print(f"Stage 1 (InterfaceCOLMAP) completed in {t1 - t0:.2f}s (Success={res1.success})", flush=True)

    # 2. Densify Stage
    s2 = OpenMVSDensifyStage()
    res2 = s2.run(ctx)
    t2 = time.time()
    print(f"Stage 2 (DensifyPointCloud) completed in {t2 - t1:.2f}s (Success={res2.success})", flush=True)
    print(f"   Points: {res2.metadata.get('point_count'):,}", flush=True)
    print(f"   Resolution Level: {res2.metadata.get('resolution_level')}", flush=True)

    # 3. Reconstruct Mesh Stage
    s3 = OpenMVSRMeshStage()
    res3 = s3.run(ctx)
    t3 = time.time()
    print(f"Stage 3 (ReconstructMesh) completed in {t3 - t2:.2f}s (Success={res3.success})", flush=True)
    print(f"   Vertices: {res3.metadata.get('vertex_count'):,}", flush=True)
    print(f"   Faces: {res3.metadata.get('face_count'):,}", flush=True)
    print(f"   Raw GLB: {res3.metadata.get('raw_glb')}", flush=True)

    print("=" * 65, flush=True)
    print(f" Total Phase 1 Runtime: {t3 - t0:.2f}s", flush=True)
    print("=" * 65, flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
