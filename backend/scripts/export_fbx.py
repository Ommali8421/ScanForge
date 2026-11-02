#!/usr/bin/env python3
"""
Headless Blender 4.1 script for exporting textured models to Autodesk FBX (.fbx).
Embeds textures and sets coordinate frame.
Usage: blender -b -P export_fbx.py -- <input_glb> <output_fbx> [up_axis]
"""

import sys
import os
import bpy


def main():
    if "--" not in sys.argv:
        print("Usage: blender -b -P export_fbx.py -- <input_glb> <output_fbx> [up_axis]")
        sys.exit(1)

    args = sys.argv[sys.argv.index("--") + 1:]
    in_glb = args[0]
    out_fbx = args[1]
    up_axis = args[2].lower() if len(args) > 2 else "y"

    if not os.path.exists(in_glb):
        print(f"Error: input file {in_glb} not found.")
        sys.exit(1)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=in_glb)

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for obj in mesh_objs:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        except Exception:
            pass
        for poly in obj.data.polygons:
            poly.use_smooth = True

    axis_up = "Z" if up_axis == "z" else "Y"
    axis_forward = "-Y" if up_axis == "z" else "-Z"

    bpy.ops.export_scene.fbx(
        filepath=out_fbx,
        path_mode="COPY",
        embed_textures=True,
        axis_forward=axis_forward,
        axis_up=axis_up,
        use_selection=False
    )
    print(f"Exported FBX successfully to {out_fbx}")


if __name__ == "__main__":
    main()

