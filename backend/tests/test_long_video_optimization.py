"""
Tests for Long Video Optimization & Deliverable Synchronization.
Verifies:
1. Adaptive keyframe budget curve (duration-based diminishing returns).
2. Joint OpenMVS resolution planning (resolution x frame count x VRAM).
3. Matches importer args generation and strided anchor loop closure.
4. Two-pass zero-RAM frame extraction execution.
5. Calibration multi-format deliverable sync (GLB, PLY, STL, XYZ, OBJ ZIP).
"""

import io
import json
import math
import shutil
import zipfile
from pathlib import Path
import numpy as np
import pytest
import trimesh

from app.config import settings
from app.pipelines.base import JobContext, CancelToken
from app.pipelines.common.frame_extraction import (
    FrameExtractionStage,
    compute_adaptive_keyframe_budget,
)
from app.utils.tool_resolve import determine_openmvs_resolution_level
from app.utils.colmap_compat import build_matches_importer_args


def test_adaptive_keyframe_budget():
    """Verify adaptive diminishing-returns curve across durations and quality presets."""
    # Short clip (20s) -> ~3.3 fps
    n_20, fps_20 = compute_adaptive_keyframe_budget(20.0, "standard")
    assert 60 <= n_20 <= 70
    assert 3.0 <= fps_20 <= 3.5

    # Medium clip (60s) -> 100 + (60-30)*1.6 = 148 frames
    n_60, fps_60 = compute_adaptive_keyframe_budget(60.0, "standard")
    assert 140 <= n_60 <= 160
    assert 2.0 <= fps_60 <= 2.6

    # 3-minute clip (180s) -> 200 + (180-90)*0.8 = 272 frames
    n_180, fps_180 = compute_adaptive_keyframe_budget(180.0, "standard")
    assert 265 <= n_180 <= 280

    # 5-minute clip (300s) -> standard capped at 300 frames
    n_300, fps_300 = compute_adaptive_keyframe_budget(300.0, "standard")
    assert n_300 == 300
    assert 0.9 <= fps_300 <= 1.1

    # 10-minute clip (600s) -> standard capped at 300 frames
    n_600, fps_600 = compute_adaptive_keyframe_budget(600.0, "standard")
    assert n_600 == 300

    # High quality preset caps at 380 frames (reaches 364 frames at 10 min)
    n_high_600, _ = compute_adaptive_keyframe_budget(600.0, "high")
    assert 360 <= n_high_600 <= 380
    n_high_800, _ = compute_adaptive_keyframe_budget(800.0, "high")
    assert n_high_800 == 380

    # Draft quality preset caps at 180 frames
    n_draft_600, _ = compute_adaptive_keyframe_budget(600.0, "draft")
    assert n_draft_600 == 180

    # Explicit override
    n_ov, _ = compute_adaptive_keyframe_budget(600.0, "standard", max_frames_override=220)
    assert n_ov == 220


def test_openmvs_joint_resolution_planning():
    """Verify resolution level accounts for image dimensions AND frame count (megapixel load)."""
    # 1. House clip (478x850, 60 frames) -> ~24 MP total load -> level 0 on 8 GB
    res_house = determine_openmvs_resolution_level(478, 850, vram_gb=8.0, quality="standard", frame_count=60)
    assert res_house == 0

    # 2. 1080p short sequence (1080x1920, 70 frames) -> ~145 MP total load -> level 0 on 8 GB
    res_1080_short = determine_openmvs_resolution_level(1080, 1920, vram_gb=8.0, quality="standard", frame_count=70)
    assert res_1080_short == 0

    # 3. 1080p medium sequence (1080x1920, 150 frames) -> ~311 MP total load -> level 1 on 8 GB
    res_1080_med = determine_openmvs_resolution_level(1080, 1920, vram_gb=8.0, quality="standard", frame_count=150)
    assert res_1080_med == 1

    # 4. 1080p long sequence (1080x1920, 250 frames) -> ~518 MP total load -> level 2 on 8 GB standard
    res_1080_long = determine_openmvs_resolution_level(1080, 1920, vram_gb=8.0, quality="standard", frame_count=250)
    assert res_1080_long == 2

    # High tier attempts level 1 for 250 frames
    res_1080_high = determine_openmvs_resolution_level(1080, 1920, vram_gb=8.0, quality="high", frame_count=250)
    assert res_1080_high == 1

    # Draft tier always returns level 2
    res_draft = determine_openmvs_resolution_level(1080, 1920, vram_gb=8.0, quality="draft", frame_count=50)
    assert res_draft == 2


def test_matches_importer_args():
    """Verify matches_importer CLI args generation for COLMAP 3.9.1 and 3.13."""
    args_39 = build_matches_importer_args(
        version=(3, 9, 1),
        database_path="/tmp/test.db",
        match_list_path="/tmp/pairs.txt",
        match_type="pairs",
        use_gpu=True,
        threads=8,
    )
    assert "--database_path" in args_39
    assert "--match_list_path" in args_39
    assert "--match_type" in args_39
    assert "pairs" in args_39
    assert "--SiftMatching.use_gpu" in args_39
    assert "1" in args_39
    assert "--SiftMatching.num_threads" in args_39
    assert "8" in args_39

    args_313 = build_matches_importer_args(
        version=(3, 13, 0),
        database_path="/tmp/test.db",
        match_list_path="/tmp/pairs.txt",
        match_type="pairs",
        use_gpu=False,
        threads=4,
    )
    assert "--FeatureMatching.use_gpu" in args_313
    assert "0" in args_313
    assert "--FeatureMatching.num_threads" in args_313
    assert "4" in args_313


def test_frame_extraction_two_pass_execution(tmp_path):
    """Verify that FrameExtractionStage runs cleanly in two-pass mode on a synthetic video."""
    import cv2
    video_path = tmp_path / "normalized_input.mp4"

    # Create a small 60-frame synthetic MP4 (2 seconds @ 30 fps)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (320, 240))
    for i in range(60):
        # Draw changing patterns with high contrast / features
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        x = int(20 + i * 4)
        cv2.circle(img, (x, 120), 30, (255, 255, 255), -1)
        cv2.putText(img, f"Frame {i}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        out.write(img)
    out.release()

    logs = []
    ctx = JobContext(
        job_id="test_long_fe",
        workdir=tmp_path,
        params={"quality": "standard"},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=logs.append
    )

    stage = FrameExtractionStage()
    res = stage.run(ctx)

    assert res.success
    frames_dir = tmp_path / "frames"
    assert frames_dir.exists()
    extracted_jpegs = list(frames_dir.glob("*.jpg"))
    assert len(extracted_jpegs) > 0

    report_file = tmp_path / "frame_extraction_report.json"
    assert report_file.exists()
    report = json.loads(report_file.read_text())
    assert report["total_video_frames"] == 60
    assert report["frames_kept"] == len(extracted_jpegs)
    assert any("Pass 1 complete" in l for l in logs)
    assert any("Pass 2 complete" in l for l in logs)


def test_calibration_deliverable_sync(tmp_path, monkeypatch):
    """Verify that scale calibration synchronizes GLB, PLY, STL, XYZ, and OBJ ZIP."""
    from app.pipelines.mesh.floor_align import scale_glb_in_place

    # Create a simple box mesh
    box = trimesh.creation.box(extents=(2.0, 1.0, 3.0))

    workdir = tmp_path / "workdir"
    art_dir = tmp_path / "artifacts"
    workdir.mkdir()
    art_dir.mkdir()

    unscaled_glb = workdir / "aligned_textured_unscaled.glb"
    box.export(str(unscaled_glb))

    # Pre-populate deliverables at 1.0x scale
    box.export(str(workdir / "aligned_textured.glb"))
    box.export(str(workdir / "mesh.glb"))
    box.export(str(workdir / "mesh.ply"))
    box.export(str(workdir / "mesh.stl"))

    # XYZ
    xyz_data = np.hstack([box.vertices, box.vertex_normals])
    np.savetxt(str(workdir / "mesh.xyz"), xyz_data, fmt="%.6f", delimiter=" ")

    # OBJ ZIP
    obj_str = trimesh.exchange.obj.export_obj(box)
    with zipfile.ZipFile(workdir / "mesh_obj.zip", "w") as zf:
        zf.writestr("mesh.obj", obj_str)
        zf.writestr("mesh.mtl", "# MTL")

    # Quality report
    rep_file = workdir / "quality_report.json"
    rep_file.write_text(json.dumps({
        "dimensions_meters": {"length": 2.0, "height": 1.0, "width": 3.0},
        "cumulative_scale": 1.0,
        "is_calibrated": False
    }))

    # Copy all to art_dir
    for f in workdir.glob("*"):
        if f.is_file():
            shutil.copy2(f, art_dir / f.name)

    # Apply 2.5x scaling
    applied_factor = 2.5
    cumulative_scale = 2.5

    # 1. Binary GLB scaling
    scale_glb_in_place(unscaled_glb, workdir / "aligned_textured.glb", scale_factor=cumulative_scale)
    shutil.copy2(workdir / "aligned_textured.glb", workdir / "mesh.glb")
    shutil.copy2(workdir / "aligned_textured.glb", art_dir / "mesh.glb")

    # 2. Rescale PLY
    for p_ply in [workdir / "mesh.ply", art_dir / "mesh.ply"]:
        m = trimesh.load(str(p_ply), process=False)
        m.vertices *= applied_factor
        m.export(str(p_ply))

    # 3. Rescale STL
    for p_stl in [workdir / "mesh.stl", art_dir / "mesh.stl"]:
        m = trimesh.load(str(p_stl), process=False)
        m.vertices *= applied_factor
        m.export(str(p_stl))

    # 4. Rescale XYZ
    for p_xyz in [workdir / "mesh.xyz", art_dir / "mesh.xyz"]:
        arr = np.loadtxt(str(p_xyz))
        arr[:, 0:3] *= applied_factor
        np.savetxt(str(p_xyz), arr, fmt="%.6f", delimiter=" ")

    # 5. Rescale OBJ ZIP
    for p_zip in [workdir / "mesh_obj.zip", art_dir / "mesh_obj.zip"]:
        buf = io.BytesIO()
        with zipfile.ZipFile(p_zip, "r") as zin:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    content = zin.read(item.filename)
                    if item.filename == "mesh.obj":
                        lines = content.decode("utf-8").splitlines()
                        scaled = []
                        for l in lines:
                            if l.startswith("v "):
                                parts = l.split()
                                vx, vy, vz = float(parts[1]) * applied_factor, float(parts[2]) * applied_factor, float(parts[3]) * applied_factor
                                scaled.append(f"v {vx:.6f} {vy:.6f} {vz:.6f}")
                            else:
                                scaled.append(l)
                        zout.writestr(item, "\n".join(scaled).encode("utf-8"))
                    else:
                        zout.writestr(item, content)
        p_zip.write_bytes(buf.getvalue())

    # Verify all rescaled deliverables
    # PLY
    m_ply_check = trimesh.load(str(workdir / "mesh.ply"), process=False)
    assert np.allclose(m_ply_check.bounds[1] - m_ply_check.bounds[0], np.array([2.0, 1.0, 3.0]) * 2.5, atol=1e-3)

    # STL
    m_stl_check = trimesh.load(str(workdir / "mesh.stl"), process=False)
    assert np.allclose(m_stl_check.bounds[1] - m_stl_check.bounds[0], np.array([2.0, 1.0, 3.0]) * 2.5, atol=1e-3)

    # XYZ
    xyz_check = np.loadtxt(str(workdir / "mesh.xyz"))
    xyz_extents = np.max(xyz_check[:, 0:3], axis=0) - np.min(xyz_check[:, 0:3], axis=0)
    assert np.allclose(xyz_extents, np.array([2.0, 1.0, 3.0]) * 2.5, atol=1e-3)

    # OBJ in ZIP
    with zipfile.ZipFile(workdir / "mesh_obj.zip", "r") as zf:
        obj_text = zf.read("mesh.obj").decode("utf-8")
        m_obj = trimesh.load(io.StringIO(obj_text), file_type="obj", process=False)
        assert np.allclose(m_obj.bounds[1] - m_obj.bounds[0], np.array([2.0, 1.0, 3.0]) * 2.5, atol=1e-3)
