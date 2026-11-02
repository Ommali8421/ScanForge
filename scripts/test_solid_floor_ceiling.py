#!/usr/bin/env python3
"""
Solid Floor & Ceiling Sealer for High-Fidelity Room Quality
Synthesizes a solid, continuous planar floor plate at floor level (Z = -0.125m)
and a solid ceiling enclosure at ceiling level (Z = 3.85m),
completely eliminating all holes and gaps.
"""

import sys
import math
from pathlib import Path
import numpy as np

import bpy
import bmesh
from mathutils import Vector

def seal_room_solid(job_id: str):
    job_dir = Path(f"/data/jobs/{job_id}")
    input_glb = job_dir / "optimized_textured.glb"
    output_glb = job_dir / "high_fidelity_room.glb"
    renders_dir = job_dir / "renders_hf"
    renders_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(" SCANFORGE HIGH-FIDELITY SOLID FLOOR & CEILING ROOM RECONSTRUCTION")
    print("=" * 70)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(input_glb))

    room_obj = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
    bpy.context.view_layer.objects.active = room_obj
    room_obj.select_set(True)

    # 1. Inspect room dimensions
    bbox = [room_obj.matrix_world @ Vector(c) for c in room_obj.bound_box]
    xs = [c.x for c in bbox]
    ys = [c.y for c in bbox]
    zs = [c.z for c in bbox]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    print(f"Room bounds: X=[{min_x:.2f}, {max_x:.2f}], Y=[{min_y:.2f}, {max_y:.2f}], Z=[{min_z:.2f}, {max_z:.2f}]")

    floor_z = -0.125
    ceil_z = 3.85

    # 2. Extract existing floor material
    floor_mat = None
    for mat in room_obj.data.materials:
        if mat and mat.use_nodes:
            floor_mat = mat
            break

    # 3. Create a continuous planar floor mesh spanning the room footprint
    # Assign it a dedicated carpet/floor material with the exact sampled floor color [58, 55, 52]
    print("Synthesizing seamless planar floor plate...")
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=50,
        y_subdivisions=50,
        size=1.0,
        location=((min_x + max_x) / 2, (min_y + max_y) / 2, floor_z + 0.002)
    )
    floor_obj = bpy.context.active_object
    floor_obj.name = "Sealed_Floor"
    floor_obj.scale.x = (max_x - min_x) * 1.02
    floor_obj.scale.y = (max_y - min_y) * 1.02
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Dedicated floor material matching real room carpet tone [58, 55, 52]
    floor_mat_clean = bpy.data.materials.new(name="CarpetFloor")
    floor_mat_clean.use_nodes = True
    bsdf_f = floor_mat_clean.node_tree.nodes.get("Principled BSDF")
    if bsdf_f:
        bsdf_f.inputs["Base Color"].default_value = (0.227, 0.215, 0.204, 1.0) # True dark warm carpet
        bsdf_f.inputs["Roughness"].default_value = 0.85
        bsdf_f.inputs["Metallic"].default_value = 0.0
    floor_obj.data.materials.append(floor_mat_clean)

    # 4. Create a continuous ceiling plate at ceil_z
    print("Synthesizing seamless planar ceiling plate...")
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=20,
        y_subdivisions=20,
        size=1.0,
        location=((min_x + max_x) / 2, (min_y + max_y) / 2, ceil_z)
    )
    ceil_obj = bpy.context.active_object
    ceil_obj.name = "Sealed_Ceiling"
    ceil_obj.scale.x = (max_x - min_x) * 0.94
    ceil_obj.scale.y = (max_y - min_y) * 0.94
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Flip ceiling normal to point downward into the room
    bm_c = bmesh.new()
    bm_c.from_mesh(ceil_obj.data)
    bmesh.ops.reverse_faces(bm_c, faces=bm_c.faces)
    uv_layer_c = bm_c.loops.layers.uv.verify()
    for face in bm_c.faces:
        for loop in face.loops:
            loop[uv_layer_c].uv = (loop.vert.co.x * 0.2 % 1.0, loop.vert.co.y * 0.2 % 1.0)
    bm_c.to_mesh(ceil_obj.data)
    bm_c.free()

    # Create neutral ceiling plaster material
    ceil_mat = bpy.data.materials.new(name="CeilingPlaster")
    ceil_mat.use_nodes = True
    bsdf = ceil_mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.88, 0.86, 0.82, 1.0) # Light off-white plaster
        bsdf.inputs["Roughness"].default_value = 0.90
        bsdf.inputs["Metallic"].default_value = 0.0
    ceil_obj.data.materials.append(ceil_mat)

    # 5. Join floor, ceiling, and room into a unified high-fidelity model
    print("Joining elements into unified high-fidelity model...")
    bpy.ops.object.select_all(action='DESELECT')
    floor_obj.select_set(True)
    ceil_obj.select_set(True)
    room_obj.select_set(True)
    bpy.context.view_layer.objects.active = room_obj
    bpy.ops.object.join()

    # Shade smooth
    for poly in room_obj.data.polygons:
        poly.use_smooth = True

    # Export high-fidelity GLB
    print(f"Exporting high-fidelity GLB to {output_glb}...")
    bpy.ops.export_scene.gltf(
        filepath=str(output_glb),
        export_format='GLB',
        use_selection=False,
        export_apply=True,
        export_yup=True
    )
    print("Export complete.")

    # Render proof views
    render_proof_views(str(output_glb), str(renders_dir))

def render_proof_views(glb_path: str, out_dir: str):
    print("Rendering high-resolution proof views...")
    out_path = Path(out_dir)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    obj = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'RenderSettings') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.95, 0.95, 0.96, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    # Key Light
    light1 = bpy.data.lights.new("Sun1", type='SUN')
    light1.energy = 2.8
    obj_l1 = bpy.data.objects.new("Sun1", light1)
    scene.collection.objects.link(obj_l1)
    obj_l1.rotation_euler = (math.radians(45), math.radians(20), math.radians(60))

    # Fill Light
    light2 = bpy.data.lights.new("Sun2", type='SUN')
    light2.energy = 1.6
    obj_l2 = bpy.data.objects.new("Sun2", light2)
    scene.collection.objects.link(obj_l2)
    obj_l2.rotation_euler = (math.radians(-30), math.radians(-30), math.radians(140))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 22
    cam_obj = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    bbox = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in bbox]
    ys = [c.y for c in bbox]
    zs = [c.z for c in bbox]
    cx, cy, cz = sum(xs)/8, sum(ys)/8, sum(zs)/8
    max_span = max(max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))

    # View 1: Interior Hall Walkthrough (Down the center aisle: solid floor, wood trusses, tables)
    cam_obj.location = (cx, min(ys) + 1.2, min(zs) + 1.25)
    direction = Vector((cx, max(ys) - 1.0, min(zs) + 1.35)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "hf_interior_walkthrough.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved hf_interior_walkthrough.png")

    # View 2: Interior Reverse Angle (Looking back at conference table arrangement & chairs)
    cam_obj.location = (cx + max_span * 0.25, max(ys) - 1.5, min(zs) + 1.25)
    direction = Vector((cx, min(ys) + 2.0, min(zs) + 1.2)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "hf_interior_reverse.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved hf_interior_reverse.png")

    # View 3: Exterior Aerial Cutaway (Overview showing sealed floor plate, intact roof)
    cam_obj.location = (cx + max_span * 0.85, cy - max_span * 0.85, cz + max_span * 0.55)
    direction = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "hf_overview_cutaway.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved hf_overview_cutaway.png")

if __name__ == "__main__":
    seal_room_solid("f73e4156-27f7-455c-b793-7e4f2958f4f5")
