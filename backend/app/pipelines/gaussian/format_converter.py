"""
Format Converter Stage for 3D Gaussian Splatting
Converts cleaned 3DGS PLY into compact 32-byte binary .splat format,
optional .spz format, and zip delivery package.
"""

import json
import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from plyfile import PlyData

from app.pipelines.base import Stage, StageResult, JobContext
from app.utils.logging import logger

SH_C0 = 0.28209479177387814

SPLAT_DTYPE = np.dtype([
    ('pos', '<f4', (3,)),
    ('scale', '<f4', (3,)),
    ('color', 'u1', (4,)),
    ('rot', 'u1', (4,)),
])


def compute_morton_order(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """
    Computes 3D Morton Z-order curve indices for spatial cache locality and fast WebGL sorting.
    Quantizes coordinates to 10-bit integers (0 to 1023) and bit-interleaves.
    """
    if len(x) == 0:
        return np.arange(0, dtype=np.int64)

    min_x, max_x = float(np.min(x)), float(np.max(x))
    min_y, max_y = float(np.min(y)), float(np.max(y))
    min_z, max_z = float(np.min(z)), float(np.max(z))

    span_x = max(max_x - min_x, 1e-4)
    span_y = max(max_y - min_y, 1e-4)
    span_z = max(max_z - min_z, 1e-4)

    qx = np.clip(((x - min_x) / span_x * 1023.0).astype(np.uint32), 0, 1023)
    qy = np.clip(((y - min_y) / span_y * 1023.0).astype(np.uint32), 0, 1023)
    qz = np.clip(((z - min_z) / span_z * 1023.0).astype(np.uint32), 0, 1023)

    def expand_bits_10(v: np.ndarray) -> np.ndarray:
        v = v.astype(np.uint64)
        v = (v | (v << 16)) & 0x030000FF
        v = (v | (v << 8))  & 0x0300F00F
        v = (v | (v << 4))  & 0x030C30C3
        v = (v | (v << 2))  & 0x09249249
        return v

    morton = expand_bits_10(qx) | (expand_bits_10(qy) << 1) | (expand_bits_10(qz) << 2)
    return np.argsort(morton)


def pack_ply_to_splat(ply_path: Path, splat_path: Path, scale_factor: float = 1.0) -> int:
    """
    Packs 3DGS PLY into compact 32-byte .splat format for WebGL / Three.js rendering.
    Returns number of packed splats.
    """
    plydata = PlyData.read(str(ply_path))
    vertex = plydata["vertex"].data
    N = len(vertex)
    if N == 0:
        splat_path.touch()
        return 0

    x = np.asarray(vertex["x"], dtype=np.float32) * scale_factor
    y = np.asarray(vertex["y"], dtype=np.float32) * scale_factor
    z = np.asarray(vertex["z"], dtype=np.float32) * scale_factor

    s0 = np.asarray(vertex["scale_0"], dtype=np.float32)
    s1 = np.asarray(vertex["scale_1"], dtype=np.float32)
    s2 = np.asarray(vertex["scale_2"], dtype=np.float32)

    # Linear scales: exp(s) * scale_factor
    scale_0 = np.exp(np.clip(s0, -20.0, 10.0)) * scale_factor
    scale_1 = np.exp(np.clip(s1, -20.0, 10.0)) * scale_factor
    scale_2 = np.exp(np.clip(s2, -20.0, 10.0)) * scale_factor

    # Opacity to uint8 alpha: sigmoid(opacity) * 255
    op = np.asarray(vertex["opacity"], dtype=np.float32)
    alpha = 1.0 / (1.0 + np.exp(-np.clip(op, -20.0, 20.0)))
    a_u8 = np.clip(alpha * 255.0, 0, 255).astype(np.uint8)

    # Color from DC Spherical Harmonics: clip((0.5 + C0 * f_dc) * 255, 0, 255)
    f_dc_0 = np.asarray(vertex["f_dc_0"], dtype=np.float32)
    f_dc_1 = np.asarray(vertex["f_dc_1"], dtype=np.float32)
    f_dc_2 = np.asarray(vertex["f_dc_2"], dtype=np.float32)

    r_u8 = np.clip((0.5 + SH_C0 * f_dc_0) * 255.0, 0, 255).astype(np.uint8)
    g_u8 = np.clip((0.5 + SH_C0 * f_dc_1) * 255.0, 0, 255).astype(np.uint8)
    b_u8 = np.clip((0.5 + SH_C0 * f_dc_2) * 255.0, 0, 255).astype(np.uint8)

    # Normalized quaternions (w, x, y, z) mapped to uint8 via clip(q * 128 + 128, 0, 255)
    qw = np.asarray(vertex["rot_0"], dtype=np.float32)
    qx = np.asarray(vertex["rot_1"], dtype=np.float32)
    qy = np.asarray(vertex["rot_2"], dtype=np.float32)
    qz = np.asarray(vertex["rot_3"], dtype=np.float32)

    q_norm = np.sqrt(qw**2 + qx**2 + qy**2 + qz**2)
    q_norm = np.where(q_norm > 1e-8, q_norm, 1.0)
    qw /= q_norm
    qx /= q_norm
    qy /= q_norm
    qz /= q_norm

    qw_u8 = np.clip(qw * 128.0 + 128.0, 0, 255).astype(np.uint8)
    qx_u8 = np.clip(qx * 128.0 + 128.0, 0, 255).astype(np.uint8)
    qy_u8 = np.clip(qy * 128.0 + 128.0, 0, 255).astype(np.uint8)
    qz_u8 = np.clip(qz * 128.0 + 128.0, 0, 255).astype(np.uint8)

    packed = np.empty(N, dtype=SPLAT_DTYPE)
    packed['pos'][:, 0] = x
    packed['pos'][:, 1] = y
    packed['pos'][:, 2] = z

    packed['scale'][:, 0] = scale_0
    packed['scale'][:, 1] = scale_1
    packed['scale'][:, 2] = scale_2

    packed['color'][:, 0] = r_u8
    packed['color'][:, 1] = g_u8
    packed['color'][:, 2] = b_u8
    packed['color'][:, 3] = a_u8

    packed['rot'][:, 0] = qw_u8
    packed['rot'][:, 1] = qx_u8
    packed['rot'][:, 2] = qy_u8
    packed['rot'][:, 3] = qz_u8

    with open(splat_path, "wb") as f:
        packed.tofile(f)

    return N


def unpack_splat_file(splat_path: Path) -> np.ndarray:
    """Reads a binary .splat file back into a structured numpy array."""
    return np.fromfile(str(splat_path), dtype=SPLAT_DTYPE)


class SplatFormatConverterStage(Stage):
    """
    Converts cleaned 3DGS PLY to .splat, .spz, and deliverable zip archive.
    """
    name: str = "splat_format_converter"
    weight: float = 0.5
    declared_outputs: List[str] = [
        "cleaned_splat.splat",
        "splat.zip",
    ]

    def run(self, ctx: JobContext) -> StageResult:
        ctx.log_cb("[FormatConverter] Converting cleaned splats to web delivery formats...")
        t0 = time.time()

        input_ply = ctx.workdir / "cleaned_splat.ply"
        if not input_ply.exists():
            input_ply = ctx.workdir / "splat.ply"
        if not input_ply.exists():
            raise FileNotFoundError(f"[FormatConverter] Splat PLY missing at {input_ply}")

        # Apply 3D Morton Z-order curve sorting for optimal WebGL cache locality
        from plyfile import PlyData, PlyElement
        pdata = PlyData.read(str(input_ply))
        vdata = pdata["vertex"].data
        if len(vdata) > 0:
            morton_order = compute_morton_order(
                np.asarray(vdata["x"], dtype=np.float32),
                np.asarray(vdata["y"], dtype=np.float32),
                np.asarray(vdata["z"], dtype=np.float32),
            )
            vdata_sorted = vdata[morton_order]
            sorted_elem = PlyElement.describe(vdata_sorted, "vertex")
            PlyData([sorted_elem], text=False).write(str(input_ply))
            ctx.log_cb(f"[FormatConverter] Applied 3D Morton Z-order spatial curve sorting to {len(vdata_sorted):,} Gaussians.")

        # 1. Binary .splat (32 bytes per Gaussian)
        splat_file = ctx.workdir / "cleaned_splat.splat"
        splat_count = pack_ply_to_splat(input_ply, splat_file, scale_factor=1.0)
        file_size_mb = splat_file.stat().st_size / (1024 * 1024)
        ctx.log_cb(
            f"[FormatConverter] Packed {splat_count:,} Gaussians into binary .splat "
            f"({file_size_mb:.2f} MB, {splat_file.stat().st_size:,} bytes)."
        )

        # Also create root preview aliases
        shutil.copy2(splat_file, ctx.workdir / "model.splat")
        shutil.copy2(input_ply, ctx.workdir / "model.ply")

        # 2. Try .spz conversion if library available
        spz_file = ctx.workdir / "cleaned_splat.spz"
        has_spz = False
        try:
            import spz
            from plyfile import PlyData
            pdata = PlyData.read(str(input_ply))
            vertex = pdata["vertex"].data
            N = len(vertex)
            if N > 0:
                pos = np.ascontiguousarray(np.column_stack([vertex["x"], vertex["y"], vertex["z"]]), dtype=np.float32)
                scales = np.ascontiguousarray(np.column_stack([vertex["scale_0"], vertex["scale_1"], vertex["scale_2"]]), dtype=np.float32)
                rots = np.ascontiguousarray(np.column_stack([vertex["rot_0"], vertex["rot_1"], vertex["rot_2"], vertex["rot_3"]]), dtype=np.float32)
                alphas = np.ascontiguousarray(vertex["opacity"], dtype=np.float32)
                colors = np.ascontiguousarray(np.column_stack([vertex["f_dc_0"], vertex["f_dc_1"], vertex["f_dc_2"]]), dtype=np.float32)

                sh_keys = [k for k in vertex.dtype.names if k.startswith("f_rest_")]
                sh_deg = 0
                sph_harm = None
                if len(sh_keys) >= 24:
                    sh_deg = 2
                    sph_harm = np.ascontiguousarray(np.column_stack([vertex[k] for k in sh_keys[:24]]), dtype=np.float32)
                elif len(sh_keys) >= 9:
                    sh_deg = 1
                    sph_harm = np.ascontiguousarray(np.column_stack([vertex[k] for k in sh_keys[:9]]), dtype=np.float32)

                splat_obj = spz.GaussianSplat(
                    positions=pos,
                    scales=scales,
                    rotations=rots,
                    alphas=alphas,
                    colors=colors,
                    sh_degree=sh_deg,
                    spherical_harmonics=sph_harm,
                )
                splat_obj.save(str(spz_file))
                shutil.copy2(spz_file, ctx.workdir / "model.spz")
                has_spz = True
                spz_mb = spz_file.stat().st_size / (1024 * 1024)
                ctx.log_cb(f"[FormatConverter] Exported compressed .spz splat: {spz_file.name} ({spz_mb:.2f} MB, Degree-{sh_deg} SH).")
        except Exception as e:
            logger.debug(f"spz export error: {e}")
            ctx.log_cb(f"[FormatConverter] Notice: .spz export skipped: {e}")

        # 3. Create ZIP bundle
        zip_path = ctx.workdir / "splat.zip"
        cameras_json = ctx.workdir / "cameras_aligned.json"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(input_ply, arcname="cleaned_splat.ply")
            zf.write(splat_file, arcname="cleaned_splat.splat")
            if cameras_json.exists():
                zf.write(cameras_json, arcname="cameras_aligned.json")
            if has_spz and spz_file.exists():
                zf.write(spz_file, arcname="cleaned_splat.spz")

        elapsed = time.time() - t0
        ctx.log_cb(
            f"[FormatConverter] Deliverable formats ready: .ply, .splat ({file_size_mb:.2f} MB), "
            f".zip ({zip_path.stat().st_size/(1024*1024):.2f} MB) in {elapsed:.2f}s."
        )

        out_files = [
            splat_file,
            ctx.workdir / "model.splat",
            ctx.workdir / "model.ply",
            zip_path,
        ]
        if cameras_json.exists():
            out_files.append(cameras_json)
        if has_spz and spz_file.exists():
            out_files.extend([spz_file, ctx.workdir / "model.spz"])

        return StageResult(
            success=True,
            output_files=out_files,
            metadata={"splat_count": splat_count, "splat_size_bytes": splat_file.stat().st_size}
        )
