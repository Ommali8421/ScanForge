"""
Safe ZIP Extraction Utility
Guards against path traversal (Zip Slip), decompression bombs, and excessive file counts.
"""

import os
import zipfile
from pathlib import Path
from typing import List


class ZipSecurityError(Exception):
    pass


def extract_zip_safely(
    zip_path: Path,
    target_dir: Path,
    max_entries: int = 10000,
    max_total_size_mb: int = 4096,
    max_single_file_size_mb: int = 1024
) -> List[Path]:
    """
    Safely extract a zip archive to a target directory.
    Guarantees that files cannot escape target_dir and total uncompressed size does not exceed limits.
    """
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted_files: List[Path] = []
    total_uncompressed_bytes = 0
    max_total_bytes = max_total_size_mb * 1024 * 1024
    max_single_file_bytes = max_single_file_size_mb * 1024 * 1024

    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()

        if len(infolist) > max_entries:
            raise ZipSecurityError(f"ZIP archive contains too many files ({len(infolist)} > {max_entries})")

        for member in infolist:
            # Check single file uncompressed size
            if member.file_size > max_single_file_bytes:
                raise ZipSecurityError(f"File {member.filename} exceeds max size limit ({member.file_size} bytes)")

            total_uncompressed_bytes += member.file_size
            if total_uncompressed_bytes > max_total_bytes:
                raise ZipSecurityError(f"Total uncompressed ZIP size exceeds limit of {max_total_size_mb} MB")

            # Check for path traversal (Zip Slip)
            resolved_dest = (target_dir / member.filename).resolve()
            try:
                resolved_dest.relative_to(target_dir)
            except ValueError:
                raise ZipSecurityError(f"Path traversal detected in archive entry: {member.filename}")

            # Do not extract symbolic links or irregular entries
            if member.is_dir():
                resolved_dest.mkdir(parents=True, exist_ok=True)
                continue

            resolved_dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as source, open(resolved_dest, "wb") as dest:
                while chunk := source.read(65536):
                    dest.write(chunk)

            extracted_files.append(resolved_dest)

    return extracted_files
