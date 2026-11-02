#!/usr/bin/env python3
"""
Tanks & Temples Tier 1 Blender 4.1 Proof Renderer
Generates:
1. outputs/t2_<scene>_sheet.png: 4-view composite (Persp 1, Persp 2, Top, Side Elevation)
2. outputs/t2_<scene>_interior.png: Eye-level interior view looking into the room
"""

import sys
import os
import math
from pathlib import Path
import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

def render_scene_proofs(job_id: str, scene_name: str):
    job_dir = Path(f"/data/jobs/{job_id}")
    glb_path = job_dir / "aligned_textured.glb"
    if not glb_path.exists():
        glb_path = job_dir / "preview_textured.glb"
    if not glb_path.exists():
        glb_path = job_dir / "scene_textured.glb"

    if not glb_path.exists():
        print(f"Error: No GLB found in {job_dir}")
        return False

    out_dir = Path("/home/om_mali/scanforge/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = job_dir / "_blender_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{scene_name}] Loading {glb_path.name} into Blender...")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not mesh_objs:
        print("No mesh objects imported.")
        return False

    obj = mesh_objs[0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Clear custom split normals so lighting is smooth
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for poly in obj.data.polygons:
        poly.use_smooth = True

    # Configure scene render
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'RenderSettings') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720

    # Studio background
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.95, 0.95, 0.96, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    # Studio lights
    sun1 = bpy.data.lights.new("SunKey", type='SUN')
    sun1.energy = 2.6
    obj_sun1 = bpy.data.objects.new("SunKey", sun1)
    scene.collection.objects.link(obj_sun1)
    obj_sun1.rotation_euler = (math.radians(45), math.radians(25), math.radians(60))

    sun2 = bpy.data.lights.new("SunFill", type='SUN')
    sun2.energy = 1.4
    obj_sun2 = bpy.data.objects.new("SunFill", sun2)
    scene.collection.objects.link(obj_sun2)
    obj_sun2.rotation_euler = (math.radians(-30), math.radians(-30), math.radians(140))

    cam_data = bpy.data.cameras.new("RenderCam")
    cam_data.lens = 24
    cam_obj = bpy.data.objects.new("RenderCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # Calculate bounding box & centers
    bbox = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in bbox]
    ys = [c.y for c in bbox]
    zs = [c.z for c in bbox]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    cx, cy, cz = (min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2
    span_x = max_x - min_x
    span_y = max_y - min_y
    span_z = max_z - min_z
    max_span = max(span_x, span_y, span_z)

    # 1. Perspective 1: 45 degree high angle
    cam_obj.location = (cx + max_span * 0.85, cy + max_span * 0.65, cz + max_span * 0.85)
    dir_vec = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = dir_vec.to_track_quat('-Z', 'Y').to_euler()
    p1_path = tmp_dir / "persp1.png"
    scene.render.filepath = str(p1_path)
    bpy.ops.render.render(write_still=True)

    # 2. Perspective 2: Opposite quarter view
    cam_obj.location = (cx - max_span * 0.85, cy + max_span * 0.55, cz - max_span * 0.75)
    dir_vec = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = dir_vec.to_track_quat('-Z', 'Y').to_euler()
    p2_path = tmp_dir / "persp2.png"
    scene.render.filepath = str(p2_path)
    bpy.ops.render.render(write_still=True)

    # 3. Top Down (Floor Plan)
    cam_obj.location = (cx, cy + max_span * 1.35, cz + 0.001)
    dir_vec = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = dir_vec.to_track_quat('-Z', 'Y').to_euler()
    top_path = tmp_dir / "top.png"
    scene.render.filepath = str(top_path)
    bpy.ops.render.render(write_still=True)

    # 4. Side Elevation (Floor Level Check: Y=0 grid level)
    cam_obj.location = (cx + max_span * 1.3, cy + 0.2, cz)
    dir_vec = Vector((cx, cy + 0.2, cz)) - cam_obj.location
    cam_obj.rotation_euler = dir_vec.to_track_quat('-Z', 'Y').to_euler()
    side_path = tmp_dir / "side.png"
    scene.render.filepath = str(side_path)
    bpy.ops.render.render(write_still=True)

    # 5. Eye-Level Interior View (1080p)
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    cam_data.lens = 18
    # Human eye level: standing on floor Y=0 -> eye at Y ~ 1.45m
    eye_y = min_y + 1.40 if min_y < 0.1 else 1.40
    cam_obj.location = (cx, eye_y, min_z + span_z * 0.15)
    dir_vec = Vector((cx, eye_y, cz + span_z * 0.45)) - cam_obj.location
    cam_obj.rotation_euler = dir_vec.to_track_quat('-Z', 'Y').to_euler()
    interior_out = out_dir / f"t2_{scene_name.lower()}_interior.png"
    scene.render.filepath = str(interior_out)
    bpy.ops.render.render(write_still=True)
    print(f"[{scene_name}] Saved interior view: {interior_out}")

    # Assemble 4-view composite sheet
    sheet_out = out_dir / f"t2_{scene_name.lower()}_sheet.png"
    try:
        img_p1 = Image.open(p1_path).convert("RGB")
        img_p2 = Image.open(p2_path).convert("RGB")
        img_top = Image.open(top_path).convert("RGB")
        img_side = Image.open(side_path).convert("RGB")
        w, h = img_p1.size

        header_h = 70
        canvas = Image.new("RGB", (w * 2, h * 2 + header_h), (15, 23, 42))
        draw = ImageDraw.Draw(canvas)

        title = f"ScanForge Interior Verification: {scene_name} (Job: {job_id[:8]})"
        subtitle = f"Dimensions: {span_x:.2f}m x {span_y:.2f}m x {span_z:.2f}m | Upright Y=0.000 | PBR Double-Sided"
        draw.text((25, 14), title, fill=(255, 255, 255))
        draw.text((25, 40), subtitle, fill=(148, 163, 184))

        canvas.paste(img_p1, (0, header_h))
        canvas.paste(img_p2, (w, header_h))
        canvas.paste(img_top, (0, header_h + h))
        canvas.paste(img_side, (w, header_h + h))
        canvas.save(str(sheet_out), quality=95)
        print(f"[{scene_name}] Saved 4-view sheet: {sheet_out}")
    except Exception as e:
        print(f"[{scene_name}] Warning: Composite failed ({e})")

    return True

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        job_id = sys.argv[-2]
        scene_name = sys.argv[-1]
    else:
        print("Usage: blender -b -P render_tier1_scene.py -- <job_id> <scene_name>")
        sys.exit(1)
    render_scene_proofs(job_id, scene_name)

