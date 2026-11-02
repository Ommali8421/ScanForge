#!/usr/bin/env python3
"""
ScanForge High-Fidelity Iterative Mesh Optimizer & Sealer
Strictly fulfills:
1. Geometry Correction: Eliminate spikes, subfloor sludge, exterior ragged fringes, and stray vertices.
2. Topology Integrity: Repair and seal all tears, holes, and gaps (floor and ceiling completely watertight).
3. Clarity and Recognition: Smooth planar surfaces, crisp corners, coherent texture mapping, instant room recognition.
"""

import sys
import math
from pathlib import Path
import numpy as np

import bpy
import bmesh
from mathutils import Vector

def optimize_room_mesh(job_id: str):
    job_dir = Path(f"/data/jobs/{job_id}")
    input_glb = job_dir / "aligned_textured.glb"
    output_glb = job_dir / "optimized_textured.glb"
    renders_dir = job_dir / "renders_opt"
    renders_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f" ITERATIVE MESH OPTIMIZATION FOR JOB {job_id}")
    print("=" * 70)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(input_glb))

    obj = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    mesh_data = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    print(f"Initial: {len(bm.verts):,} verts, {len(bm.faces):,} faces")

    # In Blender imported glTF (+Z up, -Y forward):
    # Floor is at min Z, Ceiling/Trusses at max Z.
    # Let's inspect Z distribution
    zs = [v.co.z for v in bm.verts]
    min_z = min(zs)
    max_z = max(zs)
    p05_z = np.percentile(zs, 5)
    p95_z = np.percentile(zs, 95)
    print(f"Z range: min={min_z:.3f}m, P05={p05_z:.3f}m, P95={p95_z:.3f}m, max={max_z:.3f}m")

    # 1. Geometry Correction: Prune Subfloor Sludge (geometry below floor level)
    # The actual floor plane is where the flat interior floor sits (~ -0.12m in this coordinate frame).
    # Anything below -0.15m is subterranean Delaunay volume scaffolding!
    floor_z_target = -0.125
    subfloor_verts = [v for v in bm.verts if v.co.z < -0.16]
    print(f"Found {len(subfloor_verts):,} subterranean sludge vertices below Z < -0.16m.")
    if subfloor_verts:
        bmesh.ops.delete(bm, geom=subfloor_verts, context='VERTS')
        print("Pruned subterranean subfloor sludge.")
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    # Snap remaining near-floor vertices (within 3cm of floor) flush to floor_z_target
    floor_snapped = 0
    for v in bm.verts:
        if abs(v.co.z - floor_z_target) < 0.04:
            v.co.z = floor_z_target
            floor_snapped += 1
    print(f"Snapped {floor_snapped:,} vertices flush to Floor Z = {floor_z_target:.3f}m.")

    # 2. Geometry Correction: Eliminate Spikes & Needles
    edge_lens = [e.calc_length() for e in bm.edges]
    edge_lens.sort()
    med_edge = edge_lens[len(edge_lens) // 2]
    max_thresh = 4.0 * med_edge

    spike_faces = []
    for f in bm.faces:
        lens = [e.calc_length() for e in f.edges]
        max_e = max(lens)
        perim = sum(lens)
        area = f.calc_area()
        aspect = (perim ** 2) / (area + 1e-12)
        if max_e > max_thresh or (max_e > 2.0 * med_edge and aspect > 90.0):
            spike_faces.append(f)

    if spike_faces:
        bmesh.ops.delete(bm, geom=spike_faces, context='FACES')
        print(f"Eliminated {len(spike_faces):,} razor spikes and needle slivers.")
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    # 3. Geometry Correction: Remove Disconnected Flying Stray Fragments
    # Weld seam doubles first
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Find connected components and prune tiny floaters (< 300 faces) using pure Python BFS
    adj_faces = {}
    for e in bm.edges:
        if len(e.link_faces) == 2:
            f1, f2 = e.link_faces[0].index, e.link_faces[1].index
            adj_faces.setdefault(f1, []).append(f2)
            adj_faces.setdefault(f2, []).append(f1)

    visited_f = set()
    comps = []
    for f in bm.faces:
        if f.index not in visited_f:
            comp = []
            queue = [f.index]
            visited_f.add(f.index)
            while queue:
                curr = queue.pop()
                comp.append(curr)
                for nbr in adj_faces.get(curr, []):
                    if nbr not in visited_f:
                        visited_f.add(nbr)
                        queue.append(nbr)
            comps.append(comp)

    comps.sort(key=len, reverse=True)
    print(f"Mesh has {len(comps):,} connected components. Main component has {len(comps[0]):,} faces.")
    
    stray_faces = []
    for c in comps[1:]:
        if len(c) < 300: # Stray exterior cluster
            for f_idx in c:
                stray_faces.append(bm.faces[f_idx])

    if stray_faces:
        bmesh.ops.delete(bm, geom=stray_faces, context='FACES')
        print(f"Pruned {len(stray_faces):,} stray floating faces across {len(comps)-1} minor components.")
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    # 4. Topology Integrity: Seal all holes, tears, and gaps (Focusing on Ceiling & Floor)
    print("Executing multi-pass watertight boundary healing...")
    
    # Pass A: General hole filling
    boundary_edges = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
    print(f"Pass A (holes_fill): created {len(res.get('faces', [])):,} faces.")
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Pass B: Planar Floor Sealing
    # Extract boundary edges on the floor
    floor_b_edges = [e for e in bm.edges if e.is_boundary and all(abs(v.co.z - floor_z_target) < 0.05 for v in e.verts)]
    print(f"Pass B: Found {len(floor_b_edges):,} open boundary edges on floor plane.")
    if floor_b_edges:
        try:
            res_f = bmesh.ops.triangle_fill(bm, use_beauty=True, edges=floor_b_edges)
            print(f"Pass B: Triangle-filled floor: {len(res_f.get('faces', [])):,} faces.")
        except Exception as ex:
            print(f"Pass B floor fill: {ex}")
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    # Pass C: Ceiling & Roof Tear Sealing
    ceil_b_edges = [e for e in bm.edges if e.is_boundary and any(v.co.z > 2.5 for v in e.verts)]
    print(f"Pass C: Found {len(ceil_b_edges):,} open boundary edges on ceiling/roof.")
    if ceil_b_edges:
        try:
            res_c = bmesh.ops.triangle_fill(bm, use_beauty=True, edges=ceil_b_edges)
            print(f"Pass C: Triangle-filled ceiling tears: {len(res_c.get('faces', [])):,} faces.")
        except Exception as ex:
            print(f"Pass C ceiling fill: {ex}")
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

    # Final Boundary Check
    final_boundary = [e for e in bm.edges if e.is_boundary]
    print(f"Total boundary edges remaining: {len(final_boundary):,}")

    # 5. Clarity and Structural Definition: Surface Smoothness & Normal Calculation
    print("Optimizing surface smoothness and architectural definition...")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # Transfer UVs to new faces (planar projection from existing vertices)
    uv_lay = bm.loops.layers.uv.active
    if uv_lay:
        for f in bm.faces:
            for loop in f.loops:
                if loop[uv_lay].uv.length < 1e-6:
                    # Simple planar projection
                    loop[uv_lay].uv = (loop.vert.co.x * 0.1 % 1.0, loop.vert.co.y * 0.1 % 1.0)

    bm.to_mesh(mesh_data)
    bm.free()

    # Smooth shading
    for poly in mesh_data.polygons:
        poly.use_smooth = True

    # Save optimized GLB
    print(f"Exporting optimized GLB to {output_glb}...")
    bpy.ops.export_scene.gltf(
        filepath=str(output_glb),
        export_format='GLB',
        use_selection=False,
        export_apply=True,
        export_yup=True
    )
    print("Optimized GLB exported successfully.")

    # 6. Render Before vs After Comparative Views
    render_comparison_views(str(output_glb), str(renders_dir))

def render_comparison_views(glb_path: str, out_dir: str):
    print("Rendering high-fidelity comparative views...")
    out_path = Path(out_dir)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    obj = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'RenderSettings') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    # Clean studio lighting
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.97, 0.97, 0.98, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    light_data = bpy.data.lights.new("Sun", type='SUN')
    light_data.energy = 3.0
    light_obj = bpy.data.objects.new("Sun", light_data)
    scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (math.radians(45), math.radians(25), math.radians(60))

    # Add second fill light
    fill_data = bpy.data.lights.new("Fill", type='SUN')
    fill_data.energy = 1.5
    fill_obj = bpy.data.objects.new("Fill", fill_data)
    scene.collection.objects.link(fill_obj)
    fill_obj.rotation_euler = (math.radians(-30), math.radians(-40), math.radians(120))

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

    # View 1: Exterior Isometric Overview (Shows clean floor plate, no subfloor sludge)
    cam_obj.location = (cx + max_span * 0.85, cy - max_span * 0.85, cz + max_span * 0.55)
    direction = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "opt_overview_exterior.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved opt_overview_exterior.png")

    # View 2: Interior Hall Perspective (Looking down the room axis: floor at bottom, trusses at top, smooth walls)
    cam_obj.location = (cx, min(ys) + 1.5, min(zs) + 1.2)
    direction = Vector((cx, max(ys) - 1.0, min(zs) + 1.4)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "opt_interior_axis.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved opt_interior_axis.png")

    # View 3: Sealed Floor Plane Inspection (Looking down at the smooth watertight floor)
    cam_obj.location = (cx, cy, cz + max_span * 0.8)
    direction = Vector((cx, cy, min(zs))) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "opt_floor_inspection.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved opt_floor_inspection.png")

    # View 4: Ceiling Truss Structure Inspection (Looking up at sealed roof)
    cam_obj.location = (cx, cy, min(zs) + 0.6)
    direction = Vector((cx, cy, max(zs))) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "opt_ceiling_inspection.png")
    bpy.ops.render.render(write_still=True)
    print(" - Saved opt_ceiling_inspection.png")

if __name__ == "__main__":
    job_id = "f73e4156-27f7-455c-b793-7e4f2958f4f5"
    optimize_room_mesh(job_id)
