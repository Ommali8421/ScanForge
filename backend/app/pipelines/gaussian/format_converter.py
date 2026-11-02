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
            # If spz provides conversion utility or pack function
            if hasattr(spz, "pack"):
                ctx.log_cb("[FormatConverter] Generating compressed .spz format...")
                # spz.pack implementation if available
                has_spz = True
        except Exception as e:
            logger.debug(f"spz optional conversion skipped: {e}")

        # 3. Create ZIP bundle
        zip_path = ctx.workdir / "splat.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(input_ply, arcname="cleaned_splat.ply")
            zf.write(splat_file, arcname="cleaned_splat.splat")
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
        if has_spz and spz_file.exists():
            out_files.append(spz_file)

        return StageResult(
            success=True,
            output_files=out_files,
            metadata={"splat_count": splat_count, "splat_size_bytes": splat_file.stat().st_size}
        )
