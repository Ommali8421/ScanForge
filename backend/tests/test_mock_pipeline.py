"""
Tests for mock pipeline generation
"""

from pathlib import Path
from app.pipelines.mock import (
    generate_procedural_room_obj,
    generate_synthetic_splat_ply,
    generate_compact_splat,
    create_mock_pipeline,
)
from app.pipelines.base import JobContext, CancelToken


def test_procedural_room_obj_generation(tmp_path: Path):
    obj_path = tmp_path / "room.obj"
    generate_procedural_room_obj(obj_path, scale=1.5)

    assert obj_path.exists()
    content = obj_path.read_text()
    assert "v " in content  # Vertices
    assert "f " in content  # Faces
    assert "mtllib room.mtl" in content

    mtl_path = tmp_path / "room.mtl"
    assert mtl_path.exists()
    assert "newmtl InteriorMaterial" in mtl_path.read_text()


def test_synthetic_splat_generation(tmp_path: Path):
    ply_path = tmp_path / "splat.ply"
    generate_synthetic_splat_ply(ply_path, num_points=50, scale=1.0)
    assert ply_path.exists()
    header = ply_path.read_text()
    assert "element vertex 50" in header
    assert "property float opacity" in header

    splat_path = tmp_path / "splat.splat"
    generate_compact_splat(splat_path, num_splats=20, scale=1.0)
    assert splat_path.exists()
    assert splat_path.stat().st_size == 20 * 32  # 32 bytes per splat


def test_mock_pipeline_execution(tmp_path: Path):
    pipeline = create_mock_pipeline("photo")
    assert len(pipeline.stages) == 12

    # Check texturing runs right before export (Amendment 2)
    stage_names = [s.name for s in pipeline.stages]
    assert stage_names[-2] == "uv_texture"
    assert stage_names[-1] == "export"

    logs = []
    progress_updates = []
    ctx = JobContext(
        job_id="test-job-123",
        workdir=tmp_path,
        params={"scan_type": "photo", "output_formats": ["obj", "glb"]},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: progress_updates.append((s, p)),
        log_cb=lambda l: logs.append(l),
        cumulative_scale=1.0
    )

    pipeline.run(ctx)
    assert len(logs) > 0
    assert len(progress_updates) > 0
    assert (tmp_path / ".cache_export.json").exists()
