"""
Render crisp, close-up interior wall textures using Blender.
Mathematically positions camera inside the room directly in front of the dominant interior wall plane,
facing the wall surface center along the inward normal.
"""

import sys
import os
import json
from pathlib import Path
import bpy
import mathutils
import numpy as np


def render_closeup(jid, out_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    glb_path = f"/data/jobs/{jid}/scene_textured.glb"
    if not os.path.exists(glb_path):
        glb_path = f"/data/jobs/{jid}/mesh.glb"
    analysis_path = f"/data/jobs/{jid}/room_analysis.json"
    
    if not os.path.exists(glb_path):
        print(f"File not found: {glb_path}")
        return
        
    bpy.ops.import_scene.gltf(filepath=glb_path)
    
    analysis = {}
    if os.path.exists(analysis_path):
        with open(analysis_path) as f:
            analysis = json.load(f)
            
    wall_planes = analysis.get("wall_planes", [])
    diag = float(analysis.get("scene_diagonal", 30.0))
    up_vec = mathutils.Vector(analysis.get("camera_mean_up", [0.0, -1.0, 0.0])).normalized()
    
    mesh_objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    all_verts = np.concatenate([np.array([o.matrix_world @ v.co for v in o.data.vertices]) for o in mesh_objs])
    
    if wall_planes:
        strongest_wall = max(wall_planes, key=lambda w: w.get("inliers", 0))
        wn = np.array(strongest_wall["normal"], dtype=float)
        wd = float(strongest_wall["d"])
        
        dists = np.abs(np.dot(all_verts, wn) + wd)
        inliers = all_verts[dists < 0.02 * diag]
        if len(inliers) > 10:
            c_wall = np.median(inliers, axis=0)
        else:
            c_wall = -wd * wn
            
        cam_bbox_center = (np.array(analysis.get('cam_bbox_min', [0, 0, 0])) + np.array(analysis.get('cam_bbox_max', [0, 0, 0]))) / 2.0
        to_cam = (cam_bbox_center - c_wall)
        stand_dist = max(0.8, 0.04 * diag)
        # Ensure camera is placed on the side of the cameras (inside the room)
        cam_pos = c_wall + stand_dist * (wn if np.dot(to_cam, wn) > 0 else -wn)
        look_at = c_wall
    else:
        c_wall = np.median(all_verts, axis=0)
        cam_pos = c_wall + np.array([0.0, -1.2, 0.0])
        look_at = c_wall
        
    # Build camera orientation matrix tracking look_at with true up_vec
    forward = (mathutils.Vector(look_at) - mathutils.Vector(cam_pos)).normalized()
    right = forward.cross(up_vec).normalized()
    actual_up = right.cross(forward).normalized()
    R = mathutils.Matrix([
        [right.x, actual_up.x, -forward.x],
        [right.y, actual_up.y, -forward.y],
        [right.z, actual_up.z, -forward.z]
    ])
    
    scene = bpy.context.scene
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    scene.render.image_settings.file_format = 'PNG'
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.light = 'FLAT'
    
    cam_data = bpy.data.cameras.new('CloseCam')
    cam_obj = bpy.data.objects.new('CloseCam', cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_data.lens = 40
    cam_obj.matrix_world = mathutils.Matrix.Translation(cam_pos) @ R.to_4x4()
    
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print(f"Rendered wall close-up: {out_path} (aimed at {look_at} from {cam_pos})")


def main():
    if len(sys.argv) < 4:
        print("Usage: blender -b -P render_wall_closeup.py -- <jid> <out_path>")
        return
    args = sys.argv[sys.argv.index("--") + 1:]
    jid, out_path = args[0], args[1]
    render_closeup(jid, out_path)


if __name__ == "__main__":
    main()
