"""
Render Poisson vs Delaunay side-by-side comparison views using Blender.
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
    
    # Material / Shading
    mat = bpy.data.materials.new("Clay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.78, 0.80, 0.82, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            if not obj.data.materials:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat
                
    # World
    world = bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.95, 0.95, 0.95, 1.0)
    bg.inputs['Strength'].default_value = 1.0
    
    # Lighting
    light_data = bpy.data.lights.new('Key', type='SUN')
    light_data.energy = 2.0
    key_obj = bpy.data.objects.new('Key', light_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.rotation_euler = (0.7, 0.3, 0.5)
    
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
    os.makedirs("/data/outputs/comparison", exist_ok=True)
    
    jobs = [
        ("house", "f0e89d25-b4fb-4878-abef-3c2dc479bf35"),
        ("tour", "2b7b3bcc-0c24-40ed-82b0-b2e2d4c82351")
    ]
    
    for name, jid in jobs:
        del_ply = f"/data/jobs/{jid}/mesh_repaired.ply"
        poi_glb = f"/data/jobs/{jid}/mesh_poisson.glb"
        
        out_del = f"/data/outputs/comparison/{name}_delaunay.png"
        out_poi = f"/data/outputs/comparison/{name}_poisson.png"
        
        cam_setup = render_mesh(del_ply, out_del, is_glb=False)
        print(f"Rendered Delaunay: {out_del}")
        render_mesh(poi_glb, out_poi, is_glb=True, camera_setup=cam_setup)
        print(f"Rendered Poisson: {out_poi}")

if __name__ == "__main__":
    main()
