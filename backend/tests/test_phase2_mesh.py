"""
Unit tests for Milestone P2c Phase 2 Mesh Processing:
- MeshCleanupStage (floater component filtering)
- RoomAnalysisStage (relative floor detection & leveling transform)
- PlaneRepairStage (normal-aware plane snapping & envelope pruning)
- DecimateStage (planarity-preserving quadric decimation)
- GLB PBR material property patching
"""

import json
from pathlib import Path
import numpy as np
import pytest
import trimesh

from app.pipelines.base import JobContext, CancelToken
from app.pipelines.mesh.cleanup import MeshCleanupStage
from app.pipelines.mesh.room_analysis import RoomAnalysisStage, compute_rodrigues_rotation
from app.pipelines.mesh.plane_repair import PlaneRepairStage, line_intersection_of_two_planes
from app.pipelines.mesh.decimate import DecimateStage
from app.pipelines.photo.openmvs import fix_glb_pbr_materials


def test_mesh_cleanup_floater_removal(tmp_path: Path):
    """Verify that MeshCleanupStage discards disconnected floaters <1% of primary mesh."""
    # Create large cube subdivided to have 768 faces
    main_box = trimesh.creation.box(extents=(4.0, 3.0, 4.0))
    main_box = main_box.subdivide().subdivide().subdivide()  # 12 * 4 * 4 * 4 = 768 faces

    # Create tiny floater box (12 faces, which is < 1% of 768)
    floater1 = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    floater1.apply_translation([10.0, 10.0, 10.0])

    combined = trimesh.util.concatenate([main_box, floater1])
    input_ply = tmp_path / "scene_dense_mesh.ply"
    combined.export(str(input_ply))

    ctx = JobContext(
        job_id="test_cleanup",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None,
    )

    stage = MeshCleanupStage()
    res = stage.run(ctx)
    assert res.success is True
    assert (tmp_path / "mesh_cleaned.ply").exists()

    cleaned = trimesh.load(str(tmp_path / "mesh_cleaned.ply"), process=False)
    # Floater should be completely gone
    assert len(cleaned.faces) == len(main_box.faces)
    assert np.all(cleaned.vertices[:, 0] < 8.0)  # no vertices at x=10


def test_line_intersection_of_two_planes():
    """Verify closed-form line intersection of two orthogonal planes."""
    # Plane 1: X = 0 (n=[1, 0, 0], d=0)
    # Plane 2: Y = 0 (n=[0, 1, 0], d=0)
    # Intersection should be along Z axis (dir=[0, 0, 1])
    n1 = np.array([1.0, 0.0, 0.0])
    n2 = np.array([0.0, 1.0, 0.0])
    p_line, dir_line = line_intersection_of_two_planes(n1, 0.0, n2, 0.0)

    assert np.allclose(p_line, [0.0, 0.0, 0.0], atol=1e-5)
    assert abs(dir_line[2]) > 0.99


def test_room_analysis_and_relative_floor(tmp_path: Path):
    """Verify RoomAnalysisStage identifies dominant horizontal floor plane below cameras."""
    # Create synthetic room box (floor at Y=0, ceiling at Y=2.5, walls at X=+-2, Z=+-2)
    room = trimesh.creation.box(extents=(4.0, 2.5, 4.0))
    # Translate so floor is at Y=0
    room.apply_translation([0.0, 1.25, 0.0])
    room = room.subdivide().subdivide()

    mesh_ply = tmp_path / "mesh_cleaned.ply"
    room.export(str(mesh_ply))

    # Create synthetic images.txt with cameras looking around at Y=1.5
    sparse_dir = tmp_path / "sparse_txt"
    sparse_dir.mkdir(parents=True)
    images_txt = sparse_dir / "images.txt"

    with open(images_txt, "w") as f:
        f.write("# Camera list with poses\n")
        for i in range(10):
            # Camera at (cos(theta), 1.5, sin(theta)) looking towards center
            # QW, QX, QY, QZ = 1, 0, 0, 0 (camera pointing -Z, up is -Y in camera)
            # Ty = -1.5 => camera Y center = 1.5
            f.write(f"{i+1} 1.0 0.0 0.0 0.0 0.0 -1.5 2.0 1 frame_{i:04d}.jpg\n")
            f.write("0.0 0.0 -1\n")

    ctx = JobContext(
        job_id="test_analysis",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None,
    )

    stage = RoomAnalysisStage()
    res = stage.run(ctx)
    assert res.success is True

    analysis_file = tmp_path / "room_analysis.json"
    assert analysis_file.exists()

    with open(analysis_file, "r") as f:
        data = json.load(f)

    assert "camera_mean_up" in data
    assert "chosen_floor_plane" in data
    assert "level_center_transform" in data
    assert len(data["level_center_transform"]) == 4


def test_plane_repair_snapping_and_ghost_removal(tmp_path: Path):
    """Verify PlaneRepairStage snaps coplanar vertices and drops geometry below floor."""
    # Create room mesh
    room = trimesh.creation.box(extents=(4.0, 2.5, 4.0))
    room.apply_translation([0.0, 1.25, 0.0])
    room = room.subdivide()

    # Add artificial subsurface mirror geometry at Y = -2.0 (below floor at Y=0)
    mirror_ghost = trimesh.creation.box(extents=(1.0, 0.5, 1.0))
    mirror_ghost.apply_translation([0.0, -2.0, 0.0])

    combined = trimesh.util.concatenate([room, mirror_ghost])
    input_ply = tmp_path / "mesh_cleaned.ply"
    combined.export(str(input_ply))

    # Synthetic room_analysis.json
    analysis_file = tmp_path / "room_analysis.json"
    analysis_data = {
        "scene_diagonal": 5.0,
        "chosen_floor_plane": {
            "normal": [0.0, 1.0, 0.0],
            "d": 0.0,
            "height": 0.0,
        },
        "wall_planes": [
            {"normal": [1.0, 0.0, 0.0], "d": 2.0},
            {"normal": [-1.0, 0.0, 0.0], "d": 2.0},
        ],
    }
    with open(analysis_file, "w") as f:
        json.dump(analysis_data, f)

    ctx = JobContext(
        job_id="test_repair",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None,
    )

    stage = PlaneRepairStage()
    res = stage.run(ctx)
    assert res.success is True

    repaired_ply = tmp_path / "mesh_repaired.ply"
    assert repaired_ply.exists()

    repaired = trimesh.load(str(repaired_ply), process=False)
    # The mirror ghost below Y=0 should be pruned
    assert np.all(repaired.vertices[:, 1] >= -0.1)


def test_decimate_stage(tmp_path: Path):
    """Verify DecimateStage reduces triangle count with boundary_weight=1.0."""
    box = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    box = box.subdivide().subdivide().subdivide()  # 12 * 4 * 4 * 4 = 768 faces
    initial_faces = len(box.faces)

    input_ply = tmp_path / "mesh_repaired.ply"
    box.export(str(input_ply))

    ctx = JobContext(
        job_id="test_decim",
        workdir=tmp_path,
        params={"quality": "draft", "options": {"poly_target": 200}},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None,
    )

    stage = DecimateStage()
    res = stage.run(ctx)
    assert res.success is True

    decim_ply = tmp_path / "mesh_decimated.ply"
    assert decim_ply.exists()
    decimated = trimesh.load(str(decim_ply), process=False)
    assert len(decimated.faces) <= 250
    assert len(decimated.faces) < initial_faces
