"""
E2E Test Fixtures and Helpers
Provides TestClient instances, mock media generators, and pipeline execution helpers.
"""

import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.queue.tasks import run_pipeline_task


@pytest.fixture
def client():
    """Provides a FastAPI TestClient configured for E2E testing."""
    return TestClient(app)


def make_dummy_mp4(size_bytes: int = 1024) -> bytes:
    """Creates a valid MP4 header byte sequence."""
    header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42"
    padding = b"\x00" * max(0, size_bytes - len(header))
    return header + padding


def make_dummy_zip(filenames: list[str] = None) -> bytes:
    """Creates an in-memory zip file with specified filenames."""
    if filenames is None:
        filenames = ["frame_0001.jpg", "frame_0002.jpg"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in filenames:
            zf.writestr(fname, b"dummy content for " + fname.encode("utf-8"))
    return buf.getvalue()


def submit_job(
    client: TestClient,
    scan_type: str = "photo",
    quality: str = "standard",
    output_formats: list[str] | None = None,
    options: dict | None = None,
    filename: str = "room_tour.mp4",
    file_bytes: bytes | None = None,
    content_type: str = "video/mp4",
) -> str:
    """Submits a job via POST /api/jobs and returns the enqueued job_id."""
    if file_bytes is None:
        if filename.endswith(".zip"):
            file_bytes = make_dummy_zip()
            content_type = "application/zip"
        else:
            file_bytes = make_dummy_mp4()
            content_type = "video/mp4"

    files = {"file": (filename, io.BytesIO(file_bytes), content_type)}
    data = {
        "scan_type": scan_type,
        "quality": quality,
        "output_formats": json.dumps(output_formats if output_formats is not None else ["glb", "obj"]),
        "options": json.dumps(options if options is not None else {}),
    }

    res = client.post("/api/jobs", files=files, data=data)
    assert res.status_code == 202, f"Failed submitting job: {res.text}"
    job_id = res.json()["job_id"]
    return job_id


def complete_job_pipeline(job_id: str):
    """Executes the pipeline synchronously for a job using the mock pipeline runner."""
    run_pipeline_task(job_id)
