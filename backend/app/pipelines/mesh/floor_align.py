"""
Floor Alignment and Scale Calibration Stage
Transforms the unoriented, arbitrarily-scaled interior reconstruction into a
physically-scaled, leveled coordinate system:
1. Rotates floor normal to +Y (or +Z per options) with antiparallel 180° singularity guard.
2. Orients floor normal towards interior camera centroid (rooms never flip upside-down).
3. Levels floor plane precisely to Y = 0.000 using median of floor inliers (robust against noise).
4. Aligns dominant interior wall to cardinal grid via yaw rotation.
5. Centers horizontal bounding box (X, Z) at (0, 0).
6. Multiplies coordinates by cumulative scale factor S.
7. Zero-retexturing guarantee: transforms only vertex positions and normals; UVs untouched.
"""

import json
import math
import shutil
import struct
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import trimesh

from app.pipelines.base import Stage, JobContext, StageResult
from app.utils.logging import logger


def fix_glb_pbr_materials(glb_path: Path) -> bool:
    """
    Pure-Python, zero-dependency glTF 2.0 PBR material patcher.
    Directly updates binary glTF (GLB) JSON chunk:
    - metallicFactor = 0.0 (prevents pitch-black render in standard viewers without HDR map)
    - roughnessFactor = 1.0 (diffuse matte finish for interior walls)
    - doubleSided = True (ensures both interior and exterior surfaces are rendered)
    """
    if not glb_path.exists():
        return False
    try:
        with open(glb_path, "rb") as f:
            data = f.read()
        if len(data) < 20:
            return False
        magic, version, _ = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF" or version != 2:
            return False
        c0_len, c0_type = struct.unpack_from("<II", data, 12)
        if c0_type != 0x4E4F534A:
            return False
        json_bytes = data[20:20 + c0_len]
        gltf = json.loads(json_bytes.decode("utf-8"))

        modified = False
        materials = gltf.get("materials", [])
        if not materials:
            # Create a default material if none exists
            gltf["materials"] = [{
                "name": "default",
                "pbrMetallicRoughness": {
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0
                },
                "doubleSided": True
            }]
            modified = True
        else:
            for mat in materials:
                if "pbrMetallicRoughness" not in mat:
                    mat["pbrMetallicRoughness"] = {}
                mat["pbrMetallicRoughness"]["metallicFactor"] = 0.0
                mat["pbrMetallicRoughness"]["roughnessFactor"] = 1.0
                mat["doubleSided"] = True
                modified = True

        if not modified:
            return True

        new_json = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        pad = (4 - (len(new_json) % 4)) % 4
        new_json += b" " * pad
        new_c0_len = len(new_json)
        bin_chunk = data[20 + c0_len:]
        new_total_len = 12 + 8 + new_c0_len + len(bin_chunk)
        new_header = struct.pack("<4sII", b"glTF", 2, new_total_len)
        new_c0_hdr = struct.pack("<II", new_c0_len, 0x4E4F534A)
        with open(glb_path, "wb") as f:
            f.write(new_header + new_c0_hdr + new_json + bin_chunk)
        return True
    except Exception as e:
        logger.warning(f"fix_glb_pbr_materials failed on {glb_path}: {e}")
        return False


def compute_floor_alignment_transform(
    floor_normal: np.ndarray,
    floor_d: float,
    cam_centroid: np.ndarray,
    target_up: np.ndarray = np.array([0.0, 1.0, 0.0]),
    dominant_wall_normal: Optional[np.ndarray] = None,
    u_grav: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Computes total rotation matrix R_total and floor point p_floor.
    Guarantees:
    - Normal sign points UP along true gravity u_grav (never flips room upside down).
    - Antiparallel 180° Rodrigues singularity handled cleanly without NaN.
    - Dominant wall yaw alignment to cardinal axis.
    """
    fn = np.array(floor_normal, dtype=float)
    fn_norm = np.linalg.norm(fn)
    if fn_norm < 1e-6:
        fn = target_up.copy()
    else:
        fn = fn / fn_norm

    fd = float(floor_d)
    floor_point = -fd * fn

    # 1. Normal Sign Orientation: Ensure normal points UP along gravity vector
    if u_grav is not None:
        ug = np.array(u_grav, dtype=float)
        ug_norm = np.linalg.norm(ug)
        if ug_norm > 1e-6:
            ug /= ug_norm
            if np.dot(fn, ug) < 0:
                fn = -fn
                fd = -fd
                floor_point = -fd * fn
    else:
        cam_vec = cam_centroid - floor_point
        if np.dot(fn, cam_vec) < 0:
            fn = -fn
            fd = -fd
            floor_point = -fd * fn

    # 2. Rotation R_floor from fn to target_up
    u = np.array(target_up, dtype=float)
    u = u / np.linalg.norm(u)

    c = float(np.dot(fn, u))

    if c < -0.999999:
        # Antiparallel 180° singularity: exactly opposite target up!
        # Deterministic 180-degree rotation around X axis (or perpendicular axis)
        if abs(u[1]) > 0.9:  # target is Y
            R_floor = np.array([
                [1.0,  0.0,  0.0],
                [0.0, -1.0,  0.0],
                [0.0,  0.0, -1.0]
            ], dtype=float)
        else:  # target is Z
            R_floor = np.array([
                [1.0,  0.0,  0.0],
                [0.0, -1.0,  0.0],
                [0.0,  0.0, -1.0]
            ], dtype=float)
    elif c > 0.999999:
        # Already parallel
        R_floor = np.eye(3, dtype=float)
    else:
        # Rodrigues rotation formula
        v = np.cross(fn, u)
        s = np.linalg.norm(v)
        vx = np.array([
            [0.0, -v[2], v[1]],
            [v[2], 0.0, -v[0]],
            [-v[1], v[0], 0.0]
        ], dtype=float)
        R_floor = np.eye(3, dtype=float) + vx + (vx @ vx) * ((1.0 - c) / (s * s))

    # 3. Dominant Wall Yaw Alignment (align wall normal to cardinal horizontal axis)
    R_total = R_floor.copy()
    if dominant_wall_normal is not None:
        wn = np.array(dominant_wall_normal, dtype=float)
        wn_rot = R_floor @ wn
        # Project wall normal onto horizontal plane (X-Z if Y is up)
        if abs(u[1]) > 0.9:
            horiz_len = math.sqrt(wn_rot[0] ** 2 + wn_rot[2] ** 2)
            if horiz_len > 0.3:
                yaw = math.atan2(wn_rot[0], wn_rot[2])
                # Snap to closest 90-degree cardinal angle
                snap_yaw = round(yaw / (math.pi / 2.0)) * (math.pi / 2.0)
                delta_yaw = snap_yaw - yaw
                cos_y = math.cos(delta_yaw)
                sin_y = math.sin(delta_yaw)
                R_yaw = np.array([
                    [cos_y,  0.0, sin_y],
                    [0.0,    1.0, 0.0],
                    [-sin_y, 0.0, cos_y]
                ], dtype=float)
                R_total = R_yaw @ R_floor

    return R_total, fn, fd


def apply_alignment_and_scale_to_mesh(
    mesh: trimesh.Trimesh,
    R_total: np.ndarray,
    fn_oriented: Optional[np.ndarray],
    fd_oriented: float,
    diag: float,
    scale: float = 1.0,
    target_up: np.ndarray = np.array([0.0, 1.0, 0.0])
) -> Tuple[trimesh.Trimesh, Dict[str, Any]]:
    """
    Applies alignment, Y=0 leveling, centering, and scale to a Trimesh object.
    Preserves all UV texture coordinates and face vertex indices without modification.
    """
    transformed = mesh.copy()
    verts = transformed.vertices

    # Rotate all vertices
    V_rot = verts @ R_total.T

    up_idx = 1 if abs(target_up[1]) > 0.9 else 2

    # Level floor plane to 0.000:
    # If a verified floor plane exists, use the median of floor inliers.
    # Otherwise (mandatory gravity fallback), level using the 5th-percentile bottom vertices.
    if fn_oriented is not None:
        thresh = min(0.02 * diag, 0.05)
        dists = np.abs(np.dot(verts, fn_oriented) + fd_oriented)
        inlier_mask = dists < thresh
        floor_inliers_count = int(np.sum(inlier_mask))
        if floor_inliers_count >= 30:
            Y_floor = float(np.median(V_rot[inlier_mask, up_idx]))
        else:
            floor_pt = -fd_oriented * fn_oriented
            Y_floor = float((R_total @ floor_pt)[up_idx])
    else:
        # Mandatory Gravity Fallback
        Y_floor = float(np.percentile(V_rot[:, up_idx], 5))
        floor_inliers_count = 0

    V_rot[:, up_idx] -= Y_floor

    # Center horizontal coordinates at (0, 0)
    horiz_indices = [0, 2] if up_idx == 1 else [0, 1]
    center_h0 = float((np.min(V_rot[:, horiz_indices[0]]) + np.max(V_rot[:, horiz_indices[0]])) / 2.0)
    center_h1 = float((np.min(V_rot[:, horiz_indices[1]]) + np.max(V_rot[:, horiz_indices[1]])) / 2.0)
    V_rot[:, horiz_indices[0]] -= center_h0
    V_rot[:, horiz_indices[1]] -= center_h1

    # Apply physical scale factor S
    V_final = V_rot * float(scale)

    transformed.vertices = V_final

    # Recompute smooth area-weighted vertex normals (clears OpenMVS noisy split normals)
    transformed.vertex_normals = None

    meta = {
        "R_total": R_total.tolist(),
        "Y_floor_offset": Y_floor,
        "horizontal_center": [center_h0, center_h1],
        "scale": scale,
        "target_up": target_up.tolist(),
        "floor_inliers_count": floor_inliers_count,
        "bounds_min": V_final.min(axis=0).tolist(),
        "bounds_max": V_final.max(axis=0).tolist()
    }
    return transformed, meta


def scale_glb_in_place(
    src_path: Path,
    dst_path: Path,
    scale_factor: float
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Scales the VEC3 POSITION buffer of a GLB directly in the binary chunk in <50ms.
    Guarantees bitwise-identical UVs, texture maps, normals, and materials.
    Returns (min_bounds, max_bounds, vertex_count).
    """
    with open(src_path, "rb") as f:
        header = f.read(12)
        magic, version, total_len = struct.unpack("<4sII", header)
        if magic != b"glTF":
            raise ValueError(f"Invalid GLB magic: {magic}")

        json_len, json_type = struct.unpack("<II", f.read(8))
        json_bytes = f.read(json_len)
        gltf_json = json.loads(json_bytes.decode("utf-8"))

        bin_len, bin_type = struct.unpack("<II", f.read(8))
        bin_bytes = bytearray(f.read(bin_len))

    prim = gltf_json["meshes"][0]["primitives"][0]
    pos_acc = gltf_json["accessors"][prim["attributes"]["POSITION"]]
    bv = gltf_json["bufferViews"][pos_acc["bufferView"]]
    offset = bv.get("byteOffset", 0) + pos_acc.get("byteOffset", 0)
    count = pos_acc["count"]

    verts = np.frombuffer(bin_bytes, dtype=np.float32, count=count * 3, offset=offset).reshape(count, 3).copy()
    verts *= float(scale_factor)

    min_b = verts.min(axis=0).astype(float)
    max_b = verts.max(axis=0).astype(float)
    pos_acc["min"] = min_b.tolist()
    pos_acc["max"] = max_b.tolist()

    bin_bytes[offset:offset + count * 3 * 4] = verts.tobytes()

    new_json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    pad_len = (4 - (len(new_json_bytes) % 4)) % 4
    new_json_bytes += b" " * pad_len

    new_total_len = 12 + 8 + len(new_json_bytes) + 8 + len(bin_bytes)

    with open(dst_path, "wb") as f:
        f.write(struct.pack("<4sII", magic, version, new_total_len))
        f.write(struct.pack("<II", len(new_json_bytes), json_type))
        f.write(new_json_bytes)
        f.write(struct.pack("<II", len(bin_bytes), bin_type))
        f.write(bin_bytes)

    return min_b, max_b, count


class FloorAlignAndScaleStage(Stage):
    """
    Aligns interior mesh with floor at Y=0, snaps walls, centers bounds, and scales.
    Consumes upstream scene_textured.glb (or mesh_decimated.ply) and room_analysis.json.
    """
    name = "floor_align_scale"
    weight = 1.0
    declared_inputs = ["scene_textured.glb", "room_analysis.json"]
    declared_outputs = [
        "aligned_textured.glb",
        "aligned_mesh.ply",
        "floor_alignment.json",
        "preview_textured.glb",
        "cameras_aligned.json"
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb(f"[{self.name}] (0%) Starting floor alignment and scale calibration stage...")

        in_glb = ctx.workdir / "scene_textured.glb"
        analysis_file = ctx.workdir / "room_analysis.json"

        if not in_glb.exists():
            # Fallback to mesh_decimated.ply / mesh_repaired.ply / mesh_cleaned.ply if untextured
            for cand in [
                ctx.workdir / "mesh_decimated.ply",
                ctx.workdir / "mesh_repaired.ply",
                ctx.workdir / "mesh_cleaned.ply",
                ctx.workdir / "mesh_tsdf_raw.ply",
                ctx.workdir / "mesh_splat_raw.ply",
                ctx.workdir / "raw_mesh.ply",
            ]:
                if cand.exists():
                    in_glb = cand
                    break

        if not in_glb.exists():
            # If 3DGS without include_mesh, skip gracefully
            if ctx.params.get("scan_type") in ("gaussian_splat", "3dgs") and not ctx.params.get("options", {}).get("include_mesh"):
                ctx.log_cb(f"[{self.name}] Mesh-inclusive mode not enabled for 3DGS. Skipping floor alignment.")
                return StageResult(success=True, skipped_cache=True)
            return StageResult(success=False, metadata={"error": "No mesh available for floor alignment"})

        # Load room analysis
        analysis = {}
        if analysis_file.exists():
            try:
                analysis = json.loads(analysis_file.read_text())
            except Exception as e:
                ctx.log_cb(f"[{self.name}] Warning: Could not parse room_analysis.json: {e}")

        # Extract floor plane, camera centroid, and dominant wall
        chosen_floor = analysis.get("chosen_floor_plane")
        u_grav = np.array(analysis.get("gravity_up_vector", analysis.get("camera_mean_up", [0.0, 1.0, 0.0])))
        if np.linalg.norm(u_grav) > 1e-6:
            u_grav /= np.linalg.norm(u_grav)

        cam_min = np.array(analysis.get("cam_bbox_min", [-1.0, -1.0, -1.0]))
        cam_max = np.array(analysis.get("cam_bbox_max", [1.0, 1.0, 1.0]))
        cam_centroid = (cam_min + cam_max) / 2.0
        diag = float(analysis.get("scene_diagonal", 30.0))

        # Check dominant wall
        wall_planes = analysis.get("wall_planes", [])
        dominant_wall_n = None
        if wall_planes:
            strongest_wall = max(wall_planes, key=lambda w: w.get("inliers", 0))
            if strongest_wall.get("inliers", 0) >= 800:
                dominant_wall_n = np.array(strongest_wall["normal"])

        up_axis_opt = ctx.params.get("options", {}).get("up_axis", "y").lower()
        target_up = np.array([0.0, 0.0, 1.0]) if up_axis_opt == "z" else np.array([0.0, 1.0, 0.0])

        has_verified_floor = bool(
            chosen_floor and
            chosen_floor.get("qualifies", True) and
            chosen_floor.get("inliers", 0) > 0
        )

        if has_verified_floor:
            floor_n = chosen_floor.get("normal", u_grav)
            floor_d = chosen_floor.get("d", 0.0)
            ctx.log_cb(f"[{self.name}] (20%) Aligning verified floor plane to {'+Z' if up_axis_opt == 'z' else '+Y'}...")
            R_total, fn_oriented, fd_oriented = compute_floor_alignment_transform(
                floor_normal=floor_n,
                floor_d=floor_d,
                cam_centroid=cam_centroid,
                target_up=target_up,
                dominant_wall_normal=dominant_wall_n,
                u_grav=u_grav
            )
        else:
            ctx.log_cb(
                f"[{self.name}] (20%) Mandatory Gravity Fallback: No verified floor plane in room analysis. "
                f"Aligning gravity up-vector [{u_grav[0]:.3f}, {u_grav[1]:.3f}, {u_grav[2]:.3f}] to {'+Z' if up_axis_opt == 'z' else '+Y'}..."
            )
            R_total, _, _ = compute_floor_alignment_transform(
                floor_normal=u_grav,
                floor_d=0.0,
                cam_centroid=cam_centroid,
                target_up=target_up,
                dominant_wall_normal=dominant_wall_n,
                u_grav=u_grav
            )
            fn_oriented = None
            fd_oriented = 0.0

        ctx.log_cb(f"[{self.name}] (40%) Loading textured mesh from {in_glb.name} and flattening scene-graph transforms...")
        loaded = trimesh.load(str(in_glb), force="mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            geoms = loaded.to_geometry()
            if isinstance(geoms, list):
                mesh = trimesh.util.concatenate(geoms) if geoms else trimesh.Trimesh()
            elif isinstance(geoms, dict):
                mesh = trimesh.util.concatenate(list(geoms.values())) if geoms else trimesh.Trimesh()
            else:
                mesh = geoms
        else:
            mesh = loaded

        # Amendment 4: Circular wrap-around 90-degree Manhattan wall alignment
        if len(mesh.faces) > 100:
            fnots = mesh.face_normals @ R_total.T
            # Vertical walls: normal is mostly horizontal (|ny| < 0.35)
            wall_mask = np.abs(fnots[:, 1]) < 0.35
            if np.sum(wall_mask) > 100:
                wn_x = fnots[wall_mask, 0]
                wn_z = fnots[wall_mask, 2]
                wall_areas = mesh.area_faces[wall_mask]
                thetas = np.arctan2(wn_x, wn_z)
                thetas_folded = thetas % (np.pi / 2.0)
                counts, bin_edges = np.histogram(thetas_folded, bins=90, range=(0.0, np.pi / 2.0), weights=wall_areas)

                # Circular wrap-around padding (mode='wrap') to prevent splitting at 0° / 90° boundary
                pad_w = 4
                padded = np.pad(counts, pad_width=pad_w, mode='wrap')
                kernel = np.array([1, 2, 3, 2, 1], dtype=float)
                kernel /= kernel.sum()
                smoothed = np.convolve(padded, kernel, mode='same')[pad_w:-pad_w]

                peak_bin = int(np.argmax(smoothed))
                theta_peak = float(0.5 * (bin_edges[peak_bin] + bin_edges[peak_bin + 1]))
                delta_yaw = float(-theta_peak if theta_peak <= np.pi / 4.0 else (np.pi / 2.0 - theta_peak))

                cos_y = math.cos(delta_yaw)
                sin_y = math.sin(delta_yaw)
                R_manhattan = np.array([
                    [cos_y,  0.0, sin_y],
                    [0.0,    1.0, 0.0],
                    [-sin_y, 0.0, cos_y]
                ], dtype=float)
                R_total = R_manhattan @ R_total
                ctx.log_cb(f"[{self.name}] Manhattan yaw alignment: theta_peak={math.degrees(theta_peak):.1f}°, delta_yaw={math.degrees(delta_yaw):+.1f}°. Walls aligned square to axes.")

        scale = float(ctx.cumulative_scale or 1.0)
        ctx.log_cb(f"[{self.name}] (60%) Leveling floor to Y=0.000, centering horizontal bounds, and applying scale factor {scale:.4f}x...")

        aligned_mesh, meta = apply_alignment_and_scale_to_mesh(
            mesh=mesh,
            R_total=R_total,
            fn_oriented=fn_oriented,
            fd_oriented=fd_oriented,
            diag=diag,
            scale=scale,
            target_up=target_up
        )

        # Save outputs
        out_glb = ctx.workdir / "aligned_textured.glb"
        out_ply = ctx.workdir / "aligned_mesh.ply"
        preview_glb = ctx.workdir / "preview_textured.glb"
        meta_file = ctx.workdir / "floor_alignment.json"

        meta_file.write_text(json.dumps(meta, indent=2))

        # Attach synthesized PBR textures (Normal and Roughness maps) if available
        normal_png = ctx.workdir / "normal_map.png"
        roughness_png = ctx.workdir / "roughness_map.png"
        diffuse_png = ctx.workdir / "scene_textured.png"

        if normal_png.exists() and roughness_png.exists() and diffuse_png.exists():
            try:
                from PIL import Image
                diff_img = Image.open(str(diffuse_png))
                norm_img = Image.open(str(normal_png))
                rough_img = Image.open(str(roughness_png))
                aligned_mesh.visual.material = trimesh.visual.material.PBRMaterial(
                    baseColorTexture=diff_img,
                    normalTexture=norm_img,
                    metallicRoughnessTexture=rough_img,
                    metallicFactor=0.0,
                    roughnessFactor=1.0,
                    doubleSided=True,
                )
                ctx.log_cb(f"[{self.name}] Attached PBR textures (normalTexture, metallicRoughnessTexture) to aligned master mesh.")
            except Exception as e:
                ctx.log_cb(f"[{self.name}] Notice: PBR texture attachment fallback ({e})")

        ctx.log_cb(f"[{self.name}] (80%) Exporting aligned assets: aligned_textured.glb, aligned_mesh.ply, preview_textured.glb...")
        aligned_mesh.export(str(out_glb))
        shutil.copy2(out_glb, preview_glb)

        # Save unscaled aligned reference for instantaneous O(1) recalibration (<0.1s)
        unscaled_glb = ctx.workdir / "aligned_textured_unscaled.glb"
        if abs(scale - 1.0) < 1e-6:
            shutil.copy2(out_glb, unscaled_glb)
        else:
            unscaled_mesh, _ = apply_alignment_and_scale_to_mesh(
                mesh=mesh,
                R_total=R_total,
                fn_oriented=fn_oriented,
                fd_oriented=fd_oriented,
                diag=diag,
                scale=1.0,
                target_up=target_up
            )
            if hasattr(aligned_mesh.visual, "material"):
                unscaled_mesh.visual.material = aligned_mesh.visual.material
            unscaled_mesh.export(str(unscaled_glb))

        # Also export untextured geometry PLY
        ply_mesh = trimesh.Trimesh(vertices=aligned_mesh.vertices, faces=aligned_mesh.faces, process=False)
        ply_mesh.export(str(out_ply))

        # Enforce glTF PBR material defaults via pure-Python zero-dependency patcher
        fix_glb_pbr_materials(out_glb)
        fix_glb_pbr_materials(preview_glb)
        fix_glb_pbr_materials(unscaled_glb)

        output_files = [out_glb, out_ply, meta_file, preview_glb]

        # Export aligned camera poses -> cameras_aligned.json
        sparse_dirs = [
            ctx.workdir / "sparse_txt",
            ctx.workdir / "sparse" / "0",
            ctx.workdir / "aligned_sparse" / "0",
            ctx.workdir / "nerfstudio_data" / "sparse" / "0",
        ]
        submodel_images = list(ctx.workdir.glob("sparse_txt/submodels/*/images.txt"))
        if submodel_images:
            sparse_dirs.insert(0, submodel_images[0].parent)

        target_sparse = None
        for d in sparse_dirs:
            if (d / "images.txt").exists():
                target_sparse = d
                break

        up_idx = 1 if abs(target_up[1]) > 0.9 else 2
        horiz_indices = [0, 2] if up_idx == 1 else [0, 1]

        if target_sparse:
            import re
            from scipy.spatial.transform import Rotation as R_scipy

            def _extract_frame_key(name: str) -> Tuple[int, str]:
                digits = re.findall(r"\d+", name)
                return (int(digits[-1]), name) if digits else (999999, name)

            images_txt = target_sparse / "images.txt"
            parsed_cams = []
            for line in images_txt.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 10 and any(parts[9].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png")):
                    qw, qx, qy, qz = map(float, parts[1:5])
                    tx, ty, tz = map(float, parts[5:8])
                    img_name = parts[9]

                    r_mat = R_scipy.from_quat([qx, qy, qz, qw]).as_matrix()
                    t_vec = np.array([tx, ty, tz], dtype=float)
                    center_raw = -r_mat.T @ t_vec
                    fwd_raw = r_mat.T @ np.array([0.0, 0.0, 1.0], dtype=float)
                    up_raw = -r_mat.T[:, 1]

                    parsed_cams.append({
                        "name": img_name,
                        "center": center_raw,
                        "forward": fwd_raw,
                        "up": up_raw,
                    })

            parsed_cams.sort(key=lambda c: _extract_frame_key(c["name"]))

            aligned_cameras_list = []
            for idx, c in enumerate(parsed_cams):
                c_rot = R_total @ c["center"]
                c_rot[up_idx] -= meta["Y_floor_offset"]
                c_rot[horiz_indices[0]] -= meta["horizontal_center"][0]
                c_rot[horiz_indices[1]] -= meta["horizontal_center"][1]
                c_final = c_rot * float(scale)

                fwd_rot = R_total @ c["forward"]
                fwd_norm = np.linalg.norm(fwd_rot)
                fwd_unit = (fwd_rot / fwd_norm) if fwd_norm > 1e-6 else np.array([0.0, 0.0, 1.0])

                up_rot = R_total @ c["up"]
                up_norm = np.linalg.norm(up_rot)
                up_unit = (up_rot / up_norm) if up_norm > 1e-6 else np.array([0.0, 1.0, 0.0])

                aligned_cameras_list.append({
                    "index": idx,
                    "name": c["name"],
                    "position": [round(float(v), 4) for v in c_final],
                    "up": [round(float(v), 4) for v in up_unit],
                    "forward": [round(float(v), 4) for v in fwd_unit],
                })

            first_frame_cam = aligned_cameras_list[0] if aligned_cameras_list else None
            for cam_entry in aligned_cameras_list:
                if cam_entry["position"][1] > 0.15:
                    first_frame_cam = cam_entry
                    break

            cameras_json_data = {
                "num_cameras": len(aligned_cameras_list),
                "up_axis": "+y" if abs(target_up[1]) > 0.9 else "+z",
                "floor_level": 0.0,
                "first_frame_camera": first_frame_cam,
                "cameras": aligned_cameras_list,
            }
            cams_json_path = ctx.workdir / "cameras_aligned.json"
            cams_json_path.write_text(json.dumps(cameras_json_data, indent=2))
            output_files.append(cams_json_path)
            ctx.log_cb(f"[{self.name}] Exported aligned camera poses -> cameras_aligned.json ({len(aligned_cameras_list)} cameras).")

        ctx.log_cb(
            f"[{self.name}] (100%) Floor alignment complete. Bounds: "
            f"[{meta['bounds_min'][0]:.2f}, {meta['bounds_min'][1]:.2f}, {meta['bounds_min'][2]:.2f}] to "
            f"[{meta['bounds_max'][0]:.2f}, {meta['bounds_max'][1]:.2f}, {meta['bounds_max'][2]:.2f}]."
        )
        return StageResult(success=True, output_files=output_files, metadata=meta)
