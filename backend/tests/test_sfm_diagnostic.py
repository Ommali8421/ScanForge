"""
Unit tests for P2b Diagnostic Pass and Low-Texture Filtering in ColmapSfMStage.
"""

import json
import sqlite3
import numpy as np
import pytest
from pathlib import Path

from app.pipelines.common.sfm_colmap import (
    ColmapSfMStage,
    _quaternion_to_rotation_matrix,
    _image_ids_to_pair_id,
    _parse_frame_index,
)
from app.pipelines.base import JobContext, CancelToken


def test_quaternion_to_rotation_matrix():
    # Identity quaternion [1, 0, 0, 0]
    r = _quaternion_to_rotation_matrix([1.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(r, np.eye(3), atol=1e-6)

    # 90 degree rotation around Z: cos(45)=sqrt(2)/2, sin(45)=sqrt(2)/2
    s = np.sqrt(2) / 2
    rz = _quaternion_to_rotation_matrix([s, 0.0, 0.0, s])
    expected = np.array([
        [0.0, -1.0, 0.0],
        [1.0,  0.0, 0.0],
        [0.0,  0.0, 1.0]
    ])
    np.testing.assert_allclose(rz, expected, atol=1e-6)


def test_image_ids_to_pair_id():
    p1 = _image_ids_to_pair_id(1, 2)
    p2 = _image_ids_to_pair_id(2, 1)
    assert p1 == p2
    assert p1 == 2147483647 * 1 + 2


def test_parse_frame_index():
    assert _parse_frame_index("frame_000042.jpg") == 42
    assert _parse_frame_index("img_123.png") == 123
    assert _parse_frame_index("photo.jpg") == 0


def test_low_texture_filtering(tmp_path):
    stage = ColmapSfMStage()
    db_path = tmp_path / "colmap.db"
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()

    # Create dummy images in frames_dir
    (frames_dir / "frame_000001.jpg").write_text("dummy1")
    (frames_dir / "frame_000002.jpg").write_text("dummy2")
    (frames_dir / "frame_000003.jpg").write_text("dummy3")

    # Create sqlite database with keypoints
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE images (image_id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("CREATE TABLE keypoints (image_id INTEGER PRIMARY KEY, rows INTEGER);")
    cursor.execute("CREATE TABLE descriptors (image_id INTEGER PRIMARY KEY);")

    # Insert 3 frames: frame 1 has 1500 kp, frame 2 has 35 kp (low texture), frame 3 has 2000 kp
    cursor.execute("INSERT INTO images VALUES (1, 'frame_000001.jpg'), (2, 'frame_000002.jpg'), (3, 'frame_000003.jpg');")
    cursor.execute("INSERT INTO keypoints VALUES (1, 1500), (2, 35), (3, 2000);")
    conn.commit()
    conn.close()

    ctx = JobContext(
        job_id="test_filter",
        workdir=tmp_path,
        params={},
        cancel_token=CancelToken(),
        progress_cb=lambda s, p, m: None,
        log_cb=lambda m: None
    )
    dropped = stage._filter_low_texture_frames(
        db_path=db_path,
        frames_dir=frames_dir,
        min_keypoints=100,
        ctx=ctx
    )

    assert len(dropped) == 1
    assert dropped[0]["filename"] == "frame_000002.jpg"
    assert dropped[0]["keypoint_count"] == 35
    assert dropped[0]["frame_index"] == 2

    # Check frame was removed from frames_dir and moved to dropped_low_texture_frames
    assert not (frames_dir / "frame_000002.jpg").exists()
    assert (tmp_path / "dropped_low_texture_frames" / "frame_000002.jpg").exists()
    assert (frames_dir / "frame_000001.jpg").exists()
    assert (frames_dir / "frame_000003.jpg").exists()

    # Check database cleanup
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT image_id FROM images;")
    remaining_ids = [r[0] for r in cursor.fetchall()]
    conn.close()
    assert 2 not in remaining_ids
    assert set(remaining_ids) == {1, 3}


def test_motion_and_jump_analysis(tmp_path):
    stage = ColmapSfMStage()
    db_path = tmp_path / "colmap.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE images (image_id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("CREATE TABLE keypoints (image_id INTEGER PRIMARY KEY, rows INTEGER);")
    cursor.execute("CREATE TABLE two_view_geometries (pair_id INTEGER PRIMARY KEY, rows INTEGER);")
    
    # 3 frames
    cursor.execute("INSERT INTO images VALUES (1, 'f_001.jpg'), (2, 'f_002.jpg'), (3, 'f_003.jpg');")
    cursor.execute("INSERT INTO keypoints VALUES (1, 1200), (2, 1300), (3, 1100);")
    pair12 = _image_ids_to_pair_id(1, 2)
    pair23 = _image_ids_to_pair_id(2, 3)
    cursor.execute(f"INSERT INTO two_view_geometries VALUES ({pair12}, 250), ({pair23}, 180);")
    conn.commit()
    conn.close()

    # Create 10 cameras: first 9 spaced 0.1m apart, 10th spaced 1.0m apart (10x median!)
    cameras = []
    for i in range(1, 10):
        cameras.append({
            "image_id": i,
            "name": f"f_{i:03d}.jpg",
            "frame_index": i,
            "rotation_matrix": np.eye(3),
            "cam_center": np.array([float(i) * 0.1, 0.0, 0.0])
        })
    cameras.append({
        "image_id": 10,
        "name": "f_010.jpg",
        "frame_index": 10,
        "rotation_matrix": np.eye(3),
        "cam_center": np.array([1.9, 0.0, 0.0])  # jump: 1.0m vs 0.1m (10x median!)
    })

    motion_summary, jumps_flagged, sift_map = stage._analyze_motion_and_matches(cameras, db_path)

    assert sift_map["f_001.jpg"] == 1200
    assert len(motion_summary["consecutive_pairs"]) == 9
    assert len(jumps_flagged) == 1
    assert jumps_flagged[0]["frame_a"] == "f_009.jpg"
    assert jumps_flagged[0]["frame_b"] == "f_010.jpg"
    assert jumps_flagged[0]["median_multiple"] > 5.0
