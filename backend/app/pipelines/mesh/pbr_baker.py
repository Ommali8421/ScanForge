"""
PBR Texture Map Synthesizer and UV Gutter Dilator
Bakes detail-enhancing tangent-space Normal Maps and Roughness Maps from diffuse texture atlases:
1. 4px UV Gutter Dilation: Propagates chart border colors into empty gutters to prevent mipmap bleeding.
2. High-Pass Tangent-Space Normal Map: Extracts micro-surface relief from high-pass luminance gradients,
   eroding the UV mask by 2px to guarantee chart seams receive neutral flat normal [128, 128, 255].
3. Clamped PBR Roughness Map: Computes local texture energy clamped to [0.45, 0.95] packed with metallic=0.0.
"""

from pathlib import Path
from typing import Tuple, Optional
import cv2
import numpy as np
from PIL import Image


def dilate_uv_gutters(
    diffuse_bgr: np.ndarray,
    gutter_px: int = 4,
    empty_color: Tuple[int, int, int] = (200, 200, 200),
    color_tolerance: int = 6,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Dilates valid UV chart borders outwards by `gutter_px` into empty background gutters.
    Returns:
        dilated_bgr: Texture with dilated UV gutters.
        valid_mask: Boolean mask (H, W) where True indicates valid chart pixels.
    """
    diff = np.abs(diffuse_bgr.astype(np.int16) - np.array(empty_color, dtype=np.int16))
    is_empty = np.all(diff <= color_tolerance, axis=-1)
    valid_mask = ~is_empty

    if not np.any(valid_mask) or np.all(valid_mask):
        return diffuse_bgr.copy(), valid_mask

    # Distance transform with nearest-label propagation
    # label non-empty pixels
    mask_u8 = valid_mask.astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated_mask = cv2.dilate(mask_u8, kernel, iterations=gutter_px)
    gutter_band = (dilated_mask > 0) & (~valid_mask)

    if not np.any(gutter_band):
        return diffuse_bgr.copy(), valid_mask

    # Inpaint or nearest border copy for gutter pixels
    # cv2.inpaint with radius 4 is extremely fast and smooth for texture margins
    dilated_bgr = cv2.inpaint(diffuse_bgr, (~valid_mask).astype(np.uint8), gutter_px, cv2.INPAINT_TELEA)
    # Restore empty regions beyond the gutter_band if desired, or keep smooth padding
    result_bgr = diffuse_bgr.copy()
    result_bgr[gutter_band] = dilated_bgr[gutter_band]

    return result_bgr, valid_mask


def synthesize_pbr_maps(
    diffuse_path: Path,
    output_dir: Path,
    relief_k: float = 0.85,
    roughness_range: Tuple[float, float] = (0.45, 0.95),
) -> Tuple[Path, Path, Path]:
    """
    Synthesizes normal_map.png and roughness_map.png from diffuse texture atlas.
    Returns:
        (dilated_diffuse_path, normal_map_path, roughness_map_path)
    """
    diffuse_bgr = cv2.imread(str(diffuse_path))
    if diffuse_bgr is None:
        raise FileNotFoundError(f"Cannot read diffuse texture at {diffuse_path}")

    h, w = diffuse_bgr.shape[:2]

    # 1. UV Gutter Dilation
    dilated_bgr, valid_mask = dilate_uv_gutters(diffuse_bgr, gutter_px=4)
    dilated_diffuse_path = output_dir / "scene_textured_dilated.png"
    cv2.imwrite(str(dilated_diffuse_path), dilated_bgr)

    # 2. Tangent-Space Normal Map from High-Pass Luminance
    # High-pass micro-detail (Y - GaussianBlur(Y)) eliminates macroscopic shadow gradients
    gray = cv2.cvtColor(dilated_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (9, 9), 2.0)
    high_pass = gray - blur

    # Erode valid mask by 2px so UV chart boundaries strictly receive flat normal [128, 128, 255]
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask_eroded = cv2.erode((valid_mask.astype(np.uint8) * 255), kernel_erode, iterations=2) > 0

    scale = relief_k / 255.0
    gx = cv2.Sobel(high_pass, cv2.CV_32F, 1, 0, ksize=3) * scale
    gy = cv2.Sobel(high_pass, cv2.CV_32F, 0, 1, ksize=3) * scale

    # Tangent-space normal vector: (-gx, -gy, 1.0) normalized
    gz = np.ones_like(gx, dtype=np.float32)
    norm = np.sqrt(gx**2 + gy**2 + gz**2)
    norm = np.maximum(norm, 1e-6)

    nx = -gx / norm
    ny = -gy / norm
    nz = gz / norm

    # Map to [0, 255] uint8: standard OpenGL tangent-space normal (R=X, G=Y, B=Z)
    normal_r = np.clip((nx * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal_g = np.clip((ny * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal_b = np.clip((nz * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)

    # Where outside eroded chart mask, enforce neutral flat normal [128, 128, 255]
    normal_r[~mask_eroded] = 128
    normal_g[~mask_eroded] = 128
    normal_b[~mask_eroded] = 255

    normal_rgb = np.stack([normal_r, normal_g, normal_b], axis=-1)
    normal_map_path = output_dir / "normal_map.png"
    # cv2 expects BGR
    cv2.imwrite(str(normal_map_path), cv2.cvtColor(normal_rgb, cv2.COLOR_RGB2BGR))

    # 3. PBR Metallic-Roughness Map
    # Local luminance variance / standard deviation
    blur_sq = cv2.blur(gray**2, (5, 5))
    sq_blur = cv2.blur(gray, (5, 5))**2
    local_var = np.maximum(0.0, blur_sq - sq_blur)
    local_std = np.sqrt(local_var)

    p98 = float(np.percentile(local_std[valid_mask], 98)) if np.any(valid_mask) else 1.0
    p98 = max(p98, 1e-4)

    min_r, max_r = roughness_range
    roughness_norm = np.clip(local_std / p98, 0.0, 1.0)
    roughness_val = min_r + (max_r - min_r) * roughness_norm
    roughness_u8 = np.clip(roughness_val * 255.0, 0, 255).astype(np.uint8)
    # Outside valid mask: default matte roughness (0.85)
    roughness_u8[~valid_mask] = int(0.85 * 255)

    # glTF 2.0 PBR Metallic-Roughness Texture:
    # R: Unused / Occlusion (255)
    # G: Roughness
    # B: Metalness (0 for non-metallic dielectric interiors)
    metallic_u8 = np.zeros_like(roughness_u8)
    r_chan = np.full_like(roughness_u8, 255)

    pbr_packed = np.stack([r_chan, roughness_u8, metallic_u8], axis=-1)
    roughness_map_path = output_dir / "roughness_map.png"
    cv2.imwrite(str(roughness_map_path), cv2.cvtColor(pbr_packed, cv2.COLOR_RGB2BGR))

    return dilated_diffuse_path, normal_map_path, roughness_map_path
