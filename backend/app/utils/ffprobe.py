"""
FFprobe Video Metadata Prober
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def probe_video(video_path: Path) -> Dict[str, Any]:
    """
    Probe video file metadata using ffprobe.
    Returns duration, width, height, fps, and codec information.
    """
    ffprobe_cmd = shutil.which("ffprobe")
    if not ffprobe_cmd:
        return {
            "duration": 0.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "unknown",
            "probed": False
        }

    cmd = [
        ffprobe_cmd,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if res.returncode != 0:
            return {"duration": 0.0, "width": 1920, "height": 1080, "fps": 30.0, "probed": False}

        data = json.loads(res.stdout)
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        format_info = data.get("format", {})

        duration = float(format_info.get("duration", 0.0))
        width = int(video_stream.get("width", 1920))
        height = int(video_stream.get("height", 1080))
        codec = video_stream.get("codec_name", "unknown")
        pix_fmt = video_stream.get("pix_fmt", "unknown")
        color_transfer = video_stream.get("color_transfer", "unknown")
        color_primaries = video_stream.get("color_primaries", "unknown")

        # Determine rotation (from tags or side data)
        rotation = 0
        tags = video_stream.get("tags", {})
        if "rotate" in tags:
            try:
                rotation = int(float(tags["rotate"]))
            except (ValueError, TypeError):
                pass
        for side_data in video_stream.get("side_data_list", []):
            if "rotation" in side_data:
                try:
                    rotation = int(float(side_data["rotation"]))
                except (ValueError, TypeError):
                    pass

        # Normalize rotation to 0, 90, 180, 270
        rotation = rotation % 360

        # Calculate effective dimensions based on display rotation
        if rotation in (90, 270):
            effective_width = height
            effective_height = width
        else:
            effective_width = width
            effective_height = height

        # Detect 10-bit / HDR
        is_10bit = any(x in pix_fmt for x in ("10le", "10be", "p10", "10-bit"))
        is_hdr = is_10bit or color_transfer in ("smpte2084", "arib-std-b67", "linear")

        # Calculate fps
        r_frame_rate = video_stream.get("r_frame_rate", "30/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(r_frame_rate)

        nb_frames = video_stream.get("nb_frames")
        if nb_frames:
            try:
                nb_frames = int(nb_frames)
            except (ValueError, TypeError):
                nb_frames = int(duration * fps) if duration > 0 else 0
        else:
            nb_frames = int(duration * fps) if duration > 0 else 0

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "effective_width": effective_width,
            "effective_height": effective_height,
            "fps": fps,
            "nb_frames": nb_frames,
            "codec": codec,
            "pix_fmt": pix_fmt,
            "rotation": rotation,
            "is_hdr": is_hdr,
            "color_transfer": color_transfer,
            "color_primaries": color_primaries,
            "probed": True
        }
    except Exception:
        return {
            "duration": 0.0,
            "width": 1920,
            "height": 1080,
            "effective_width": 1920,
            "effective_height": 1080,
            "fps": 30.0,
            "nb_frames": 0,
            "codec": "unknown",
            "pix_fmt": "unknown",
            "rotation": 0,
            "is_hdr": False,
            "color_transfer": "unknown",
            "color_primaries": "unknown",
            "probed": False
        }
