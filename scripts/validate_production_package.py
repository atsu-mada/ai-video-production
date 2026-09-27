#!/usr/bin/env python3
"""Validate a scene-based AI-video production package without modifying it."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def resolve_required_path(root: Path, relative: str | Path) -> tuple[Path | None, str | None]:
    relative_path = Path(relative)
    try:
        resolved_root = root.resolve(strict=False)
        lexical_candidate = root / relative_path
        if lexical_candidate.is_symlink() and not lexical_candidate.exists():
            return None, f"cannot resolve required path: {relative_path.as_posix()}"
        candidate = lexical_candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return None, f"cannot resolve required path: {relative_path.as_posix()}"
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None, f"required path escapes project root: {relative_path.as_posix()}"
    return candidate, None


def required_path(root: Path, relative: str | Path, expected: str) -> tuple[Path | None, str | None]:
    relative_path = Path(relative)
    candidate, resolution_error = resolve_required_path(root, relative_path)
    if resolution_error:
        return None, resolution_error
    assert candidate is not None
    if not candidate.exists():
        return None, f"missing required path: {relative_path.as_posix()}"
    if expected == "directory" and not candidate.is_dir():
        return None, f"required path is not a directory: {relative_path.as_posix()}"
    if expected == "file" and not candidate.is_file():
        return None, f"required path is not a regular file: {relative_path.as_posix()}"
    return candidate, None


def resolve_manifest_target(root: Path, manifest: Path, raw: str) -> tuple[Path | None, str | None]:
    """Resolve a manifest path using one explicit canonical or legacy form.

    New manifests use paths relative to ``root``.  Existing manifests may use
    ``../`` paths relative to ``99_manifests``; that form is accepted only when
    it stays inside the project.  We never fall back from one interpretation to
    the other after a missing target, and reject a path when both interpretations
    resolve to different existing targets.
    """
    value = raw.strip()
    candidate = Path(value)
    if candidate.is_absolute():
        return None, "absolute path is not allowed"
    try:
        canonical = (root / candidate).resolve(strict=False)
        legacy = (manifest.parent / candidate).resolve(strict=False)
    except (OSError, RuntimeError):
        return None, "cannot resolve manifest path"
    legacy_form = value == ".." or value.startswith("../")
    target = legacy if legacy_form else canonical
    alternate = canonical if legacy_form else legacy

    if not inside(root, target):
        return None, "escapes project root"
    if inside(root, alternate) and target != alternate and target.exists() and alternate.exists():
        return None, "ambiguous manifest path; use one unambiguous relative form"
    return target, None


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    required_layout = (
        ("00_master-index.md", "file"),
        ("99_manifests/global-asset-manifest.md", "file"),
        ("99_manifests/global-cut-manifest.csv", "file"),
        ("00_common", "directory"),
        ("01_scenes", "directory"),
        ("99_manifests", "directory"),
    )
    resolved_layout: dict[str, Path] = {}
    for relative, expected in required_layout:
        target, path_error = required_path(root, relative, expected)
        if path_error:
            errors.append(path_error)
        elif target is not None:
            resolved_layout[relative] = target

    manifest = resolved_layout.get("99_manifests/global-cut-manifest.csv")
    if manifest is None:
        return errors
    try:
        with manifest.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append(f"cannot read global cut manifest: {exc}")
        return errors
    required = {"cut_id", "start_sec", "end_sec", "duration_sec"}
    if not rows:
        errors.append("global cut manifest has no rows")
        return errors
    if not required.issubset(rows[0]):
        errors.append(f"global cut manifest missing columns: {sorted(required - set(rows[0]))}")
        return errors
    scene_field = "scene_id" if "scene_id" in rows[0] else "scene" if "scene" in rows[0] else None
    if scene_field is None:
        errors.append("global cut manifest missing scene_id or scene column")

    scene_root = resolved_layout.get("01_scenes")
    validated_scene_ids: dict[str, list[str]] = {}
    if scene_root is not None:
        for scene_entry in sorted(scene_root.glob("SC*")):
            scene_relative = Path("01_scenes") / scene_entry.name
            scene, scene_error = required_path(root, scene_relative, "directory")
            scene_valid = scene_error is None and scene is not None
            if scene_error:
                errors.append(f"{scene_entry.name}: {scene_error}")
            if scene is not None:
                required_scene_paths = (
                    ("00_scene-overview.md", "file"),
                    ("01_used-common-assets.md", "file"),
                    ("03_storyboard", "directory"),
                    ("04_text-storyboard", "directory"),
                    ("05_cut-prompts", "directory"),
                    ("06_scene-cut-manifest.csv", "file"),
                )
                for relative, expected in required_scene_paths:
                    _, path_error = required_path(root, scene_relative / relative, expected)
                    if path_error:
                        scene_valid = False
                        if path_error.startswith("missing required path: "):
                            errors.append(f"{scene_entry.name}: missing {relative}")
                        else:
                            errors.append(f"{scene_entry.name}: {path_error}")
            if scene_valid:
                scene_identifier = scene_entry.name.split("_", 1)[0]
                validated_scene_ids.setdefault(scene_identifier, []).append(scene_entry.name)
        for scene_identifier, scene_names in sorted(validated_scene_ids.items()):
            if len(scene_names) > 1:
                errors.append(
                    f"duplicate scene directory identifier {scene_identifier}: {', '.join(scene_names)}"
                )

    seen: set[str] = set()
    previous_end: float | None = None
    for number, row in enumerate(rows, start=2):
        cut_id = (row.get("cut_id") or "").strip()
        if not cut_id or cut_id in seen:
            errors.append(f"row {number}: empty or duplicate cut_id {cut_id!r}")
        seen.add(cut_id)
        scene_value = (row.get(scene_field) or "").strip() if scene_field is not None else ""
        if scene_field is not None and not scene_value:
            errors.append(f"row {number}: {scene_field} must be nonempty")
        elif scene_field is not None and scene_root is not None:
            matches = validated_scene_ids.get(scene_value, [])
            if not matches:
                errors.append(f"row {number}: {scene_field} does not match a validated scene directory: {scene_value}")
            elif len(matches) != 1:
                errors.append(f"row {number}: {scene_field} matches multiple scene directories: {scene_value}")
        try:
            start = float(row["start_sec"])
            end = float(row["end_sec"])
            duration = float(row["duration_sec"])
        except (TypeError, ValueError):
            errors.append(f"row {number}: invalid numeric timing")
            continue
        if not all(math.isfinite(value) for value in (start, end, duration)):
            errors.append(f"row {number}: invalid numeric timing")
            continue
        if start < 0:
            errors.append(f"row {number}: start_sec must be nonnegative")
        if end < 0:
            errors.append(f"row {number}: end_sec must be nonnegative")
        if duration <= 0:
            errors.append(f"row {number}: duration_sec must be greater than zero")
        if end <= start:
            errors.append(f"row {number}: end_sec must exceed start_sec")
        if not math.isclose(duration, end - start, abs_tol=1e-6):
            errors.append(f"row {number}: duration_sec does not match end-start")
        if previous_end is not None and start < previous_end:
            errors.append(f"row {number}: cut overlaps previous cut")
        previous_end = end
        for field in ("video_prompt", "prompt_path", "storyboard", "storyboard_path", "text_storyboard", "text_storyboard_path", "output_path"):
            raw = (row.get(field) or "").strip()
            if not raw:
                continue
            target, resolution_error = resolve_manifest_target(root, manifest, raw)
            if resolution_error:
                errors.append(f"row {number}: {field} {resolution_error}")
            elif target is not None:
                if not target.exists():
                    errors.append(f"row {number}: missing {field} target {raw}")
                elif not target.is_file():
                    errors.append(f"row {number}: {field} target must be a regular file: {raw}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    if not root.is_dir():
        parser.error("project_root must be a directory")
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: production package structure and cut timing are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
