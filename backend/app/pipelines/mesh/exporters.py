"""
Multi-Format Mesh Exporters
Exports the aligned, physically-scaled canonical reconstruction into deliverable formats:
1. GLB: Standard binary glTF with embedded PNG textures and PBR defaults.
2. GLTF: Separate JSON glTF (.gltf + .bin + .png).
3. OBJ ZIP: Complete archive containing .obj + .mtl + texture.png for Blender/Maya.
4. PLY: Stanford triangle polygon mesh.
5. STL: Binary stereolithography surface for 3D printing / CAD.
6. XYZ: ASCII point cloud coordinates and normals (X, Y, Z, Nx, Ny, Nz).
7. FBX: Autodesk Filmbox with embedded PBR textures via headless Blender 4.1.
8. USDZ: Apple AR Quick Look archive with embedded textures via headless Blender 4.1.

Applies user options:
- up_axis ('y' | 'z'): converts coordinate frame for user exports while preview stays +Y.
- units ('m' | 'cm' | 'mm'): applies linear scale factor (1.0, 100.0, 1000.0).
"""

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import trimesh

from app.pipelines.base import Stage, JobContext, StageResult
from app.pipelines.tool_runner import ToolRunner
from app.utils.logging import logger
from app.utils.tool_resolve import resolve_blender


def apply_user_transform_for_export(
    mesh: trimesh.Trimesh,
    up_axis: str = "y",
    units: str = "m"
) -> trimesh.Trimesh:
    """
    Applies coordinate frame rotation (Y to Z if requested) and unit scaling
    (m -> cm / mm) to a duplicate mesh for deliverable exports.
    """
    m = mesh.copy()

    # 1. Units conversion
    units_lower = units.lower()
    if units_lower == "cm":
        scale_factor = 100.0
    elif units_lower == "mm":
        scale_factor = 1000.0
    else:
        scale_factor = 1.0

    if scale_factor != 1.0:
        m.vertices = m.vertices * scale_factor

    # 2. Up-axis conversion: if Z is requested, rotate +90 deg around X (Y becomes Z)
    if up_axis.lower() == "z":
        # R_x(+90 deg): [x, y, z] -> [x, -z, y]
        R_z_up = np.array([
            [1.0,  0.0,  0.0],
            [0.0,  0.0, -1.0],
            [0.0,  1.0,  0.0]
        ], dtype=float)
        m.vertices = m.vertices @ R_z_up.T
        if hasattr(m, "vertex_normals") and len(m.vertex_normals) > 0:
            m.vertex_normals = m.vertex_normals @ R_z_up.T

    return m


class MeshExportStage(Stage):
    """
    Exports the aligned textured mesh into all selected deliverable formats.
    """
    name = "mesh_export"
    weight = 1.0
    declared_inputs = ["aligned_textured.glb"]
    declared_outputs = [
        "mesh.glb",
        "mesh_obj.zip",
        "mesh.ply",
        "mesh.stl",
        "mesh.xyz"
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb(f"[{self.name}] (0%) Starting multi-format mesh export stage...")

        in_glb = ctx.workdir / "aligned_textured.glb"
        if not in_glb.exists():
            in_glb = ctx.workdir / "scene_textured.glb"
        if not in_glb.exists():
            return StageResult(success=False, metadata={"error": "No aligned GLB mesh found for export."})

        opts = ctx.params.get("options", {})
        up_axis = str(opts.get("up_axis", "y")).lower()
        units = str(opts.get("units", "m")).lower()
        requested_formats = [f.lower() for f in ctx.params.get("output_formats", ["glb", "obj", "ply", "stl", "xyz"])]

        ctx.log_cb(f"[{self.name}] Loading aligned master model (up_axis={up_axis}, units={units}, formats={requested_formats})...")
        loaded = trimesh.load(str(in_glb), process=False)
        if isinstance(loaded, trimesh.Scene):
            geoms = list(loaded.geometry.values())
            raw_mesh = geoms[0] if geoms else trimesh.Trimesh()
        else:
            raw_mesh = loaded

        # Apply export unit scale and up-axis conversion
        export_mesh = apply_user_transform_for_export(raw_mesh, up_axis=up_axis, units=units)

        exported_files: List[Path] = []

        # ----------------------------------------------------
        # 1. GLB Export
        # ----------------------------------------------------
        out_glb = ctx.workdir / "mesh.glb"
        try:
            ctx.log_cb(f"[{self.name}] Exporting binary glTF -> mesh.glb...")
            export_mesh.export(str(out_glb))
            # Ensure PBR material defaults
            try:
                from pygltflib import GLTF2
                gltf = GLTF2().load(str(out_glb))
                for mat in gltf.materials:
                    if mat.pbrMetallicRoughness:
                        mat.pbrMetallicRoughness.metallicFactor = 0.0
                        mat.pbrMetallicRoughness.roughnessFactor = 1.0
                    mat.doubleSided = True
                gltf.save(str(out_glb))
            except Exception:
                pass
            exported_files.append(out_glb)
        except Exception as e:
            ctx.log_cb(f"[{self.name}] Warning: GLB export failed: {e}")

        # ----------------------------------------------------
        # 2. GLTF Export (JSON + .bin + .png)
        # ----------------------------------------------------
        if "gltf" in requested_formats:
            try:
                out_gltf = ctx.workdir / "mesh.gltf"
                ctx.log_cb(f"[{self.name}] Exporting separate glTF -> mesh.gltf...")
                gltf_files = trimesh.exchange.gltf.export_gltf(export_mesh, embed_buffers=False)
                if isinstance(gltf_files, dict):
                    for fname, fbytes in gltf_files.items():
                        target = ctx.workdir / fname
                        target.write_bytes(fbytes if isinstance(fbytes, bytes) else fbytes.encode())
                        if fname.endswith(".gltf"):
                            exported_files.append(target)
                else:
                    out_gltf.write_text(str(gltf_files))
                    exported_files.append(out_gltf)
            except Exception as e:
                ctx.log_cb(f"[{self.name}] Warning: glTF export failed: {e}")

        # ----------------------------------------------------
        # 3. OBJ Archive Export (.obj + .mtl + texture.png -> mesh_obj.zip)
        # ----------------------------------------------------
        out_obj_zip = ctx.workdir / "mesh_obj.zip"
        try:
            ctx.log_cb(f"[{self.name}] Exporting Wavefront OBJ archive -> mesh_obj.zip...")
            # Convert PBRMaterial to SimpleMaterial so return_texture generates MTL and PNG
            geom_for_obj = export_mesh.copy()
            if hasattr(geom_for_obj.visual, "material") and hasattr(geom_for_obj.visual.material, "to_simple"):
                geom_for_obj.visual.material = geom_for_obj.visual.material.to_simple()

            obj_res = trimesh.exchange.obj.export_obj(geom_for_obj, return_texture=True)
            if isinstance(obj_res, tuple) and len(obj_res) == 2:
                obj_text, aux_files = obj_res
            else:
                obj_text = str(obj_res)
                aux_files = {}

            # Build ZIP archive
            with zipfile.ZipFile(out_obj_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("mesh.obj", obj_text)
                for aux_name, aux_data in aux_files.items():
                    if isinstance(aux_data, bytes):
                        zf.writestr(aux_name, aux_data)
                    else:
                        zf.writestr(aux_name, str(aux_data).encode("utf-8"))

            exported_files.append(out_obj_zip)
        except Exception as e:
            ctx.log_cb(f"[{self.name}] Warning: OBJ export failed: {e}")

        # ----------------------------------------------------
        # 4. PLY Export
        # ----------------------------------------------------
        out_ply = ctx.workdir / "mesh.ply"
        try:
            ctx.log_cb(f"[{self.name}] Exporting Stanford PLY -> mesh.ply...")
            export_mesh.export(str(out_ply))
            exported_files.append(out_ply)
        except Exception as e:
            ctx.log_cb(f"[{self.name}] Warning: PLY export failed: {e}")

        # ----------------------------------------------------
        # 5. STL Export (Binary Surface)
        # ----------------------------------------------------
        out_stl = ctx.workdir / "mesh.stl"
        try:
            ctx.log_cb(f"[{self.name}] Exporting binary STL -> mesh.stl...")
            stl_mesh = trimesh.Trimesh(vertices=export_mesh.vertices, faces=export_mesh.faces, process=False)
            stl_mesh.export(str(out_stl))
            exported_files.append(out_stl)
        except Exception as e:
            ctx.log_cb(f"[{self.name}] Warning: STL export failed: {e}")

        # ----------------------------------------------------
        # 6. XYZ Point Cloud Export (X Y Z Nx Ny Nz)
        # ----------------------------------------------------
        out_xyz = ctx.workdir / "mesh.xyz"
        try:
            ctx.log_cb(f"[{self.name}] Exporting point cloud -> mesh.xyz...")
            v = export_mesh.vertices
            n = export_mesh.vertex_normals if len(export_mesh.vertex_normals) == len(v) else np.zeros_like(v)
            stacked = np.hstack([v, n])
            np.savetxt(str(out_xyz), stacked, fmt="%.6f", delimiter=" ")
            exported_files.append(out_xyz)
        except Exception as e:
            ctx.log_cb(f"[{self.name}] Warning: XYZ export failed: {e}")

        # ----------------------------------------------------
        # 7. FBX & USDZ Exports (via headless Blender 4.1)
        # ----------------------------------------------------
        blender_bin = resolve_blender()
        has_blender = shutil.which(blender_bin) is not None

        if has_blender:
            scripts_dir = Path(__file__).parents[3] / "scripts"
            if not scripts_dir.exists():
                scripts_dir = Path(__file__).parents[2] / "scripts"

            # FBX
            out_fbx = ctx.workdir / "mesh.fbx"
            fbx_script = scripts_dir / "export_fbx.py"
            if fbx_script.exists():
                try:
                    ctx.log_cb(f"[{self.name}] Exporting Autodesk FBX (embedded PBR textures) -> mesh.fbx...")
                    res = subprocess.run(
                        [blender_bin, "-b", "-P", str(fbx_script), "--", str(out_glb), str(out_fbx), up_axis],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120
                    )
                    if res.returncode == 0 and out_fbx.exists():
                        exported_files.append(out_fbx)
                    else:
                        ctx.log_cb(f"[{self.name}] Warning: Blender FBX export returned {res.returncode}:\n{res.stdout[:200]}")
                except Exception as e:
                    ctx.log_cb(f"[{self.name}] Warning: FBX export failed: {e}")

            # USDZ
            out_usdz = ctx.workdir / "mesh.usdz"
            usdz_script = scripts_dir / "export_usdz.py"
            if usdz_script.exists():
                try:
                    ctx.log_cb(f"[{self.name}] Exporting Apple AR USDZ -> mesh.usdz...")
                    res = subprocess.run(
                        [blender_bin, "-b", "-P", str(usdz_script), "--", str(out_glb), str(out_usdz), up_axis],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120
                    )
                    if res.returncode == 0 and out_usdz.exists():
                        exported_files.append(out_usdz)
                    else:
                        ctx.log_cb(f"[{self.name}] Warning: Blender USDZ export returned {res.returncode}:\n{res.stdout[:200]}")
                except Exception as e:
                    ctx.log_cb(f"[{self.name}] Warning: USDZ export failed: {e}")

        ctx.log_cb(f"[{self.name}] (100%) Multi-format export complete. Generated {len(exported_files)} assets.")
        return StageResult(
            success=True,
            output_files=exported_files,
            metadata={"formats_exported": [f.suffix.lstrip(".") for f in exported_files]}
        )
