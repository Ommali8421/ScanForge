"""
Execute Phase 3 Stages on Real Jobs (House and Tour).
Stages executed:
1. FloorAlignAndScaleStage
2. MeshExportStage
3. QualityReportStage
"""

import sys
import os
import json
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, "/workspace/backend")

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.mesh.floor_align import FloorAlignAndScaleStage
from app.pipelines.mesh.exporters import MeshExportStage
from app.pipelines.mesh.quality_report import QualityReportStage
from app.utils.logging import logger

JOB_IDS = [
    "a78fc585-4120-48b5-8512-17d2b6afa8f2",  # House clip
    "4945096f-639c-40bb-97bc-2ac258e8b9d6",  # Tour clip
]

def run_phase3_on_job(job_id: str):
    workdir = Path(f"/data/jobs/{job_id}")
    if not workdir.exists():
        raise FileNotFoundError(f"Job workdir {workdir} does not exist")

    print(f"\n=======================================================")
    print(f"=== RUNNING PHASE 3 ON JOB {job_id} ===")
    print(f"=======================================================")

    cancel_token = CancelToken()
    def progress_cb(stage: str, pct: int, msg: str):
        print(f"[{stage}] {pct}% - {msg}")
    def log_cb(msg: str):
        print(f"[LOG] {msg}")

    # Default job params
    params = {
        "options": {
            "up_axis": "y",
            "units": "m",
        },
        "up_axis": "y",
        "units": "m",
        "output_formats": ["glb", "gltf", "obj", "ply", "stl", "xyz", "fbx", "usdz"],
        "formats": ["glb", "gltf", "obj", "ply", "stl", "xyz", "fbx", "usdz"],
    }

    ctx = JobContext(
        job_id=job_id,
        workdir=workdir,
        params=params,
        cancel_token=cancel_token,
        progress_cb=progress_cb,
        log_cb=log_cb,
        cumulative_scale=1.0,
    )

    # 1. FloorAlignAndScaleStage
    t0 = time.time()
    align_stage = FloorAlignAndScaleStage()
    align_res = align_stage.run(ctx)
    t_align = time.time() - t0
    print(f"FloorAlignAndScaleStage finished in {t_align:.2f}s: success={align_res.success}")
    if not align_res.success:
        raise RuntimeError(f"FloorAlignAndScaleStage failed on {job_id}")

    # 2. MeshExportStage
    t0 = time.time()
    export_stage = MeshExportStage()
    export_res = export_stage.run(ctx)
    t_export = time.time() - t0
    print(f"MeshExportStage finished in {t_export:.2f}s: success={export_res.success}")
    print(f"Exported files: {[str(p.name) for p in export_res.output_files]}")
    if not export_res.success:
        raise RuntimeError(f"MeshExportStage failed on {job_id}")

    # 3. QualityReportStage
    t0 = time.time()
    report_stage = QualityReportStage()
    report_res = report_stage.run(ctx)
    t_report = time.time() - t0
    print(f"QualityReportStage finished in {t_report:.2f}s: success={report_res.success}")
    if not report_res.success:
        raise RuntimeError(f"QualityReportStage failed on {job_id}")

    # Print summary of quality_report.json
    rep_path = workdir / "quality_report.json"
    with open(rep_path, "r") as f:
        rep_data = json.load(f)
    print(f"Quality Report Summary for {job_id}:")
    print(json.dumps(rep_data, indent=2))

if __name__ == "__main__":
    for jid in JOB_IDS:
        run_phase3_on_job(jid)
    print("\nAll Phase 3 stages successfully executed on real jobs!")
