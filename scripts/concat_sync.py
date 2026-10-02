#!/usr/bin/env python3
"""Concatenate video segments without accumulating audio drift.

Stream-copy concatenation (ffmpeg concat demuxer with ``-c copy``) keeps each
segment's AAC audio at whatever length it was encoded with. Audio is usually a
little longer or shorter than the video of the same segment, and the error
accumulates at every join (drift of roughly half a second has been observed
over a multi-segment edit).

This script instead:

1. concatenates the video streams with ``-c copy`` (segments must share codec,
   resolution, frame rate, time base, and pixel format),
2. trims or pads each segment's audio to exactly that segment's video duration
   (a segment without audio contributes silence of the same length),
3. joins the conformed audio with the ``concat`` filter, re-encodes it to AAC,
   and muxes it with the copied video,
4. reports the output's video and audio durations so drift can be checked.

The input is an ffmpeg concat list, one ``file '<path>'`` line per segment.
Relative paths resolve from the list file's directory, as ffmpeg does.

Usage:
    concat_sync.py list.txt out.mp4 [--audio-bitrate 256k] [--sample-rate 48000]
                                    [--overwrite] [--dry-run]

Requirements: Python standard library only, plus ``ffmpeg`` and ``ffprobe`` on
PATH. The script never overwrites an existing output unless ``--overwrite`` is
given; prefer writing a new versioned file instead.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_MATCH_KEYS = ("codec_name", "width", "height", "pix_fmt", "r_frame_rate", "time_base")


def parse_concat_list(list_path: Path) -> list[Path]:
    """Return segment paths from an ffmpeg concat list."""
    base = list_path.resolve().parent
    segments: list[Path] = []
    for number, raw in enumerate(list_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or not line.startswith("file "):
            continue
        value = line[5:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            quote = value[0]
            value = value[1:-1]
            if quote == "'":
                value = value.replace("'\\''", "'")
        if not value:
            raise ValueError(f"line {number}: empty file entry")
        path = Path(value)
        segments.append(path if path.is_absolute() else base / path)
    if not segments:
        raise ValueError(f"no 'file' entries found in {list_path}")
    return segments


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def first_stream(info: dict, kind: str) -> dict | None:
    return next((s for s in info.get("streams", []) if s.get("codec_type") == kind), None)


def video_duration(info: dict, path: Path) -> float:
    stream = first_stream(info, "video")
    if stream is None:
        raise RuntimeError(f"no video stream: {path}")
    for value in (stream.get("duration"), info.get("format", {}).get("duration")):
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration
    raise RuntimeError(f"cannot read video duration: {path}")


def build_command(
    list_path: Path,
    segments: list[Path],
    infos: list[dict],
    output: Path,
    *,
    audio_bitrate: str,
    sample_rate: int,
    overwrite: bool,
) -> tuple[list[str], float]:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y" if overwrite else "-n"]
    command += ["-f", "concat", "-safe", "0", "-i", str(list_path)]
    filters: list[str] = []
    labels: list[str] = []
    total = 0.0
    for index, (segment, info) in enumerate(zip(segments, infos), 1):
        duration = video_duration(info, segment)
        total += duration
        label = f"a{index}"
        if first_stream(info, "audio") is not None:
            command += ["-i", str(segment)]
            source = f"[{index}:a:0]"
            filters.append(
                f"{source}aresample={sample_rate},aformat=channel_layouts=stereo,"
                f"asetpts=PTS-STARTPTS,apad=whole_dur={duration:.6f},"
                f"atrim=0:{duration:.6f},asetpts=PTS-STARTPTS[{label}]"
            )
        else:
            command += ["-f", "lavfi", "-t", f"{duration:.6f}", "-i", f"anullsrc=r={sample_rate}:cl=stereo"]
            filters.append(f"[{index}:a:0]atrim=0:{duration:.6f},asetpts=PTS-STARTPTS[{label}]")
        labels.append(label)
    filters.append("".join(f"[{label}]" for label in labels) + f"concat=n={len(labels)}:v=0:a=1[aout]")
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", audio_bitrate, "-ar", str(sample_rate), "-ac", "2",
        "-movflags", "+faststart",
        str(output),
    ]
    return command, total


def video_mismatches(segments: list[Path], infos: list[dict]) -> list[str]:
    reference = first_stream(infos[0], "video") or {}
    problems: list[str] = []
    for segment, info in zip(segments[1:], infos[1:]):
        stream = first_stream(info, "video") or {}
        for key in VIDEO_MATCH_KEYS:
            if stream.get(key) != reference.get(key):
                problems.append(f"{segment.name}: {key}={stream.get(key)} differs from {segments[0].name} ({reference.get(key)})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("list", type=Path, help="ffmpeg concat list (file '<path>' lines)")
    parser.add_argument("output", type=Path, help="output video path; use a new versioned name")
    parser.add_argument("--audio-bitrate", default="256k", help="AAC bitrate for the rebuilt audio (default: 256k)")
    parser.add_argument("--sample-rate", type=int, default=48000, help="output audio sample rate (default: 48000)")
    parser.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    parser.add_argument("--allow-mismatch", action="store_true", help="continue even if segment video parameters differ")
    parser.add_argument("--dry-run", action="store_true", help="print the ffmpeg command without running it")
    args = parser.parse_args(argv)

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            print(f"ERROR: {tool} not found on PATH", file=sys.stderr)
            return 2
    if args.output.exists() and not args.overwrite and not args.dry_run:
        print(f"ERROR: output exists; choose a new version or pass --overwrite: {args.output}", file=sys.stderr)
        return 2
    try:
        segments = parse_concat_list(args.list)
        missing = [str(path) for path in segments if not path.is_file()]
        if missing:
            raise RuntimeError("missing segment(s): " + ", ".join(missing))
        infos = [probe(path) for path in segments]
        mismatches = video_mismatches(segments, infos)
        if mismatches:
            for line in mismatches:
                print(f"WARNING: {line}", file=sys.stderr)
            if not args.allow_mismatch:
                raise RuntimeError("segment video parameters differ; stream copy would be unsafe (re-encode first or pass --allow-mismatch)")
        command, expected = build_command(
            args.list, segments, infos, args.output,
            audio_bitrate=args.audio_bitrate, sample_rate=args.sample_rate, overwrite=args.overwrite,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(" ".join(command))
        return 0
    result = subprocess.run(command)
    if result.returncode != 0:
        print("ERROR: ffmpeg failed", file=sys.stderr)
        return result.returncode

    info = probe(args.output)
    streams = {s.get("codec_type"): s for s in info.get("streams", [])}
    try:
        v = float(streams["video"]["duration"])
        a = float(streams["audio"]["duration"])
    except (KeyError, TypeError, ValueError):
        print(f"OK: wrote {args.output} ({len(segments)} segments); could not read stream durations for the drift check")
        return 0
    print(f"OK: wrote {args.output} ({len(segments)} segments)")
    print(f"expected video {expected:.3f}s | video {v:.3f}s | audio {a:.3f}s | audio-video {a - v:+.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
