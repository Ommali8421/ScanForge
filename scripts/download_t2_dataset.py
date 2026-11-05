#!/usr/bin/env python3
"""
Tanks and Temples Dataset Downloader
http://www.tanksandtemples.org

Provides high-speed downloads for intermediate, advanced, and training scenes
from the official Google Cloud Storage mirror with MD5 integrity validation,
unpacking, and data status inspection.
"""

import os
import sys
import argparse
import zipfile
import hashlib
import subprocess
from pathlib import Path

# MD5 Checksums from official Tanks and Temples repository
VIDEO_MD5 = {
    'Auditorium': '0c05722a5a4b1ba9a4bba54e96081b11',
    'Ballroom': '36776c491b2ad975a62714bf920038c0',
    'Barn': '748e814e78aa3ebf797eccd21d0da741',
    'Caterpillar': '33d0a7fdc61fe655c22b11d3fbf1164a',
    'Church': '700f556684bf48f5208103fa2546b1b9',
    'Courthouse': '57ef8aad51a4510a252140062d772b78',
    'Courtroom': 'fc53fe3b181365284cf02bc5194d1907',
    'Family': '107680df05d9887b2ca906423cc9964f',
    'Francis': 'c2ab2b9dda0d0191f64fd27ee59a4117',
    'Horse': 'accafa181892b8217405e9341d3530ca',
    'Ignatius': '990468306128264dd063afac5f915cc4',
    'Lighthouse': '5a97964957bcf876706ee022d9c993b1',
    'M60': '788388f9f49999d9c8a46eadff93dd21',
    'Meetingroom': '5beeb4e21ca5b8fda31235cf15972393',
    'Museum': '080d99de72ee4f142e538b6f21ca6ce7',
    'Palace': '811c1b82264bb7869db275fbfd435637',
    'Panther': '66f426044495cbc4c0f220bb9f28e7c9',
    'Playground': 'f9a41962eae61e5663de11893ec97fb3',
    'Temple': 'f864b96018ef596a7812a938a7cdbc74',
    'Train': '239661e825808a465be09390d04ee18f',
    'Truck': 'ece8864881d81c4250121036b812d43b',
}

IMAGE_MD5 = {
    'Auditorium': '5ef597e1f6b8a6dd30b1314fae0299bf',
    'Ballroom': '75d1656c071583d7890f507b94d93d39',
    'Courtroom': '319a3b684cb4dc2d815774a3f12ef4b4',
    'Ignatius': '3f581feda897a35918ebf85dfd2ac2e6',
    'Meetingroom': '5c282662c161f3083e44be25ef7ef3c4',
}

INTERMEDIATE_LIST = ['Family', 'Francis', 'Horse', 'Lighthouse', 'M60', 'Panther', 'Playground', 'Train']
ADVANCED_LIST = ['Auditorium', 'Ballroom', 'Courtroom', 'Museum', 'Palace', 'Temple']
TRAINING_LIST = ['Barn', 'Caterpillar', 'Church', 'Courthouse', 'Ignatius', 'Meetingroom', 'Truck']

GCS_BASE = "https://storage.googleapis.com/t2-downloads"

def generate_file_md5(filename: str, blocksize: int = 2**20) -> str:
    m = hashlib.md5()
    with open(filename, "rb") as f:
        while True:
            buf = f.read(blocksize)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()

def download_url_curl(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest.with_suffix(dest.suffix + ".part")
    cmd = [
        "curl", "-L", "-C", "-",
        "--connect-timeout", "15",
        "--retry", "3",
        "--retry-delay", "2",
        "-o", str(temp_dest),
        url
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0 and temp_dest.exists():
        temp_dest.rename(dest)
        return True
    return False

def check_file_status(filepath: Path, expected_md5: str | None) -> str:
    if not filepath.exists():
        return " "
    if expected_md5:
        actual = generate_file_md5(str(filepath))
        return "X" if actual == expected_md5 else "?"
    return "X" if filepath.stat().st_size > 1024 * 1024 else "?"

def print_status(sequences: str, modality: str, pathname: str):
    print("\n\n data status: \n\n")
    print("[X] - downloaded    [ ] - missing    [?] - corrupted / mismatch    [n] - not checked")

    base = Path(pathname) if pathname else Path(".")
    groups = []
    if sequences in ('intermediate', 'both', 'all', ''):
        groups.append(('intermediate Dataset', INTERMEDIATE_LIST))
    if sequences in ('advanced', 'both', 'all', ''):
        groups.append(('advanced Dataset', ADVANCED_LIST))
    if sequences in ('training', 'all'):
        groups.append(('training Dataset', TRAINING_LIST))

    for group_name, scene_list in groups:
        print("\n-----------------------------------------------------------------")
        print(f"{group_name:24} {'Video':>12} {'image set':>14}")
        print("-----------------------------------------------------------------")
        for scene in sorted(scene_list):
            vid_path = base / "videos" / f"{scene}.mp4"
            img_path = base / "image_sets" / f"{scene}.zip"

            v_stat = check_file_status(vid_path, VIDEO_MD5.get(scene)) if modality in ('video', 'both', '') else 'n'
            i_stat = check_file_status(img_path, IMAGE_MD5.get(scene)) if modality in ('image', 'both', '') else 'n'
            print(f"{scene:24} {v_stat:>12} {i_stat:>14}")

def main():
    parser = argparse.ArgumentParser(description="Tanks and Temples file downloader")
    parser.add_argument("--modality", type=str, choices=["image", "video", "both"], default="image",
                        help="(image|video|both) choose video sequences or image sets")
    parser.add_argument("--group", type=str, choices=["intermediate", "advanced", "training", "both", "all"], default="both",
                        help="(intermediate|advanced|both|training|all) choose dataset group")
    parser.add_argument("--pathname", type=str, default="", help="destination path name, default = current directory")
    parser.add_argument("-s", action="store_true", default=False, dest="status", help="show data status")
    parser.add_argument("--unpack_off", action="store_false", default=True, dest="unpack", help="do not unzip folders after download")
    parser.add_argument("--calc_md5_off", action="store_false", default=True, dest="calc_md5", help="do not verify md5 checksum")
    parser.add_argument("--scene", type=str, default=None, help="download a specific single scene (e.g. Ballroom, Ignatius)")

    args = parser.parse_args()

    if args.status:
        print_status(args.group, args.modality, args.pathname)
        return

    base_dir = Path(args.pathname) if args.pathname else Path(".")
    
    if args.scene:
        scenes = [args.scene.capitalize()]
    elif args.group == "intermediate":
        scenes = INTERMEDIATE_LIST
    elif args.group == "advanced":
        scenes = ADVANCED_LIST
    elif args.group == "training":
        scenes = TRAINING_LIST
    elif args.group == "both":
        scenes = sorted(INTERMEDIATE_LIST + ADVANCED_LIST)
    elif args.group == "all":
        scenes = sorted(INTERMEDIATE_LIST + ADVANCED_LIST + TRAINING_LIST)
    else:
        scenes = sorted(INTERMEDIATE_LIST + ADVANCED_LIST)

    for scene in scenes:
        if args.modality in ("video", "both"):
            vid_dest = base_dir / "videos" / f"{scene}.mp4"
            url = f"{GCS_BASE}/videos/{scene}.mp4"
            print(f"\n[T2] Downloading video {scene}.mp4 from {url}...")
            if download_url_curl(url, vid_dest):
                if args.calc_md5 and scene in VIDEO_MD5:
                    actual = generate_file_md5(str(vid_dest))
                    if actual == VIDEO_MD5[scene]:
                        print(f"[T2] MD5 verified: {actual}")
                    else:
                        print(f"[T2] WARNING: MD5 mismatch: got {actual}, expected {VIDEO_MD5[scene]}")
            else:
                print(f"[T2] Failed downloading video for {scene}")

        if args.modality in ("image", "both"):
            img_dest = base_dir / "image_sets" / f"{scene}.zip"
            url = f"{GCS_BASE}/image_sets/{scene}.zip"
            print(f"\n[T2] Downloading image set {scene}.zip from {url}...")
            if download_url_curl(url, img_dest):
                if args.calc_md5 and scene in IMAGE_MD5:
                    actual = generate_file_md5(str(img_dest))
                    if actual == IMAGE_MD5[scene]:
                        print(f"[T2] MD5 verified: {actual}")
                    else:
                        print(f"[T2] WARNING: MD5 mismatch: got {actual}, expected {IMAGE_MD5[scene]}")
                if args.unpack and zipfile.is_zipfile(img_dest):
                    extract_dir = base_dir / "image_sets" / scene
                    print(f"[T2] Unpacking {img_dest.name} -> {extract_dir}...")
                    with zipfile.ZipFile(img_dest, "r") as zf:
                        zf.extractall(extract_dir)
            else:
                print(f"[T2] Failed downloading image set for {scene}")

if __name__ == "__main__":
    main()

