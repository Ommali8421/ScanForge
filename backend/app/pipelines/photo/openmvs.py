"""
OpenMVS Pipeline Stages (Milestone P2c Phase 1)
Wrappers for InterfaceCOLMAP, DensifyPointCloud, and ReconstructMesh.
Adheres to ScanForge Portability & Resource Etiquette Rules:
1. Dynamic OpenMVS binary resolution.
2. Dynamic working resolution derived from actual image dimensions and VRAM tier.
3. Automatic low-memory OOM retry (bumps resolution level).
4. RAM guard for 11 GB WSL environment.
5. Emits dense point cloud and raw mesh preview artifacts for the UI.
"""

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner
from app.utils.logging import logger
from app.utils.tool_resolve import (
    resolve_openmvs,
    get_configured_threads,
    get_available_vram_gb,
    check_ram_guard,
    determine_openmvs_resolution_level,
)


class OpenMVSInterfaceStage(Stage):
    """
    Exports COLMAP undistorted model to OpenMVS scene format (scene.mvs).
    """
    name: str = "openmvs_interface"
    weight: float = 0.5
    declared_outputs: List[str] = ["scene.mvs"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Preparing COLMAP model for MVS reconstruction...")
        interface_bin = resolve_openmvs("InterfaceCOLMAP")
        threads = str(get_configured_threads())

        undistorted_dir = ctx.workdir / "undistorted"
        if not undistorted_dir.exists():
            raise FileNotFoundError(
                f"Undistorted COLMAP folder not found at {undistorted_dir}. "
                "Ensure ColmapSfMStage ran successfully."
            )

        output_mvs = ctx.workdir / "scene.mvs"
        cmd = [
            interface_bin,
            "-w", str(ctx.workdir),
            "-i", "undistorted",
            "-o", "scene.mvs",
            "--image-folder", "undistorted/images",
            "--max-threads", threads,
            "-v", "2",
        ]

        ctx.log_cb(f"[OpenMVS] Running InterfaceCOLMAP -> {output_mvs.name} (threads: {threads})")
        res = ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=300,
        )

        if not output_mvs.exists():
            raise RuntimeError(
                f"InterfaceCOLMAP completed with exit code {res.exit_code} "
                f"but output {output_mvs} was not created."
            )

        ctx.log_cb(f"[OpenMVS] Scene interface created successfully: {output_mvs.name} ({output_mvs.stat().st_size / 1024:.1f} KB)")
        return StageResult(
            success=True,
            output_files=[output_mvs],
            metadata={"mvs_file": str(output_mvs.name)},
        )


class OpenMVSDensifyStage(Stage):
    """
    Computes dense point cloud from scene.mvs using OpenMVS DensifyPointCloud.
    Resolution level is dynamically selected based on image size and VRAM tier,
    with automatic OOM fallback retry.
    """
    name: str = "openmvs_densify"
    weight: float = 3.0
    declared_outputs: List[str] = ["scene_dense.mvs", "scene_dense.ply", "dense_cloud.ply"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Initializing dense point cloud reconstruction (DensifyPointCloud)...")
        densify_bin = resolve_openmvs("DensifyPointCloud")
        threads = str(get_configured_threads())

        # Check RAM guard for 11 GB WSL
        is_safe, avail_mb, total_mb = check_ram_guard(min_available_mb=1500)
        ctx.log_cb(f"[RAM Guard] Host memory check: {avail_mb:.1f} MB available / {total_mb:.1f} MB total (safe: {is_safe})")

        # Determine input image dimensions
        img_w, img_h = 1080, 1920
        ingest_meta_file = ctx.workdir / "ingest_metadata.json"
        if ingest_meta_file.exists():
            try:
                with open(ingest_meta_file, "r") as f:
                    meta = json.load(f)
                    img_w = meta.get("effective_width") or meta.get("width") or img_w
                    img_h = meta.get("effective_height") or meta.get("height") or img_h
            except Exception:
                pass

        vram_gb = get_available_vram_gb()
        quality = ctx.params.get("quality", "standard")
        initial_res_level = determine_openmvs_resolution_level(img_w, img_h, vram_gb=vram_gb, quality=quality)

        ctx.log_cb(
            f"[OpenMVS] Dynamic resolution planning: frame={img_w}x{img_h}, VRAM={vram_gb:.1f} GB, "
            f"quality='{quality}' -> initial resolution-level {initial_res_level}"
        )

        input_mvs = ctx.workdir / "scene.mvs"
        output_mvs = ctx.workdir / "scene_dense.mvs"
        output_ply = ctx.workdir / "scene_dense.ply"

        if not input_mvs.exists():
            raise FileNotFoundError(f"Input scene file not found: {input_mvs}")

        # Execution with OOM auto-retry
        res_level = initial_res_level
        max_retries = 2
        success = False
        last_error = ""

        for attempt in range(max_retries + 1):
            cmd = [
                densify_bin,
                "-w", str(ctx.workdir),
                "-i", "scene.mvs",
                "-o", "scene_dense.mvs",
                "--resolution-level", str(res_level),
                "--max-threads", threads,
                "-v", "2",
            ]

            ctx.log_cb(f"[OpenMVS] Running DensifyPointCloud (attempt {attempt+1}, resolution-level {res_level}, threads {threads})...")
            try:
                res = ToolRunner.run(
                    cmd,
                    cwd=str(ctx.workdir),
                    log_callback=ctx.log_cb,
                    cancel_token=ctx.cancel_token,
                    timeout=1800,
                )

                if output_mvs.exists() and output_ply.exists():
                    success = True
                    break
                else:
                    last_error = f"DensifyPointCloud exited with code {res.exit_code} without generating outputs."
            except Exception as e:
                err_msg = str(e)
                last_error = err_msg
                is_oom = any(k in err_msg.lower() for k in ("out of memory", "cuda error", "std::bad_alloc", "oom"))
                if is_oom and attempt < max_retries:
                    res_level += 1
                    ctx.log_cb(
                        f"[OpenMVS] WARNING: Memory pressure / CUDA OOM detected during densification. "
                        f"Retrying automatically at lower resolution-level {res_level}..."
                    )
                    continue
                raise

        if not success:
            raise RuntimeError(f"Dense point cloud reconstruction failed: {last_error}")

        # Parse number of dense points from generated ply or log
        point_count = 0
        try:
            if output_ply.exists():
                with open(output_ply, "rb") as f:
                    for _ in range(30):
                        line = f.readline().decode("ascii", errors="ignore")
                        if line.startswith("element vertex"):
                            point_count = int(line.split()[-1])
                            break
        except Exception:
            pass

        ctx.log_cb(f"[OpenMVS] Dense point cloud generated: {point_count:,} points ({output_ply.stat().st_size / (1024*1024):.1f} MB)")

        # Create standardized preview artifact
        dense_preview = ctx.workdir / "dense_cloud.ply"
        if not dense_preview.exists() and output_ply.exists():
            shutil.copyfile(output_ply, dense_preview)

        return StageResult(
            success=True,
            output_files=[output_mvs, output_ply, dense_preview],
            metadata={
                "point_count": point_count,
                "resolution_level": res_level,
                "dense_ply": str(output_ply.name),
                "preview_ply": str(dense_preview.name),
            },
        )


class OpenMVSRMeshStage(Stage):
    """
    Reconstructs surface mesh from dense point cloud using OpenMVS ReconstructMesh.
    Converts and exports raw_mesh.glb for instant web 3D preview.
    """
    name: str = "openmvs_reconstruct_mesh"
    weight: float = 2.0
    declared_outputs: List[str] = ["scene_dense_mesh.ply", "raw_mesh.ply", "raw_mesh.glb"]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[OpenMVS] Initializing Delaunay tetrahedral surface mesh reconstruction (ReconstructMesh)...")
        rmesh_bin = resolve_openmvs("ReconstructMesh")
        threads = str(get_configured_threads())

        input_mvs = ctx.workdir / "scene_dense.mvs"
        output_ply = ctx.workdir / "scene_dense_mesh.ply"

        if not input_mvs.exists():
            raise FileNotFoundError(f"Dense scene input not found: {input_mvs}")

        cmd = [
            rmesh_bin,
            "-w", str(ctx.workdir),
            "-i", "scene_dense.mvs",
            "-o", "scene_dense_mesh.ply",
            "--max-threads", threads,
            "-v", "2",
        ]

        ctx.log_cb(f"[OpenMVS] Running ReconstructMesh -> {output_ply.name} (threads: {threads})...")
        res = ToolRunner.run(
            cmd,
            cwd=str(ctx.workdir),
            log_callback=ctx.log_cb,
            cancel_token=ctx.cancel_token,
            timeout=1200,
        )

        if not output_ply.exists():
            raise RuntimeError(
                f"ReconstructMesh completed with exit code {res.exit_code} "
                f"but output {output_ply} was not created."
            )

        # Standard raw mesh copy
        raw_ply = ctx.workdir / "raw_mesh.ply"
        if not raw_ply.exists():
            shutil.copyfile(output_ply, raw_ply)

        # Convert to raw_mesh.glb for instant UI preview
        raw_glb = ctx.workdir / "raw_mesh.glb"
        vertex_count = 0
        face_count = 0

        ctx.log_cb("[OpenMVS] Generating raw_mesh.glb preview for interactive 3D viewer...")
        try:
            import trimesh
            mesh = trimesh.load(str(output_ply), process=False)
            if isinstance(mesh, trimesh.Scene):
                mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
            vertex_count = len(mesh.vertices)
            face_count = len(mesh.faces)
            mesh.export(str(raw_glb))
            ctx.log_cb(f"[OpenMVS] Raw mesh preview exported: {vertex_count:,} vertices, {face_count:,} faces ({raw_glb.stat().st_size / (1024*1024):.2f} MB)")
        except Exception as e:
            ctx.log_cb(f"[OpenMVS] Warning: Failed to convert PLY to GLB preview via trimesh ({e}).")

        outputs = [output_ply, raw_ply]
        if raw_glb.exists():
            outputs.append(raw_glb)

        return StageResult(
            success=True,
            output_files=outputs,
            metadata={
                "vertex_count": vertex_count,
                "face_count": face_count,
                "raw_ply": str(raw_ply.name),
                "raw_glb": str(raw_glb.name) if raw_glb.exists() else None,
            },
        )
