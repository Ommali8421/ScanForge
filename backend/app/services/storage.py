"""
Storage Service
Manages uploads, job workspaces, generated artifacts, and export zip archives.
"""

import shutil
import zipfile
from pathlib import Path
from typing import BinaryIO, List
from app.config import settings


class StorageService:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.data_path
        self.uploads_dir = self.base_dir / "uploads"
        self.jobs_dir = self.base_dir / "jobs"
        self.artifacts_dir = self.base_dir / "artifacts"

        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def get_job_upload_dir(self, job_id: str) -> Path:
        d = self.uploads_dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_job_workdir(self, job_id: str) -> Path:
        d = self.jobs_dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_job_artifacts_dir(self, job_id: str) -> Path:
        d = self.artifacts_dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_zip_archive(self, job_id: str, archive_name: str = "scanforge_outputs.zip") -> Path:
        """Create a zip file containing all artifact files for a job."""
        art_dir = self.get_job_artifacts_dir(job_id)
        zip_path = art_dir / archive_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in art_dir.glob("*"):
                if item.is_file() and item.name != archive_name:
                    zf.write(item, arcname=item.name)

        return zip_path

    def delete_job_files(self, job_id: str):
        """Remove all files associated with a job."""
        for target in [self.uploads_dir / job_id, self.jobs_dir / job_id, self.artifacts_dir / job_id]:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)


storage_service = StorageService()
