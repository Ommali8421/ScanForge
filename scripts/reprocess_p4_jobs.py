#!/usr/bin/env python3
"""
ScanForge Milestone P4 Benchmark Reprocessor
Clears downstream mesh caches and re-runs stages on RTX 4060 with fixed 1-pixel finite difference edge checks.
"""

import sys
import shutil
from pathlib import Path

# Add backend to path
sys.path.insert(0, "/workspace/backend")

from app.queue.tasks import run_pipeline_task
from app.services.storage import storage_service


def clean_and_run_splat_mesh(job_id: str):
    print(f"\n==========================================")
    print(f"REPROCESSING 3DGS MESH INCLUSIVE: {job_id}")
    print(f"==========================================")
    workdir = storage_service.get_job_workdir(job_id)
    stages = [
        "splat_mesher", "mesh_cleanup", "plane_repair", "decimate",
        "openmvs_texture", "floor_align_scale", "floor_plan",
        "quality_report", "mesh_export"
    ]
    for s in stages:
        c = workdir / f".cache_{s}.json"
        if c.exists():
            c.unlink()
            print(f"Removed cache: {c.name}")

    patterns = [
        "mesh_splat_raw.ply", "mesh_dense.ply", "mesh_cleaned.ply",
        "mesh_repaired.ply", "mesh_decimated.ply", "scene_textured.*",
        "aligned_*", "mesh.*", "preview_textured.glb", "floor_plan.*",
        "floor_alignment.json"
    ]
    for pat in patterns:
        for f in workdir.glob(pat):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)

    run_pipeline_task(job_id)
    print(f"Completed {job_id} successfully!")


def clean_and_run_depth_fusion(job_id: str):
    print(f"\n==========================================")
    print(f"REPROCESSING DEPTH FUSION ROUTE B: {job_id}")
    print(f"==========================================")
    workdir = storage_service.get_job_workdir(job_id)
    stages = [
        "depth_align", "tsdf_fusion", "mesh_cleanup", "plane_repair", "decimate",
        "openmvs_texture", "floor_align_scale", "floor_plan",
        "quality_report", "mesh_export"
    ]
    for s in stages:
        c = workdir / f".cache_{s}.json"
        if c.exists():
            c.unlink()
            print(f"Removed cache: {c.name}")

    patterns = [
        "mesh_tsdf_raw.ply", "mesh_dense.ply", "mesh_cleaned.ply",
        "mesh_repaired.ply", "mesh_decimated.ply", "scene_textured.*",
        "aligned_*", "mesh.*", "preview_textured.glb", "floor_plan.*",
        "floor_alignment.json"
    ]
    for pat in patterns:
        for f in workdir.glob(pat):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)

    depth_aligned = workdir / "depth_aligned"
    if depth_aligned.exists():
        shutil.rmtree(depth_aligned)
        print("Removed depth_aligned directory.")

    run_pipeline_task(job_id)
    print(f"Completed {job_id} successfully!")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target in ("tour_splat_mesh", "all"):
        clean_and_run_splat_mesh("299db6af-de22-4055-af38-b2c615e076e7")
    if target in ("tour_route_b", "all"):
        clean_and_run_depth_fusion("bd00e5c7-d4f5-4c6f-b9f2-b59bbabedc49")
    if target in ("house_route_b", "all"):
        clean_and_run_depth_fusion("d1fd0269-4325-4f98-9c80-6c70aedbc19c")

