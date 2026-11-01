#!/usr/bin/env python3
"""
Headless Blender 4.1 script for exporting textured models to Universal Scene Description (.usdz).
Apple AR Quick Look ready with packed textures.
Usage: blender -b -P export_usdz.py -- <input_glb> <output_usdz> [up_axis]
"""

import sys
import os
import bpy


def main():
    if "--" not in sys.argv:
        print("Usage: blender -b -P export_usdz.py -- <input_glb> <output_usdz> [up_axis]")
        sys.exit(1)

    args = sys.argv[sys.argv.index("--") + 1:]
    in_glb = args[0]
    out_usdz = args[1]
    up_axis = args[2].lower() if len(args) > 2 else "y"

    if not os.path.exists(in_glb):
        print(f"Error: input file {in_glb} not found.")
        sys.exit(1)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=in_glb)

    # Blender 4.1 native USDZ export with textures
    bpy.ops.wm.usd_export(
        filepath=out_usdz,
        export_textures=True,
        relative_paths=True,
        selected_objects_only=False
    )
    print(f"Exported USDZ successfully to {out_usdz}")


if __name__ == "__main__":
    main()

