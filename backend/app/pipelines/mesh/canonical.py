"""
Canonical Textured Mesh Contract
Standardized internal mesh representation between MVS texturing and post-processing stages.
Ensures post-texture stages (alignment, scale calibration, exporters, quality report)
are completely decoupled from OpenMVS and ready for future alternative engines (AliceVision, etc.).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np
import trimesh


@dataclass
class CanonicalMesh:
    """Standardized representation of a textured 3D mesh."""
    vertices: np.ndarray        # (N, 3) float32
    faces: np.ndarray           # (M, 3) int32
    uvs: Optional[np.ndarray] = None  # (M, 3, 2) or (N, 2) float32
    texture_image_path: Optional[Path] = None
    normals: Optional[np.ndarray] = None  # (N, 3) float32
    material_properties: Dict[str, Any] = field(default_factory=lambda: {
        "metallicFactor": 0.0,
        "roughnessFactor": 1.0,
        "doubleSided": True
    })

    @classmethod
    def from_trimesh(cls, mesh: trimesh.Trimesh, texture_path: Optional[Path] = None) -> "CanonicalMesh":
        """Construct CanonicalMesh from a loaded Trimesh object."""
        uvs = None
        if hasattr(mesh.visual, "uv") and mesh.visual.uv is not None:
            uvs = np.array(mesh.visual.uv, dtype=np.float32)

        return cls(
            vertices=np.array(mesh.vertices, dtype=np.float32),
            faces=np.array(mesh.faces, dtype=np.int32),
            uvs=uvs,
            texture_image_path=texture_path,
            normals=np.array(mesh.vertex_normals, dtype=np.float32) if len(mesh.vertex_normals) > 0 else None
        )

    def to_trimesh(self) -> trimesh.Trimesh:
        """Convert back to Trimesh object preserving materials and texture."""
        visual = None
        if self.uvs is not None and self.texture_image_path and self.texture_image_path.exists():
            from PIL import Image
            img = Image.open(str(self.texture_image_path))
            visual = trimesh.visual.texture.TextureVisuals(
                uv=self.uvs,
                image=img
            )
        mesh = trimesh.Trimesh(
            vertices=self.vertices,
            faces=self.faces,
            vertex_normals=self.normals,
            visual=visual,
            process=False
        )
        return mesh

