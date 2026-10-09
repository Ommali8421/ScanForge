"""
Tests for safe ZIP extraction utility
"""

import io
import zipfile
import pytest
from pathlib import Path
from app.utils.zip_safe import extract_zip_safely, ZipSecurityError


def test_safe_zip_extraction(tmp_path: Path):
    zip_path = tmp_path / "test.zip"
    dest_dir = tmp_path / "extracted"

    # Create a valid test ZIP
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file1.txt", "Hello World")
        zf.writestr("sub/file2.txt", "Inner text")

    files = extract_zip_safely(zip_path, dest_dir)
    assert len(files) == 2
    assert (dest_dir / "file1.txt").exists()
    assert (dest_dir / "sub" / "file2.txt").exists()
    assert (dest_dir / "file1.txt").read_text() == "Hello World"


def test_zip_slip_traversal_blocked(tmp_path: Path):
    zip_path = tmp_path / "malicious.zip"
    dest_dir = tmp_path / "extracted"

    # Create ZIP with path traversal entry
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../evil.txt", "Malicious content")

    with pytest.raises(ZipSecurityError, match="Path traversal"):
        extract_zip_safely(zip_path, dest_dir)


def test_zip_max_entry_limit(tmp_path: Path):
    zip_path = tmp_path / "bomb.zip"
    dest_dir = tmp_path / "extracted"

    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(15):
            zf.writestr(f"file_{i}.txt", "data")

    with pytest.raises(ZipSecurityError, match="too many files"):
        extract_zip_safely(zip_path, dest_dir, max_entries=10)
