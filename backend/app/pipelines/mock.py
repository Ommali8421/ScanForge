"""
Mock Reconstruction Pipeline
Generates procedural interior room meshes (4 walls, floor, ceiling, furniture boxes)
and synthetic Gaussian Splats without requiring GPU or external binaries.
"""

import math
import struct
import time
from pathlib import Path
from typing import List, Dict, Any
from app.pipelines.base import Stage, StageResult, JobContext, Pipeline
from app.services.storage import storage_service
from app.services.job_service import add_artifact


def generate_procedural_room_obj(obj_path: Path, scale: float = 1.0):
    """
    Generate a 3D Wavefront OBJ representation of an interior room:
    Floor (greenish-gray), Ceiling (white), 4 Walls (off-white), Table box, Chair box.
    Scaled by the metric scale factor.
    """
    # Dimensions in meters
    w = 4.0 * scale   # X axis (width)
    l = 5.0 * scale   # Z axis (length)
    h = 2.6 * scale   # Y axis (height)

    # Vertices (x, y, z)
    vertices = [
        # Floor (0..3)
        (-w/2, 0, -l/2), (w/2, 0, -l/2), (w/2, 0, l/2), (-w/2, 0, l/2),
        # Ceiling (4..7)
        (-w/2, h, -l/2), (w/2, h, -l/2), (w/2, h, l/2), (-w/2, h, l/2),
        # Table Box (8..15) - center
        (-0.6*scale, 0, -0.4*scale), (0.6*scale, 0, -0.4*scale), (0.6*scale, 0, 0.4*scale), (-0.6*scale, 0, 0.4*scale),
        (-0.6*scale, 0.75*scale, -0.4*scale), (0.6*scale, 0.75*scale, -0.4*scale), (0.6*scale, 0.75*scale, 0.4*scale), (-0.6*scale, 0.75*scale, 0.4*scale),
        # Chair Box (16..23)
        (0.8*scale, 0, 0.2*scale), (1.2*scale, 0, 0.2*scale), (1.2*scale, 0, 0.6*scale), (0.8*scale, 0, 0.6*scale),
        (0.8*scale, 0.45*scale, 0.2*scale), (1.2*scale, 0.45*scale, 0.2*scale), (1.2*scale, 0.45*scale, 0.6*scale), (0.8*scale, 0.45*scale, 0.6*scale),
    ]

    # Faces (1-indexed quad triangles)
    faces = [
        # Floor (facing up)
        (1, 3, 2), (1, 4, 3),
        # Ceiling (facing down)
        (5, 6, 7), (5, 7, 8),
        # Wall Back (Z = -l/2)
        (1, 2, 6), (1, 6, 5),
        # Wall Front (Z = l/2)
        (4, 7, 3), (4, 8, 7),
        # Wall Left (X = -w/2)
        (1, 5, 8), (1, 8, 4),
        # Wall Right (X = w/2)
        (2, 3, 7), (2, 7, 6),
        # Table top
        (13, 14, 15), (13, 15, 16),
        # Table sides
        (9, 10, 14), (9, 14, 13),
        (10, 11, 15), (10, 15, 14),
        (11, 12, 16), (11, 16, 15),
        (12, 9, 13), (12, 13, 16),
        # Chair top
        (21, 22, 23), (21, 23, 24),
        # Chair sides
        (17, 18, 22), (17, 22, 21),
        (18, 19, 23), (18, 23, 22),
        (19, 20, 24), (19, 24, 23),
        (20, 17, 21), (20, 21, 24),
    ]

    mtl_filename = obj_path.with_suffix(".mtl").name
    with open(obj_path, "w") as f:
        f.write("# ScanForge Procedural Interior Room Mesh (Mock Engine)\n")
        f.write(f"mtllib {mtl_filename}\n")
        f.write("o Room\n")
        for v in vertices:
            f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        f.write("usemtl InteriorMaterial\n")
        f.write("s 1\n")
        for tri in faces:
            f.write(f"f {tri[0]} {tri[1]} {tri[2]}\n")

    # Companion MTL
    with open(obj_path.with_suffix(".mtl"), "w") as f:
        f.write("# Material for ScanForge Room\n")
        f.write("newmtl InteriorMaterial\n")
        f.write("Ka 0.2 0.2 0.2\n")
        f.write("Kd 0.85 0.82 0.78\n")
        f.write("Ks 0.1 0.1 0.1\n")
        f.write("d 1.0\n")
        f.write("illum 2\n")


def generate_synthetic_splat_ply(ply_path: Path, num_points: int = 500, scale: float = 1.0):
    """
    Generate a synthetic 3D Gaussian Splat PLY file representing room geometry.
    Header includes standard 3DGS properties (x, y, z, nx, ny, nz, f_dc_*, opacity, scale_*, rot_*).
    """
    w = 4.0 * scale
    l = 5.0 * scale
    h = 2.6 * scale

    header = f"""ply
format ascii 1.0
element vertex {num_points}
property float x
property float y
property float z
property float f_dc_0
property float f_dc_1
property float f_dc_2
property float opacity
property float scale_0
property float scale_1
property float scale_2
property float rot_0
property float rot_1
property float rot_2
property float rot_3
end_header
"""
    with open(ply_path, "w") as f:
        f.write(header)
        for i in range(num_points):
            # Points distributed along floor and walls
            t = (i / num_points) * 2 * math.pi
            r = (i % 5) / 5.0
            x = (math.cos(t) * (w / 2.2)) * r
            z = (math.sin(t) * (l / 2.2)) * r
            y = (float(i % 10) / 10.0) * h

            # Spherical harmonics dc RGB color
            f_dc_0 = 0.5 + 0.3 * math.sin(t)
            f_dc_1 = 0.5 + 0.2 * math.cos(t)
            f_dc_2 = 0.6
            opacity = 2.5
            s0 = -4.0
            s1 = -4.0
            s2 = -4.0
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {f_dc_0:.3f} {f_dc_1:.3f} {f_dc_2:.3f} {opacity:.2f} {s0:.2f} {s1:.2f} {s2:.2f} 1.0 0.0 0.0 0.0\n")


def generate_compact_splat(splat_path: Path, num_splats: int = 200, scale: float = 1.0):
    """Generate a binary .splat file for direct rendering in web viewer."""
    with open(splat_path, "wb") as f:
        for i in range(num_splats):
            # Position (3 floats = 12 bytes)
            x = math.sin(i * 0.1) * 1.5 * scale
            y = (i % 20) * 0.1 * scale
            z = math.cos(i * 0.1) * 1.5 * scale
            f.write(struct.pack("<fff", x, y, z))
            # Scales (3 floats = 12 bytes)
            f.write(struct.pack("<fff", 0.05, 0.05, 0.05))
            # Color RGBA (4 uint8 = 4 bytes)
            r = int((math.sin(i) * 0.5 + 0.5) * 255)
            g = int((math.cos(i) * 0.5 + 0.5) * 255)
            b = 200
            a = 255
            f.write(struct.pack("<BBBB", r, g, b, a))
            # Rotation quaternion (4 uint8 normalized = 4 bytes)
            f.write(struct.pack("<BBBB", 128, 128, 128, 255))


class MockIngestStage(Stage):
    name = "ingest"
    weight = 0.5

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Ingest] Validating uploaded archive and video stream...")
        time.sleep(0.2)
        ctx.log_cb("[Ingest] Input integrity verified: 1080p, 30fps.")
        return StageResult(success=True)


class MockFrameExtractionStage(Stage):
    name = "frame_extraction"
    weight = 1.0

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Extraction] Extracting frames with adaptive sharpness scoring...")
        for step in range(1, 4):
            time.sleep(0.15)
            ctx.log_cb(f"[Extraction] Processed keyframe set {step}/3 (sharpness score > 180.0)")
        return StageResult(success=True)


class MockSfMStage(Stage):
    name = "sfm_colmap"
    weight = 1.5

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[SfM] Feature extraction (SIFT GPU sequential matcher)...")
        time.sleep(0.25)
        ctx.log_cb("[SfM] Loop closure verified: 186/186 frames registered (100% coverage).")
        return StageResult(success=True)


class MockDenseMVSStage(Stage):
    name = "mvs_dense"
    weight = 2.0

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Densifying point cloud at resolution-level 2 (fits 8 GB VRAM budget)...")
        time.sleep(0.3)
        ctx.log_cb("[OpenMVS] Point cloud densified: 1,420,500 3D spatial points.")
        dense_ply = ctx.workdir / "dense_cloud.ply"
        generate_synthetic_splat_ply(dense_ply, num_points=1000, scale=ctx.cumulative_scale)
        return StageResult(success=True, output_files=[dense_ply])


class MockMeshReconstructStage(Stage):
    name = "mesh_reconstruct"
    weight = 1.5

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Reconstructing watertight Delaunay tetrahedral mesh...")
        time.sleep(0.25)
        ctx.log_cb("[OpenMVS] Initial surface mesh generated: 380,000 faces.")
        raw_obj = ctx.workdir / "raw_mesh.obj"
        generate_procedural_room_obj(raw_obj, scale=ctx.cumulative_scale)
        raw_glb = ctx.workdir / "raw_mesh.glb"
        try:
            import trimesh
            mesh = trimesh.load(str(raw_obj))
            mesh.export(str(raw_glb))
        except Exception:
            with open(raw_glb, "wb") as f:
                f.write(b"glTF" + b"\x00" * 1024)
        return StageResult(success=True, output_files=[raw_glb])



class MockMeshCleanupStage(Stage):
    name = "mesh_cleanup"
    weight = 0.5

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Cleanup] Removing non-manifold edges and small disconnected floating components...")
        time.sleep(0.15)
        return StageResult(success=True)


class MockPlaneRepairStage(Stage):
    name = "plane_repair"
    weight = 0.5

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Planar RANSAC] Detecting dominant room planes (Floor, Walls, Ceiling)...")
        time.sleep(0.15)
        ctx.log_cb("[Planar RANSAC] 5 planar segments detected. Holes patched on drywalls.")
        return StageResult(success=True)


class MockFloorAlignStage(Stage):
    name = "floor_align"
    weight = 0.5

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Floor Align] Leveling lowest dominant horizontal plane to Y=0...")
        time.sleep(0.15)
        ctx.log_cb("[Floor Align] Coordinate frame rotation matrix applied.")
        return StageResult(success=True)


class MockScaleStage(Stage):
    name = "mesh_scale"
    weight = 0.5

    def run(self, ctx: JobContext) -> StageResult:
        scale = ctx.cumulative_scale
        ctx.log_cb(f"[Scale] Applying cumulative metric scale factor: {scale:.4f}")
        time.sleep(0.15)
        return StageResult(success=True)


class MockDecimateStage(Stage):
    name = "mesh_decimate"
    weight = 0.5

    def run(self, ctx: JobContext) -> StageResult:
        target = ctx.params.get("options", {}).get("poly_target") or 200000
        ctx.log_cb(f"[Decimate] Planarity-aware quadric decimation to {target} faces...")
        time.sleep(0.15)
        return StageResult(success=True)


class MockUVTextureStage(Stage):
    name = "uv_texture"
    weight = 1.0

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Texturing] Executing OpenMVS TextureMesh on final decimated geometry with COLMAP cameras...")
        time.sleep(0.3)
        ctx.log_cb("[Texturing] Texture atlas baked at configured resolution.")
        return StageResult(success=True)


class MockExportStage(Stage):
    name = "export"
    weight = 1.0

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[Export] Generating canonical formats and user-requested outputs...")
        art_dir = storage_service.get_job_artifacts_dir(ctx.job_id)
        scale = ctx.cumulative_scale
        scan_type = ctx.params.get("scan_type", "photo")
        output_formats = ctx.params.get("output_formats", ["glb", "obj"])

        # 1. Generate OBJ + MTL
        obj_file = art_dir / "scanforge_room.obj"
        generate_procedural_room_obj(obj_file, scale=scale)
        if "obj" in output_formats:
            add_artifact(
                job_id=ctx.job_id,
                kind="mesh",
                format_name="obj",
                filename=obj_file.name,
                size_bytes=obj_file.stat().st_size,
                file_path=str(obj_file)
            )

        # 2. Generate or copy GLB
        glb_file = art_dir / "scanforge_room.glb"
        try:
            import trimesh
            mesh = trimesh.load(str(obj_file))
            mesh.export(str(glb_file))
        except Exception:
            # If trimesh is not present or failed, write standard binary mock header
            with open(glb_file, "wb") as f:
                f.write(b"glTF" + b"\x00" * 1024)

        if "glb" in output_formats or "photo" in scan_type:
            add_artifact(
                job_id=ctx.job_id,
                kind="mesh",
                format_name="glb",
                filename=glb_file.name,
                size_bytes=glb_file.stat().st_size if glb_file.exists() else 1024,
                file_path=str(glb_file)
            )

        # 3. Generate Splats if 3DGS or requested
        if scan_type == "gaussian_splat" or "splat" in output_formats or "ply" in output_formats:
            splat_ply = art_dir / "scanforge_splat.ply"
            generate_synthetic_splat_ply(splat_ply, scale=scale)
            add_artifact(
                job_id=ctx.job_id,
                kind="splat",
                format_name="ply",
                filename=splat_ply.name,
                size_bytes=splat_ply.stat().st_size,
                file_path=str(splat_ply)
            )

            splat_binary = art_dir / "scanforge_splat.splat"
            generate_compact_splat(splat_binary, scale=scale)
            add_artifact(
                job_id=ctx.job_id,
                kind="splat",
                format_name="splat",
                filename=splat_binary.name,
                size_bytes=splat_binary.stat().st_size,
                file_path=str(splat_binary)
            )

        # Create zip archive of all artifacts
        storage_service.create_zip_archive(ctx.job_id)
        ctx.log_cb("[Export] All requested output artifacts generated successfully.")
        return StageResult(success=True)


def create_mock_pipeline(scan_type: str) -> Pipeline:
    """Instantiate mock pipeline matching scan type and amendment stage orders."""
    stages = [
        MockIngestStage(),
        MockFrameExtractionStage(),
        MockSfMStage(),
        MockDenseMVSStage(),
        MockMeshReconstructStage(),
        MockMeshCleanupStage(),
        MockPlaneRepairStage(),
        MockFloorAlignStage(),
        MockScaleStage(),
        MockDecimateStage(),
        MockUVTextureStage(),  # Amendment 2: Texturing runs last
        MockExportStage()
    ]
    return Pipeline(scan_type=scan_type, stages=stages)
