# LiDAR & RGB-D Input Specification (docs/LIDAR_INPUT_FORMAT.md)

Specification for LiDAR and RGB-D depth captures supported by ScanForge.

---

## 1. Supported Input Formats

### 1.1 Record3D (`.r3d`)
Standard ZIP archive exported directly from the Record3D iOS application containing:
- `metadata`: JSON file detailing camera intrinsics, FPS, and timestamps.
- `poses`: 4x4 camera transformation matrices for each frame.
- `rgb/`: Compressed JPEG color frames.
- `depth/`: LZFSE-compressed 32-bit floating point depth maps in meters.

### 1.2 Generic RGB-D ZIP Archive
A standard ZIP file containing:
```
manifest.json
color/
  frame_00001.jpg
  frame_00002.jpg
depth/
  depth_00001.png   (16-bit millimeter or float32 meters)
  depth_00002.png
poses/              (optional if SfM is required)
  pose_00001.txt    (4x4 matrix)
```

`manifest.json` schema:
```json
{
  "camera": {
    "fx": 1420.5,
    "fy": 1420.5,
    "cx": 960.0,
    "cy": 540.0,
    "depth_scale": 1000.0
  },
  "coordinate_frame": "opencv",
  "fps": 30
}
```
