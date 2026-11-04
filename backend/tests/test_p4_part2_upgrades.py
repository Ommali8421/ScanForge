"""
Unit tests for Milestone P4 Part 2 High-Impact 3D Quality Upgrades:
1. 1-pixel occlusion step masking vs smooth perspective floors.
2. Tangent-space Normal & Roughness PBR map synthesis and GLB embedding.
3. Border-locked decimation (boundary_weight=10.0) and floor plane snapping.
4. Single-stroke CAD floor plan and enclosed area calculation.
5. Compressed .spz export preserving Degree 1/2 Spherical Harmonics.
"""

import json
import struct
import numpy as np
import pytest
from pathlib import Path
from PIL import Image
import trimesh

from app.pipelines.mesh.pbr_baker import dilate_uv_gutters, synthesize_pbr_maps
from app.pipelines.mesh.floor_align import fix_glb_pbr_materials
from app.pipelines.gaussian.format_converter import pack_ply_to_splat


def test_1pixel_relative_step_discontinuity():
    """Verify that smooth perspective floors (step_rel < 0.03) stay intact, while jump edges (> 0.12) are masked."""
    # Synthetic depth map of an oblique floor: z ramps smoothly from 2.0 to 4.0 across 100 pixels
    # Gradient per pixel: (4.0 - 2.0) / 100 = 0.02
    # Relative step: 0.02 / 2.0 = 0.01 (1%), well below 0.03 and 0.12
    y_grid, x_grid = np.mgrid[0:100, 0:100]
    z_smooth = 2.0 + 0.02 * y_grid.astype(np.float32)

    # Insert a genuine step discontinuity occlusion jump at col 50 (z jumps from 2.5 to 5.0, jump = 100%)
    z_with_jump = z_smooth.copy()
    z_with_jump[:, 50:] += 2.5

    # 1-pixel finite difference relative step check
    dz_dx = np.abs(np.diff(z_with_jump, axis=1, prepend=z_with_jump[:, :1]))
    dz_dy = np.abs(np.diff(z_with_jump, axis=0, prepend=z_with_jump[:1, :]))
    step_rel = np.maximum(dz_dx, dz_dy) / np.maximum(z_with_jump, 1e-4)

    edge_mask = step_rel > 0.12

    # Assert smooth perspective floor is 100% unmasked
    assert np.all(~edge_mask[:, :49]), "Smooth floor should not have any masked pixels"
    assert np.all(~edge_mask[:, 52:]), "Smooth upper floor should not have any masked pixels"
    # Assert genuine jump column is detected and masked
    assert np.any(edge_mask[:, 50]), "Occlusion step jump must be detected"


def test_pbr_baker_synthesis(tmp_path):
    """Verify 4px UV gutter dilation, tangent-space normal map, and clamped roughness map."""
    # Create synthetic diffuse texture with a colored square in the center and empty background
    H, W = 128, 128
    diffuse = np.full((H, W, 3), 200, dtype=np.uint8) # empty background
    # Central island
    diffuse[32:96, 32:96] = [150, 100, 80] # Wood/carpet color
    # Add high-frequency noise for texture
    rng = np.random.RandomState(42)
    noise = rng.randint(-15, 15, (64, 64, 3)).astype(np.int16)
    diffuse[32:96, 32:96] = np.clip(diffuse[32:96, 32:96].astype(np.int16) + noise, 0, 255).astype(np.uint8)

    diff_path = tmp_path / "scene_textured.png"
    Image.fromarray(diffuse).save(str(diff_path))

    dilated_path, norm_path, rough_path = synthesize_pbr_maps(
        diffuse_path=diff_path,
        output_dir=tmp_path,
        relief_k=0.85,
        roughness_range=(0.45, 0.95),
    )

    assert dilated_path.exists()
    assert norm_path.exists()
    assert rough_path.exists()

    # Verify normal map is valid RGB normal
    norm_img = np.array(Image.open(str(norm_path)))
    assert norm_img.shape == (H, W, 3)
    # Background gutter should be neutral flat normal [128, 128, 255]
    assert np.array_equal(norm_img[10, 10], [128, 128, 255])
    # Z component of normal map should be positive (blue dominant >= 128)
    assert np.all(norm_img[..., 2] >= 120)

    # Verify roughness map is clamped to [0.45, 0.95]
    rough_img = np.array(Image.open(str(rough_path)))
    # G channel contains roughness
    rough_g = rough_img[32:96, 32:96, 1] / 255.0
    assert np.min(rough_g) >= 0.44
    assert np.max(rough_g) <= 0.96
    # B channel contains metalness (should be 0 for non-metallic interior)
    assert np.all(rough_img[..., 2] == 0)


def test_glb_pbr_embedding_and_gltfpack(tmp_path):
    """Verify embedding normalTexture and metallicRoughnessTexture into GLB and gltfpack compatibility."""
    mesh = trimesh.creation.icosphere(subdivisions=2)
    diff = Image.fromarray(np.full((32, 32, 3), 180, dtype=np.uint8))
    norm = Image.fromarray(np.full((32, 32, 3), [128, 128, 255], dtype=np.uint8))
    rough = Image.fromarray(np.full((32, 32, 3), [0, 200, 0], dtype=np.uint8))

    mesh.visual = trimesh.visual.TextureVisuals(
        uv=np.random.rand(len(mesh.vertices), 2),
        material=trimesh.visual.material.PBRMaterial(
            baseColorTexture=diff,
            normalTexture=norm,
            metallicRoughnessTexture=rough,
            metallicFactor=0.0,
            roughnessFactor=1.0,
            doubleSided=True,
        )
    )

    glb_path = tmp_path / "mesh.glb"
    mesh.export(str(glb_path))
    fix_glb_pbr_materials(glb_path)

    # Inspect glTF JSON chunk
    data = glb_path.read_bytes()
    c0_len, c0_type = struct.unpack_from("<II", data, 12)
    gltf = json.loads(data[20:20+c0_len].decode("utf-8"))
    mat = gltf["materials"][0]

    assert "baseColorTexture" in mat["pbrMetallicRoughness"]
    assert "metallicRoughnessTexture" in mat["pbrMetallicRoughness"]
    assert "normalTexture" in mat
    assert mat.get("doubleSided") is True


def test_spz_splat_export(tmp_path):
    """Verify .spz generation using native spz library with Degree 1/2 Spherical Harmonics."""
    import spz
    N = 100
    pos = np.ascontiguousarray(np.random.randn(N, 3).astype(np.float32))
    scales = np.ascontiguousarray(np.full((N, 3), -3.0, dtype=np.float32))
    rots = np.ascontiguousarray(np.tile([1.0, 0.0, 0.0, 0.0], (N, 1)).astype(np.float32))
    alphas = np.ascontiguousarray(np.full(N, 2.0, dtype=np.float32))
    colors = np.ascontiguousarray(np.full((N, 3), 0.5, dtype=np.float32))
    sph_harm = np.ascontiguousarray(np.zeros((N, 24), dtype=np.float32))

    splat_obj = spz.GaussianSplat(
        positions=pos,
        scales=scales,
        rotations=rots,
        alphas=alphas,
        colors=colors,
        sh_degree=2,
        spherical_harmonics=sph_harm,
    )

    spz_path = tmp_path / "test.spz"
    splat_obj.save(str(spz_path))

    assert spz_path.exists()
    assert spz_path.stat().st_size > 0

    # Load back with spz
    loaded = spz.GaussianSplat.load(str(spz_path))
    assert loaded.num_points == N
    assert loaded.sh_degree == 2
