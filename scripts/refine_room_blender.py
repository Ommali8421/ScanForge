#!/usr/bin/env python3
"""
Blender 4.1 Mesh Refinement & Sealing Script
1. Geometry correction: eliminate spikes, anomalies, stray vertices.
2. Topology integrity: repair and seal all tears, holes, and gaps, specifically floor & ceiling for 100% watertightness.
3. Clarity and recognition: surface smoothing, texture coherence, structural definition.
4. Render 4 diagnostic proof views.
"""

import sys
import math
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

def refine_and_seal(input_glb: str, output_glb: str, render_dir: str):
    print("=" * 60)
    print(" SCANFORGE HIGH-FIDELITY MESH REFINEMENT & WATERTIGHT SEALING")
    print("=" * 60)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    # 1. Import glTF
    print(f"[1/6] Importing {input_glb}...")
    bpy.ops.import_scene.gltf(filepath=input_glb)

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    if not mesh_objs:
        raise RuntimeError("No mesh object found in imported GLB")
    obj = mesh_objs[0]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Extract UV layer and material
    mesh_data = obj.data
    uv_layer = mesh_data.uv_layers.active

    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    initial_verts = len(bm.verts)
    initial_faces = len(bm.faces)
    initial_boundary = len([e for e in bm.edges if e.is_boundary])
    print(f"Initial: {initial_verts:,} verts, {initial_faces:,} faces, {initial_boundary:,} boundary edges")

    # Step A: Geometry Correction - Weld duplicate vertices along split UV seams
    print("[2/6] Welding split UV seam vertices (distance = 0.0005m)...")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    post_weld_boundary = len([e for e in bm.edges if e.is_boundary])
    print(f"Post-weld: {len(bm.verts):,} verts, {len(bm.faces):,} faces, {post_weld_boundary:,} true geometric boundary edges")

    # Step B: Remove spikes & needle triangles
    print("[3/6] Eliminating needle spikes and long sliver triangles...")
    # Calculate median edge length
    edge_lens = [e.calc_length() for e in bm.edges]
    edge_lens.sort()
    med_len = edge_lens[len(edge_lens) // 2]
    max_thresh = 4.5 * med_len

    spikes_removed = 0
    faces_to_remove = []
    for f in bm.faces:
        lens = [e.calc_length() for e in f.edges]
        max_e = max(lens)
        perim = sum(lens)
        area = f.calc_area()
        aspect = (perim ** 2) / (area + 1e-12)
        if max_e > max_thresh or (max_e > 2.0 * med_len and aspect > 100.0):
            faces_to_remove.append(f)

    if faces_to_remove:
        bmesh.ops.delete(bm, geom=faces_to_remove, context='FACES')
        spikes_removed = len(faces_to_remove)
        print(f"Removed {spikes_removed:,} spike/sliver faces (med edge = {med_len:.4f}m)")

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Step C: Topology Integrity - Seal all tears, holes and gaps
    print("[4/6] Repairing and sealing all holes and gaps (bmesh hole filling)...")
    boundary_edges = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.holes_fill(bm, edges=boundary_edges, sides=0)
    added_faces = len(res.get('faces', []))
    print(f"Filled internal holes: +{added_faces:,} new faces generated.")

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Identify remaining boundary loops (specifically floor and ceiling)
    rem_boundary = [e for e in bm.edges if e.is_boundary]
    print(f"Remaining boundary edges before planar floor/ceiling seal: {len(rem_boundary):,}")

    if rem_boundary:
        # Build connected boundary edge chains
        adj = {}
        for e in rem_boundary:
            u, v = e.verts[0], e.verts[1]
            adj.setdefault(u, []).append((v, e))
            adj.setdefault(v, []).append((u, e))

        visited_edges = set()
        loops = []
        for start_edge in rem_boundary:
            if start_edge in visited_edges:
                continue
            loop_verts = [start_edge.verts[0]]
            loop_edges = [start_edge]
            visited_edges.add(start_edge)
            curr_vert = start_edge.verts[1]

            while True:
                loop_verts.append(curr_vert)
                next_edge = None
                for nbr_vert, nbr_edge in adj.get(curr_vert, []):
                    if nbr_edge not in visited_edges:
                        next_edge = nbr_edge
                        curr_vert = nbr_vert
                        break
                if next_edge is None:
                    break
                visited_edges.add(next_edge)
                loop_edges.append(next_edge)

            loops.append((loop_verts, loop_edges))

        print(f"Classifying {len(loops)} remaining boundary loops...")

        # Find room floor height (min Z) and ceiling height (max Z)
        all_z = [v.co.z for v in bm.verts]
        floor_z = min(all_z)
        ceil_z = max(all_z)
        room_height = ceil_z - floor_z
        print(f"Room bounds: Floor Z = {floor_z:.3f}m, Ceiling Z = {ceil_z:.3f}m, Height = {room_height:.3f}m")

        # Seal each boundary loop
        sealed_loops = 0
        for l_idx, (l_verts, l_edges) in enumerate(loops):
            # Calculate loop centroid and height span
            zs = [v.co.z for v in l_verts]
            z_min, z_max = min(zs), max(zs)
            z_mean = sum(zs) / len(zs)
            z_span = z_max - z_min

            is_floor = (z_mean < floor_z + 0.15 * room_height) and (z_span < 0.25 * room_height)
            is_ceil = (z_mean > ceil_z - 0.20 * room_height) and (z_span < 0.25 * room_height)

            if is_floor:
                # Snap boundary vertices precisely to floor_z
                for v in l_verts:
                    v.co.z = floor_z

            # Attempt triangle fill or ear-clipping on planar projection
            try:
                # bmesh.ops.triangle_fill handles complex polygons
                res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=l_edges)
                if res.get('faces'):
                    sealed_loops += 1
            except Exception:
                # If triangle_fill fails on complex multi-loop, create centroid fan
                try:
                    c_x = sum(v.co.x for v in l_verts) / len(l_verts)
                    c_y = sum(v.co.y for v in l_verts) / len(l_verts)
                    c_z = floor_z if is_floor else (ceil_z if is_ceil else z_mean)
                    center_vert = bm.verts.new(Vector((c_x, c_y, c_z)))
                    for e in l_edges:
                        v_a, v_b = e.verts[0], e.verts[1]
                        bm.faces.new((v_a, v_b, center_vert))
                    sealed_loops += 1
                except Exception as ex2:
                    pass

        print(f"Sealed {sealed_loops}/{len(loops)} remaining boundary loops.")

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # Step D: Final Topological Cleaning & Normal Consistency
    print("[5/6] Enforcing normal orientation and surface smoothness...")
    bmesh.ops.dissolve_degenerate(bm, dist=0.0001)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    final_boundary = len([e for e in bm.edges if e.is_boundary])
    print(f"Final boundary edges: {final_boundary} (Watertight: {final_boundary == 0})")

    # Write back to mesh data
    bm.to_mesh(mesh_data)
    bm.free()

    # Apply Auto-smooth / Shade Smooth for clarity and crisp structural recognition
    for p in mesh_data.polygons:
        p.use_smooth = True

    # Save refined GLB
    print(f"[6/6] Exporting refined watertight GLB to {output_glb}...")
    Path(output_glb).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=output_glb,
        export_format='GLB',
        use_selection=False,
        export_apply=True,
        export_materials='EXPORT',
        export_yup=True
    )
    print("Refined GLB exported successfully.")

    # Render diagnostic views
    render_diagnostic_views(output_glb, render_dir)

def render_diagnostic_views(glb_path: str, output_dir: str):
    print("Rendering 4 high-resolution diagnostic proof views...")
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb_path)

    obj = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]

    # Setup Cycles / Eevee renderer
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'RenderSettings') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.film_transparent = False

    # World background
    world = bpy.data.worlds.new("StudioWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.95, 0.95, 0.96, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    # Lighting
    light_data = bpy.data.lights.new("Sun", type='SUN')
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new("Sun", light_data)
    scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (math.radians(50), math.radians(20), math.radians(45))

    # Add camera
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 24
    cam_obj = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # Calculate bounding box
    bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    xs = [c.x for c in bbox_corners]
    ys = [c.y for c in bbox_corners]
    zs = [c.z for c in bbox_corners]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    cz = (min(zs) + max(zs)) / 2
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    span_z = max(zs) - min(zs)
    max_dim = max(span_x, span_y, span_z)

    # View 1: Overview Perspective (Room Structural Definition)
    cam_obj.location = (cx + max_dim * 0.9, cy - max_dim * 0.9, cz + max_dim * 0.6)
    direction = Vector((cx, cy, cz)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "refined_overview_persp.png")
    bpy.ops.render.render(write_still=True)
    print(" - Rendered Overview Perspective")

    # View 2: Floor Watertight Inspection (Looking down at sealed floor)
    cam_obj.location = (cx, cy, cz + max_dim * 0.9)
    direction = Vector((cx, cy, min(zs))) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "refined_floor_watertight.png")
    bpy.ops.render.render(write_still=True)
    print(" - Rendered Floor Inspection View")

    # View 3: Ceiling Watertight Inspection (Looking up at sealed ceiling)
    cam_obj.location = (cx, cy, min(zs) + 0.5)
    direction = Vector((cx, cy, max(zs))) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "refined_ceiling_watertight.png")
    bpy.ops.render.render(write_still=True)
    print(" - Rendered Ceiling Inspection View")

    # View 4: Interior Hall Closeup (Clarity, Recognition, Surface Smoothness)
    cam_obj.location = (cx - max_dim * 0.2, cy - max_dim * 0.3, min(zs) + 1.2)
    direction = Vector((cx + max_dim * 0.3, cy + max_dim * 0.3, min(zs) + 1.2)) - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = str(out_path / "refined_interior_hall.png")
    bpy.ops.render.render(write_still=True)
    print(" - Rendered Interior Hall View")

if __name__ == "__main__":
    in_glb = "/data/jobs/f73e4156-27f7-455c-b793-7e4f2958f4f5/aligned_textured.glb"
    out_glb = "/data/jobs/f73e4156-27f7-455c-b793-7e4f2958f4f5/refined_textured.glb"
    out_dir = "/data/jobs/f73e4156-27f7-455c-b793-7e4f2958f4f5/renders"
    refine_and_seal(in_glb, out_glb, out_dir)
