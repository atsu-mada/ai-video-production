#!/usr/bin/env python3
"""Create a minimal scene-based package without overwriting existing paths."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DIRECTORIES = (
    "00_common/01_style-and-production-rules",
    "00_common/02_characters",
    "00_common/03_environments",
    "00_common/04_objects",
    "00_common/05_prompt-library",
    "01_scenes",
    "99_manifests",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--templates", type=Path, default=Path(__file__).resolve().parents[1] / "assets" / "templates")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target = args.target.resolve()
    if target.exists() and any(target.iterdir()):
        parser.error("target exists and is not empty; refusing to overwrite")
    planned = [target / item for item in DIRECTORIES]
    planned += [target / "00_master-index.md", target / "99_manifests" / "global-asset-manifest.md", target / "99_manifests" / "global-cut-manifest.csv"]
    if args.dry_run:
        for path in planned:
            print(path)
        return 0
    for directory in DIRECTORIES:
        (target / directory).mkdir(parents=True, exist_ok=False)
    shutil.copyfile(args.templates / "master-index.md", target / "00_master-index.md")
    shutil.copyfile(args.templates / "global-asset-manifest.md", target / "99_manifests" / "global-asset-manifest.md")
    shutil.copyfile(args.templates / "cut-manifest.csv", target / "99_manifests" / "global-cut-manifest.csv")
    print(f"OK: initialized {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
