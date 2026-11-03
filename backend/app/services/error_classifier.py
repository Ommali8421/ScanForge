"""
Error Classification & Actionable Remediation Diagnostics (Milestone P5)
Categorizes pipeline exceptions and log patterns into structured error codes
with clear, human-friendly explanations and actionable recovery checklists.
"""

import re
from typing import Dict, Any, List, Optional


ERROR_DEFINITIONS = {
    "ERR_LOW_SFM_REGISTRATION": {
        "title": "Insufficient Camera Registration",
        "summary": "Structure-from-Motion was unable to register enough camera frames (< 60%) to establish a stable 3D sparse point cloud.",
        "remediation": [
            "Increase camera overlap between successive frames (aim for > 70% overlap).",
            "Move the camera slowly and smoothly along a continuous perimeter loop.",
            "Ensure the room is evenly illuminated and avoid featureless blank walls by including corners or furniture in every frame.",
        ],
    },
    "ERR_MOTION_BLUR": {
        "title": "Excessive Motion Blur Detected",
        "summary": "Keyframe sharpness analysis detected severe motion blur across multiple frames, degrading feature point detection.",
        "remediation": [
            "Walk more slowly when recording, especially when turning corners or entering new rooms.",
            "Use a handheld gimbal, tripod dolly, or phone stabilizer to minimize camera jitter.",
            "Record at 60 fps with high shutter speed and ample ambient lighting.",
        ],
    },
    "ERR_PURE_ROTATION": {
        "title": "Pure Rotational Camera Motion (Zero Baseline)",
        "summary": "The camera rotated in place without physically translating across space, causing triangulation and depth parallax failure.",
        "remediation": [
            "Translate the camera physically across the space (walk a perimeter loop) rather than standing in the center and panning.",
            "Maintain at least 0.5m of baseline displacement between viewpoint angles.",
            "Re-record by walking the perimeter of the room facing the center.",
        ],
    },
    "ERR_CUDA_OOM": {
        "title": "GPU Memory Exhausted (CUDA Out-of-Memory)",
        "summary": "The reconstruction stage exceeded available GPU VRAM (8 GB budget).",
        "remediation": [
            "Switch quality preset to 'Standard' or 'Draft'.",
            "Downscale input video to 1080p before uploading.",
            "Select 'Route B (Depth Fusion)' under Advanced options for low-memory TSDF meshing.",
            "Click 'Resume Job' to retry with automatic memory reduction.",
        ],
    },
    "ERR_CORRUPT_INPUT": {
        "title": "Corrupted Input Media",
        "summary": "The uploaded video or archive was corrupted, unreadable, or missing valid video streams.",
        "remediation": [
            "Verify that the video file plays smoothly in a local media player (e.g. VLC) before uploading.",
            "Re-export or transcode the video to standard H.264 / AAC MP4 format.",
            "Check that the file size is greater than 1 MB and was not truncated during transfer.",
        ],
    },
    "ERR_GENERIC_FAILURE": {
        "title": "Reconstruction Processing Error",
        "summary": "The reconstruction pipeline encountered an unhandled error during execution.",
        "remediation": [
            "Inspect the execution log drawer below for technical traceback details.",
            "Click 'Resume Job' to retry execution from the last cached stage checkpoint.",
            "If the problem persists, try reprocessing with 'Standard' quality preset.",
        ],
    },
}


def classify_error(error_msg: Optional[str], log_tail: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Analyzes error message and recent log lines to determine structured error code
    and actionable remediation advice.
    """
    combined_text = (error_msg or "") + "\n" + "\n".join(log_tail or [])
    lower_text = combined_text.lower()

    # 1. CUDA OOM
    if (
        "out of memory" in lower_text
        or "cuda oom" in lower_text
        or "cuda out of memory" in lower_text
        or "cublas_status_alloc_failed" in lower_text
        or "torch.cuda.outofmemoryerror" in lower_text
    ):
        code = "ERR_CUDA_OOM"

    # 2. Low SfM registration
    elif (
        "registration threshold" in lower_text
        or "verification threshold" in lower_text
        or "threshold unmet" in lower_text
        or "registered frames" in lower_text
        or bool(re.search(r"registered\s+\d+/\d+", lower_text))
        or "sfm registered" in lower_text
        or "colmap mapper failed" in lower_text
        or "low sfm" in lower_text
        or "could not register enough" in lower_text
        or "registration ratio" in lower_text
    ):
        code = "ERR_LOW_SFM_REGISTRATION"

    # 3. Motion blur
    elif (
        "motion blur" in lower_text
        or "laplacian variance" in lower_text
        or "blurry frames" in lower_text
        or "insufficient sharp frames" in lower_text
    ):
        code = "ERR_MOTION_BLUR"

    # 4. Pure rotation / zero baseline
    elif (
        "pure rotation" in lower_text
        or "zero baseline" in lower_text
        or "degenerate baseline" in lower_text
        or "no parallax" in lower_text
    ):
        code = "ERR_PURE_ROTATION"

    # 5. Corrupt input
    elif (
        "corrupt" in lower_text
        or "invalid data found when processing input" in lower_text
        or "moov atom not found" in lower_text
        or "could not find codec parameters" in lower_text
        or "no video stream" in lower_text
        or "ffmpeg error" in lower_text
    ):
        code = "ERR_CORRUPT_INPUT"

    # 6. Fallback
    else:
        code = "ERR_GENERIC_FAILURE"

    definition = ERROR_DEFINITIONS[code]
    return {
        "code": code,
        "title": definition["title"],
        "summary": definition["summary"],
        "remediation": definition["remediation"],
        "raw_error": error_msg or "Unknown error",
    }
