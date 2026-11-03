#!/usr/bin/env python3
"""
Blender 4.1 Headless Mesh Viewport Renderer for Milestone P4 Proofs
Renders 2 diagnostic views of any GLB mesh:
1. Overview Perspective Cutaway (looking into the room from elevated angle)
2. Interior Eye-level Wall View (standing inside, looking at walls and floor)
"""

import sys
import math
from pathlib import Path

import bpy
from mathutils import Vector

def render_mesh_views(glb_path: str, out_dir: str, prefix: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)

    print(f"Importing {glb_path}...")
    bpy.ops.import_scene.gltf(filepath=glb_path)

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not mesh_objs:
        raise RuntimeError(f"No mesh found in {glb_path}")

    # Set all meshes to use smooth shading
    for obj in mesh_objs:
        for p in obj.data.polygons:
            p.use_smooth = True

    # Compute aggregate bounding box
    all_corners = []
    for obj in mesh_objs:
        for corner in obj.bound_box:
            all_corners.append(obj.matrix_world @ Vector(corner))

    xs = [c.x for c in all_corners]
    ys = [c.y for c in all_corners]
    zs = [c.z for c in all_corners]

    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = (min(zs) + max(zs)) / 2.0
    min_z = min(zs)
    max_z = max(zs)
    height = max(0.1, max_z - min_z)
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    dim_h = max(span_x, span_y)

    print(f"Bounds: X[{min(xs):.2f}, {max(xs):.2f}], Y[{min(ys):.2f}, {max(ys):.2f}], Z[{min_z:.2f}, {max_z:.2f}]")
    print(f"Center: ({cx:.2f}, {cy:.2f}, {cz:.2f}), DimH={dim_h:.2f}, H={height:.2f}")

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    scene.render.film_transparent = False

    # Studio background
    world = bpy.data.worlds.new("StudioWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.92, 0.93, 0.95, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    # Studio Sun Light
    light_data = bpy.data.lights.new("Sun", type='SUN')
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new("Sun", light_data)
    scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (math.radians(50), math.radians(20), math.radians(45))

    # Fill Light
    fill_data = bpy.data.lights.new("Fill", type='SUN')
    fill_data.energy = 1.2
    fill_obj = bpy.data.objects.new("Fill", fill_data)
    scene.collection.objects.link(fill_obj)
    fill_obj.rotation_euler = (math.radians(-30), math.radians(-40), math.radians(120))

    # Camera
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 22 # Wide angle for interior rooms
    cam_obj = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # View 1: 3/4 Elevated Overview Cutaway
    cam_dist = dim_h * 1.15
    cam_obj.location = (cx + cam_dist * 0.7, cy - cam_dist * 0.7, min_z + height * 1.3)
    target = Vector((cx, cy, min_z + height * 0.35))
    direction = target - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    scene.render.filepath = str(out_path / f"{prefix}_overview.png")
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {scene.render.filepath}")

    # View 2: Interior Eye-Level Walkthrough View
    eye_z = min_z + max(1.0, height * 0.35)
    cam_obj.location = (cx - dim_h * 0.22, cy - dim_h * 0.22, eye_z)
    look_target = Vector((cx + dim_h * 0.25, cy + dim_h * 0.25, eye_z))
    direction = look_target - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    scene.render.filepath = str(out_path / f"{prefix}_interior.png")
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {scene.render.filepath}")


if __name__ == "__main__":
    args = sys.argv
    if "--" in args:
        idx = args.index("--")
        glb = args[idx + 1]
        out_d = args[idx + 2]
        pfx = args[idx + 3]
        render_mesh_views(glb, out_d, pfx)
    else:
        print("Usage: blender -b -P scripts/render_p4_mesh_views.py -- <glb> <out_dir> <prefix>")
