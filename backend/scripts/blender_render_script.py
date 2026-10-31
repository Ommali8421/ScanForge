#!/usr/bin/env python3
"""
Headless Blender 4.1 script for rendering 4 canonical viewpoints.
Runs inside Blender's embedded Python (bpy).
Outputs 4 views:
1. persp1.png (Perspective Front-Left)
2. persp2.png (Perspective Back-Right)
3. top.png (Orthographic Plan looking down +Y)
4. side.png (Orthographic Elevation)
"""

import math
import os
import sys
from pathlib import Path
import bpy
import mathutils
import numpy as np


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup_lighting():
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.05, 0.07, 0.1, 1.0)
        bg.inputs[1].default_value = 1.0

    key_light_data = bpy.data.lights.new(name="KeyLight", type="SUN")
    key_light_data.energy = 3.5
    key_light_data.color = (1.0, 0.98, 0.95)
    key_light = bpy.data.objects.new(name="KeyLight", object_data=key_light_data)
    key_light.rotation_euler = (math.radians(45), math.radians(30), math.radians(45))
    bpy.context.collection.objects.link(key_light)

    fill_light_data = bpy.data.lights.new(name="FillLight", type="SUN")
    fill_light_data.energy = 2.0
    fill_light_data.color = (0.85, 0.9, 1.0)
    fill_light = bpy.data.objects.new(name="FillLight", object_data=fill_light_data)
    fill_light.rotation_euler = (math.radians(-30), math.radians(-45), math.radians(135))
    bpy.context.collection.objects.link(fill_light)


def get_scene_bounds():
    min_coord = np.array([float("inf"), float("inf"), float("inf")])
    max_coord = np.array([float("-inf"), float("-inf"), float("-inf")])

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            for corner in [obj.matrix_world @ mathutils.Vector(b) for b in obj.bound_box]:
                min_coord = np.minimum(min_coord, [corner.x, corner.y, corner.z])
                max_coord = np.maximum(max_coord, [corner.x, corner.y, corner.z])

    if np.any(np.isinf(min_coord)):
        return np.array([0, 0, 0]), 2.0
    center = (min_coord + max_coord) / 2.0
    size = np.max(max_coord - min_coord)
    return center, max(size, 0.5)


def render_view(cam_pos, look_at, is_ortho, ortho_scale, output_path, up_vector=(0, 1, 0), res=(800, 600)):
    scene = bpy.context.scene
    scene.render.resolution_x = res[0]
    scene.render.resolution_y = res[1]
    scene.render.engine = "BLENDER_WORKBENCH"

    has_textures = len(bpy.data.images) > 0
    has_vertex_colors = any(
        obj.type == "MESH" and (len(getattr(obj.data, "color_attributes", [])) > 0 or len(getattr(obj.data, "vertex_colors", [])) > 0)
        for obj in bpy.context.scene.objects
    )

    if has_textures:
        scene.display.shading.color_type = "TEXTURE"
        scene.display.shading.light = "FLAT"  # Bright, unshadowed photographic texture
    elif has_vertex_colors:
        scene.display.shading.color_type = "VERTEX"
        scene.display.shading.light = "MATCAP"
    else:
        scene.display.shading.color_type = "SINGLE"
        scene.display.shading.single_color = (0.78, 0.82, 0.88)  # Clean architectural clay
        scene.display.shading.light = "MATCAP"

    cam_data = bpy.data.cameras.new("RenderCam")
    cam_obj = bpy.data.objects.new("RenderCam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    if is_ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho_scale * 1.3
    else:
        cam_data.type = "PERSP"
        cam_data.lens = 35

    cam_obj.location = cam_pos
    direction = mathutils.Vector(look_at) - mathutils.Vector(cam_pos)
    
    # If looking straight down/up along Y, specify proper roll/up
    if abs(direction.normalized().y) > 0.99:
        rot_quat = direction.to_track_quat("-Z", "Z")
    else:
        rot_quat = direction.to_track_quat("-Z", "Y")
        
    cam_obj.rotation_euler = rot_quat.to_euler()

    scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(cam_obj, do_unlink=True)
    bpy.data.cameras.remove(cam_data, do_unlink=True)


def main():
    argv = sys.argv
    if "--" not in argv:
        print("Usage: blender -b -P blender_render_script.py -- <model_path> <output_dir>")
        return 1

    args = argv[argv.index("--") + 1:]
    model_path = Path(args[0])
    output_dir = Path(args[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    if not model_path.exists():
        print(f"Error: model file {model_path} does not exist.")
        return 1

    clear_scene()
    setup_lighting()

    print(f"[Blender] Loading model: {model_path}...")
    if model_path.suffix.lower() in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(model_path))
    elif model_path.suffix.lower() == ".ply":
        bpy.ops.wm.ply_import(filepath=str(model_path))
    elif model_path.suffix.lower() == ".obj":
        bpy.ops.wm.obj_import(filepath=str(model_path))

    center, size = get_scene_bounds()
    print(f"[Blender] Model bounds: center={center}, max_size={size:.3f}")

    dist = size * 1.8

    # Note: Model is oriented with up = +Y
    # View 1: Perspective Front-Left Corner (isometric)
    p1_pos = center + np.array([-dist * 0.7, dist * 0.6, dist * 0.7])
    render_view(p1_pos, center, is_ortho=False, ortho_scale=size, output_path=output_dir / "persp1.png")

    # View 2: Perspective Back-Right Corner
    p2_pos = center + np.array([dist * 0.7, dist * 0.6, -dist * 0.7])
    render_view(p2_pos, center, is_ortho=False, ortho_scale=size, output_path=output_dir / "persp2.png")

    # View 3: Top-Down Plan View (looking straight down along -Y)
    top_pos = center + np.array([0, dist * 1.5, 0])
    render_view(top_pos, center, is_ortho=True, ortho_scale=size, output_path=output_dir / "top.png")

    # View 4: Side Elevation View (looking from +X towards center)
    side_pos = center + np.array([dist * 1.5, 0, 0])
    render_view(side_pos, center, is_ortho=True, ortho_scale=size, output_path=output_dir / "side.png")

    print("[Blender] All 4 canonical views rendered successfully.")
    return 0


if __name__ == "__main__":
    main()
