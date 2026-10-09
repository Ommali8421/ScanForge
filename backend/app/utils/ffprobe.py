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
        
        # Calculate fps
        r_frame_rate = video_stream.get("r_frame_rate", "30/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(r_frame_rate)

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "fps": fps,
            "codec": video_stream.get("codec_name", "unknown"),
            "probed": True
        }
    except Exception:
        return {
            "duration": 0.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "codec": "unknown",
            "probed": False
        }
