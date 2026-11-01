import sys
import os
from pathlib import Path
import bpy
import mathutils
import numpy as np

def render_closeup(name, jid):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb_path = f"/data/jobs/{jid}/scene_textured.glb"
    if not os.path.exists(glb_path):
        print(f"File not found: {glb_path}")
        return
        
    bpy.ops.import_scene.gltf(filepath=glb_path)
    
    scene = bpy.context.scene
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    scene.render.image_settings.file_format = 'PNG'
    
    # Setup camera and lighting
    cam_data = bpy.data.cameras.new('CloseCam')
    cam_obj = bpy.data.objects.new('CloseCam', cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_data.lens = 40
    
    # World lighting
    world = bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.9, 0.9, 0.9, 1.0)
    bg.inputs['Strength'].default_value = 1.0
    
    # Sun light
    light_data = bpy.data.lights.new('Sun', type='SUN')
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new('Sun', light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.rotation_euler = (0.6, 0.2, 0.8)
    
    # Calculate bounding box of mesh
    mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    all_verts = []
    for o in mesh_objs:
        for v in o.data.vertices:
            all_verts.append(o.matrix_world @ v.co)
    all_verts = np.array(all_verts)
    center = np.median(all_verts, axis=0)
    
    if name == 'house':
        # Point camera at living room wall
        cam_obj.location = mathutils.Vector((center[0] - 0.5, center[1] - 1.2, center[2] - 0.3))
        target = mathutils.Vector((center[0] - 0.5, center[1] + 1.8, center[2] - 0.3))
    else:
        # Point camera at bedroom wall
        cam_obj.location = mathutils.Vector((center[0] + 0.3, center[1] - 0.9, center[2] - 0.4))
        target = mathutils.Vector((center[0] + 0.3, center[1] + 1.6, center[2] - 0.4))
        
    direction = target - cam_obj.location
    cam_obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    
    os.makedirs("/data/outputs", exist_ok=True)
    out_path = f"/data/outputs/{name}_wall_closeup.png"
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"Rendered wall close-up: {out_path}")

render_closeup("house", "f0e89d25-b4fb-4878-abef-3c2dc479bf35")
render_closeup("tour", "2b7b3bcc-0c24-40ed-82b0-b2e2d4c82351")
