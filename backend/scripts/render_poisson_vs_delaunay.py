"""
Render Poisson vs Delaunay side-by-side comparison views using Blender.
High-contrast configuration: Dark slate background, crisp architectural clay,
three-point cavity lighting.
"""

import sys
import os
import bpy
import mathutils
import numpy as np

def render_mesh(mesh_path, out_path, is_glb=False, camera_setup=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    if is_glb:
        bpy.ops.import_scene.gltf(filepath=mesh_path)
    else:
        bpy.ops.wm.ply_import(filepath=mesh_path)
        
    scene = bpy.context.scene
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.image_settings.file_format = 'PNG'
    scene.render.engine = 'BLENDER_WORKBENCH'
    
    # 1. Dark slate background for high contrast
    world = bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.07, 0.09, 0.13, 1.0)  # Dark slate #121721
    bg.inputs['Strength'].default_value = 1.0
    
    # 2. Crisp architectural clay material
    mat = bpy.data.materials.new("ClayHighContrast")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.86, 0.84, 0.81, 1.0)  # Crisp light stone
    bsdf.inputs["Roughness"].default_value = 0.35
    
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            if not obj.data.materials:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat
                
    # 3. Workbench Cavity / Ridge highlighting to accentuate geometric contours
    scene.render.film_transparent = True
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.86, 0.84, 0.81)
    scene.display.shading.light = "MATCAP"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.cavity_ridge_factor = 2.0
    scene.display.shading.cavity_valley_factor = 2.0
    
    # 4. Three-point lighting
    # Key Light (warm)
    key_data = bpy.data.lights.new('Key', type='SUN')
    key_data.energy = 3.5
    key_data.color = (1.0, 0.98, 0.92)
    key_obj = bpy.data.objects.new('Key', key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.rotation_euler = (0.7, 0.3, 0.5)
    
    # Fill Light (cool sky)
    fill_data = bpy.data.lights.new('Fill', type='SUN')
    fill_data.energy = 1.8
    fill_data.color = (0.70, 0.82, 1.0)
    fill_obj = bpy.data.objects.new('Fill', fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.rotation_euler = (-0.5, -0.4, 2.2)
    
    # Rim Light (crisp silhouette)
    rim_data = bpy.data.lights.new('Rim', type='SUN')
    rim_data.energy = 2.5
    rim_data.color = (1.0, 1.0, 1.0)
    rim_obj = bpy.data.objects.new('Rim', rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.rotation_euler = (1.2, -0.6, -1.8)
    
    # Camera
    cam_data = bpy.data.cameras.new('Cam')
    cam_obj = bpy.data.objects.new('Cam', cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_data.lens = 35
    
    if camera_setup:
        cam_obj.location = camera_setup["loc"]
        cam_obj.rotation_euler = camera_setup["rot"]
    else:
        # Fit bounding box
        mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
        all_verts = []
        for o in mesh_objs:
            for v in o.data.vertices:
                all_verts.append(o.matrix_world @ v.co)
        all_verts = np.array(all_verts)
        center = np.median(all_verts, axis=0)
        extents = np.max(all_verts, axis=0) - np.min(all_verts, axis=0)
        max_dim = np.max(extents)
        
        cam_pos = center + np.array([1.2 * max_dim, -1.2 * max_dim, 0.8 * max_dim])
        cam_obj.location = cam_pos
        direction = mathutils.Vector(center) - mathutils.Vector(cam_pos)
        cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    return {"loc": cam_obj.location.copy(), "rot": cam_obj.rotation_euler.copy()}

def main():
    if len(sys.argv) < 6:
        print("Usage: blender -b -P render_poisson_vs_delaunay.py -- <del_ply> <poi_glb> <out_del_png> <out_poi_png>")
        return
    args = sys.argv[sys.argv.index("--") + 1:]
    del_ply, poi_glb, out_del, out_poi = args[0], args[1], args[2], args[3]
    
    cam_setup = render_mesh(del_ply, out_del, is_glb=False)
    print(f"Rendered Delaunay: {out_del}")
    render_mesh(poi_glb, out_poi, is_glb=True, camera_setup=cam_setup)
    print(f"Rendered Poisson: {out_poi}")

if __name__ == "__main__":
    main()
