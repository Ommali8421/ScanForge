"""
Single Model Roundtrip Renderer in Blender 4.1
Imports a GLB or FBX file, creates a ground grid at Z=0.000,
positions camera and lighting, and renders a high-contrast textured view.
"""

import sys
import math
import bpy
import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
model_path = argv[0]
out_png = argv[1]
model_type = argv[2]  # 'glb' or 'fbx'

# Clear scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# 1. Import model
if model_type.lower() == 'glb':
    bpy.ops.import_scene.gltf(filepath=model_path)
elif model_type.lower() == 'fbx':
    bpy.ops.import_scene.fbx(filepath=model_path)
else:
    raise ValueError(f"Unknown model type: {model_type}")

mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
if not mesh_objs:
    raise RuntimeError("No mesh objects found after import!")

# Compute combined bounding box across imported mesh objects
all_coords = []
for obj in mesh_objs:
    for corner in obj.bound_box:
        all_coords.append(obj.matrix_world @ mathutils.Vector(corner))

xs = [v.x for v in all_coords]
ys = [v.y for v in all_coords]
zs = [v.z for v in all_coords]

min_x, max_x = min(xs), max(xs)
min_y, max_y = min(ys), max(ys)
min_z, max_z = min(zs), max(zs)

cx = (min_x + max_x) / 2.0
cy = (min_y + max_y) / 2.0
cz = (min_z + max_z) / 2.0
dx = max_x - min_x
dy = max_y - min_y
dz = max_z - min_z
extent = max(dx, dy, 5.0)

# 2. Add ground grid plane at Z = 0.000
grid_size = max(extent * 1.5, 30.0)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=24, y_subdivisions=24, size=grid_size, location=(cx, cy, 0.0))
grid_obj = bpy.context.active_object
grid_obj.name = "GroundGrid"

# Wireframe modifier on grid
wire_mod = grid_obj.modifiers.new(name="Wireframe", type='WIREFRAME')
wire_mod.thickness = 0.04
wire_mod.use_replace = True

# Material for ground grid (cyan-tinted grid line)
grid_mat = bpy.data.materials.new(name="GridMaterial")
grid_mat.use_nodes = True
nodes = grid_mat.node_tree.nodes
nodes.clear()
bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
bsdf.inputs["Base Color"].default_value = (0.2, 0.65, 0.95, 1.0)
bsdf.inputs["Roughness"].default_value = 0.4
out_node = nodes.new(type="ShaderNodeOutputMaterial")
grid_mat.node_tree.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
grid_obj.data.materials.append(grid_mat)

# 3. Add solid dark ground plane slightly below (Z = -0.01) for shadow/contrast
bpy.ops.mesh.primitive_plane_add(size=grid_size, location=(cx, cy, -0.01))
floor_plane = bpy.context.active_object
floor_plane.name = "GroundFloor"
floor_mat = bpy.data.materials.new(name="GroundFloorMat")
floor_mat.use_nodes = True
nodes2 = floor_mat.node_tree.nodes
nodes2.clear()
bsdf2 = nodes2.new(type="ShaderNodeBsdfPrincipled")
bsdf2.inputs["Base Color"].default_value = (0.05, 0.07, 0.10, 1.0)
bsdf2.inputs["Roughness"].default_value = 0.9
out_node2 = nodes2.new(type="ShaderNodeOutputMaterial")
floor_mat.node_tree.links.new(bsdf2.outputs["BSDF"], out_node2.inputs["Surface"])
floor_plane.data.materials.append(floor_mat)

# 4. Camera setup: Isometric 3/4 elevated view
cam_data = bpy.data.cameras.new("RenderCam")
cam_data.lens = 32
cam_obj = bpy.data.objects.new("RenderCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

dist = extent * 1.35
cam_x = cx + dist * 0.75
cam_y = cy - dist * 0.85
cam_z = max(cz + dz * 0.65, dz * 0.95)
cam_obj.location = (cam_x, cam_y, cam_z)

# Aim camera at (cx, cy, cz * 0.4)
target = mathutils.Vector((cx, cy, cz * 0.4))
direction = target - cam_obj.location
rot_quat = direction.to_track_quat('-Z', 'Y')
cam_obj.rotation_euler = rot_quat.to_euler()

# 5. Lighting
key_light = bpy.data.lights.new("KeyLight", 'SUN')
key_light.energy = 4.0
key_obj = bpy.data.objects.new("KeyLight", key_light)
bpy.context.collection.objects.link(key_obj)
key_obj.location = (cx + dist, cy - dist, cz + dist)
key_dir = target - key_obj.location
key_obj.rotation_euler = key_dir.to_track_quat('-Z', 'Y').to_euler()

fill_light = bpy.data.lights.new("FillLight", 'SUN')
fill_light.energy = 2.0
fill_light.color = (0.7, 0.85, 1.0)
fill_obj = bpy.data.objects.new("FillLight", fill_light)
bpy.context.collection.objects.link(fill_obj)
fill_obj.location = (cx - dist, cy + dist, cz + dist)
fill_dir = target - fill_obj.location
fill_obj.rotation_euler = fill_dir.to_track_quat('-Z', 'Y').to_euler()

# 6. Workbench with Texture shading for crisp rendering
bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
bpy.context.scene.display.shading.color_type = 'TEXTURE'
bpy.context.scene.display.shading.light = 'STUDIO'
bpy.context.scene.display.shading.show_cavity = True
bpy.context.scene.display.shading.cavity_type = 'BOTH'
bpy.context.scene.display.shading.cavity_ridge_factor = 1.2
bpy.context.scene.display.shading.cavity_valley_factor = 1.2

# Set viewport background
bpy.context.scene.display.shading.background_type = 'VIEWPORT'
bpy.context.scene.display.shading.background_color = (0.07, 0.09, 0.13)

# Render resolution
bpy.context.scene.render.resolution_x = 960
bpy.context.scene.render.resolution_y = 540
bpy.context.scene.render.filepath = out_png

bpy.ops.render.render(write_still=True)
print(f"Rendered {out_png} successfully!")
