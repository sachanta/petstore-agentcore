#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Zips the repo source directory for upload to CodeBuild's S3 staging bucket.
# Excludes .git, .terraform, tfstate, __pycache__, *.pyc, and tmp/ dirs.
#
# Usage:
#   python3 zip_source.py --source-dir /path/to/repo --output /tmp/source.zip

import argparse
import os
import zipfile

EXCLUDE_PATTERNS = (
    ".git",
    ".terraform",
    "terraform.tfstate",
    "__pycache__",
    ".pyc",
    "/tmp/",
)


def should_exclude(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(pat in norm for pat in EXCLUDE_PATTERNS)


def zip_directory(source_dir: str, output_path: str) -> None:
    source_dir = os.path.abspath(source_dir)
    print(f"Zipping {source_dir} → {output_path}")
    count = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            # Prune excluded dirs in-place so os.walk skips them
            dirs[:] = [
                d for d in dirs
                if not should_exclude(os.path.join(root, d))
            ]
            for fname in files:
                full_path = os.path.join(root, fname)
                if should_exclude(full_path):
                    continue
                arcname = os.path.relpath(full_path, source_dir)
                zf.write(full_path, arcname)
                count += 1
    print(f"Zipped {count} files.")


def main():
    parser = argparse.ArgumentParser(description="Zip repo source for CodeBuild")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output",     required=True)
    args = parser.parse_args()
    zip_directory(args.source_dir, args.output)


if __name__ == "__main__":
    main()
