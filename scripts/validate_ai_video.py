#!/usr/bin/env python3
"""Validate the generic AI-video production deliverables."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import math
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import unquote, urlsplit


SKILL_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = SKILL_ROOT / "references" / "profiles" / "generation-profiles.json"
PANEL_RE = re.compile(r"(?ms)^[ \t]*Panel\s+(\d+):[ \t]*(.*?)(?=^[ \t]*Panel\s+\d+:[ \t]*|\Z)")
PANEL_HEADING_LINE_RE = re.compile(r"(?im)^[ \t]*Panel\b[^\r\n]*$")
CANONICAL_PANEL_HEADING_RE = re.compile(r"^[ \t]*Panel\s+\d+:[ \t]*$")
TEXT_STORYBOARD_FORBIDDEN_FIELD_RE = re.compile(
    r"(?im)^[ \t]*(?P<label>dialogue|narration|sound|audio|台詞|セリフ|ナレーション|音声|効果音)[ \t]*(?P<colon>[:：])"
)
TIME_RE = re.compile(r"(\d+):([0-5]\d)\s*[–—-]\s*(\d+):([0-5]\d)")
RANGE_ENDPOINT = r"(?:\d+(?:\.\d+)?|\d+:[0-5]\d)"
RANGE_RE = re.compile(rf"^\s*({RANGE_ENDPOINT})\s*[–—-]\s*({RANGE_ENDPOINT})\s*$")
LINK_RE = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")
REFERENCE_HEADING_RE = re.compile(r"(?im)^\s*#{2,6}\s+References\s*$")
EXTERNAL_URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>)]+")
RAW_PATH_RE = re.compile(
    r"(?ix)"
    r"(?:\bfile:(?:/{1,2})|(?<![\w])(?:~|\.{1,2})/|(?<![\w])/(?:[^\s<>)]+)|"
    r"(?<![\w.-])[\w.-]+/(?:[^\s<>)]+)|"
    r"(?<![\w.-])[\w.-]+\.(?:md|markdown|png|jpe?g|webp|csv|json|txt|html)\b)"
)
PREPARATION_ONLY_SUBMISSION = "prepare only; submit only after a separate explicit generation request."
TOPOLOGY_RE = re.compile(r"(?im)^\s*(?:VFX\s+)?TOPOLOGY:\s*(.*?)\s*$")
HTML_RESOURCE_TAGS = {
    "audio": ("src",),
    "embed": ("src",),
    "iframe": ("src",),
    "img": ("src",),
    "object": ("data",),
    "source": ("src",),
    "track": ("src",),
    "video": ("poster", "src"),
}
KNOWLEDGE_MAP_FIELDS = {
    "id",
    "path",
    "anchor",
    "legacy_sections",
    "source_refs",
    "status",
}
CANONICAL_KNOWLEDGE_PATHS = {
    "references/index.html",
    "references/core/continuity.html",
    "references/core/production-order.html",
    "references/core/validation.html",
    "references/deliverables/character-sheet.html",
    "references/deliverables/cut-prompt.html",
    "references/deliverables/environment-sheet.html",
    "references/deliverables/generation-handoff.html",
    "references/deliverables/object-sheet.html",
    "references/deliverables/production-package.html",
    "references/deliverables/scene-prompt.html",
    "references/deliverables/storyboard.html",
    "references/deliverables/text-storyboard.html",
    "references/deliverables/vfx-sheet.html",
    "references/manifest-contracts.html",
    "references/package-layout.html",
    "references/validation.html",
}
KNOWLEDGE_CONTENT_MARKERS = {
    "references/core/continuity.html": ("object state", "storyboard blocking"),
    "references/core/production-order.html": ("00_common", "07_generation-handoffs"),
    "references/core/validation.html": ("camera start", "Prompt and handoff validation"),
    "references/deliverables/character-sheet.html": ("neck-down", "three-quarter"),
    "references/deliverables/cut-prompt.html": ("positive duration", "motivated camera path"),
    "references/deliverables/environment-sheet.html": ("top-down map", "camera start"),
    "references/deliverables/generation-handoff.html": ("upload order", "boundary frame"),
    "references/deliverables/object-sheet.html": ("scene-state reference", "keyboard layouts"),
    "references/deliverables/production-package.html": ("asset manifest", "cut manifest"),
    "references/deliverables/scene-prompt.html": ("multi-cut scene", "job split"),
    "references/deliverables/storyboard.html": ("pure white", "motion trails"),
    "references/deliverables/text-storyboard.html": ("映像：", "画角：", "カメラ："),
    "references/deliverables/vfx-sheet.html": ("VFX TOPOLOGY", "uniform black background"),
    "references/manifest-contracts.html": ("cut_id", "Asset manifest"),
    "references/package-layout.html": ("canonical package layout", "production-order.html"),
    "references/validation.html": ("canonical validation rules", "body is maintained"),
}
HANDOFF_FIELDS = (
    "Provider profile:",
    "Model:",
    "Execution skill:",
    "Input references:",
    "Duration:",
    "Prompt artifact:",
    "Output contract:",
    "Validation commands:",
    "Approval state:",
    "Submission:",
)


def png_ratio(path: Path) -> float:
    raw = path.read_bytes()[:24]
    if len(raw) != 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("image must be a PNG")
    width, height = struct.unpack(">II", raw[16:24])
    if not height:
        raise ValueError("image height must be non-zero")
    return width / height


def confident_text(path: Path) -> list[str]:
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract is required when validating an image")
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "jpn+eng", "--psm", "6", "tsv"],
        text=True,
        capture_output=True,
        check=True,
    )
    hits: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        columns = line.split("\t")
        if len(columns) < 12:
            continue
        try:
            confidence = float(columns[10])
        except ValueError:
            continue
        token = "".join(re.findall(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff]", columns[11]))
        if confidence >= 70 and len(token) >= 2:
            hits.append(token)
    return hits


def image_errors(image: Path | None, *, require_text: bool = False, forbid_text: bool = False) -> list[str]:
    if image is None:
        return []
    errors: list[str] = []
    try:
        if abs(png_ratio(image) - 1.5) > 0.03:
            errors.append("image aspect ratio is not 3:2")
        hits = confident_text(image)
        if require_text and not hits:
            errors.append("image does not contain confident explanatory text")
        if forbid_text and hits:
            errors.append(f"confident multi-character OCR detected: {hits}")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(str(exc))
    return errors


def read_prompt(path: Path) -> tuple[str, list[str]]:
    try:
        return path.read_text(encoding="utf-8"), []
    except (OSError, UnicodeError) as exc:
        return "", [f"cannot read prompt: {exc}"]


def required_terms(text: str, terms: Iterable[str]) -> list[str]:
    lowered = text.casefold()
    return [f"missing prompt requirement: {term}" for term in terms if term.casefold() not in lowered]


_PERMISSION_WORDS = r"(?:allowed|permitted|included|present|shown|visible|waived)"


def _has_term_prohibition(text: str, term: str) -> bool:
    escaped = re.escape(term)
    patterns = (
        rf"\bno\b[^.\n;]*\b{escaped}\b",
        rf"\b(?:without|excluding|exclude|prohibit(?:ed)?|forbid(?:den)?|avoid|omit|remove|never|do\s+not|must\s+not|don't)\b[^.\n;]*\b{escaped}\b",
        rf"\b{escaped}\b[^.\n;]*\b(?:is|are)\s+(?:not\s+allowed|not\s+permitted|prohibited|forbidden|excluded|absent)\b",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _has_term_permission(text: str, term: str) -> bool:
    escaped = re.escape(term)
    patterns = (
        re.compile(rf"\b{escaped}\b\s+(?:(?:is|are)\s+)?{_PERMISSION_WORDS}\b", re.IGNORECASE),
        re.compile(rf"\b{escaped}\b[^.\n;]{{0,60}}?\b(?:may|can|will|should)\s+be\s+{_PERMISSION_WORDS}\b", re.IGNORECASE),
        re.compile(rf"\b{escaped}\b[^.\n;]{{0,60}}?\b(?:is|are)\s+(?!not\s+){_PERMISSION_WORDS}\b", re.IGNORECASE),
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            prefix_start = max(
                text.rfind("\n", 0, match.start()),
                text.rfind(".", 0, match.start()),
                text.rfind(";", 0, match.start()),
            )
            prefix = text[prefix_start + 1 : match.start()].strip()
            no_match = list(re.finditer(r"\bno\b", prefix, re.IGNORECASE))
            no_suffix = prefix[no_match[-1].end() :] if no_match else ""
            if no_match and not re.search(r"\b(?:but|however|except|although)\b", no_suffix, re.IGNORECASE):
                continue
            return True
    return False


def prohibition_errors(text: str, terms: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for term in terms:
        if not _has_term_prohibition(text, term):
            errors.append(f"missing prompt prohibition: {term}")
        if _has_term_permission(text, term):
            errors.append(f"prompt permits forbidden element: {term}")
    return errors


def selected_image(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "image_option", None) or getattr(args, "image", None)
    return Path(raw) if raw else None


def validate_character(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    errors += required_terms(
        text,
        ("3:2", "#808080", "LEFT ZONE", "CENTER ZONE", "RIGHT ZONE", "neck-down", "three-quarter", "only visible face"),
    )
    lowered = text.casefold()
    if not any(phrase.casefold() in lowered for phrase in ("no extra face", "no front face", "no additional face")):
        errors.append("prompt does not prohibit additional face views")
    if "remove the entire head" not in lowered and "remove the head" not in lowered:
        errors.append("front/back body views do not explicitly remove the head")
    errors += prohibition_errors(text, ("text", "logo", "watermark"))
    return errors + image_errors(selected_image(args), forbid_text=True)


def validate_environment(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    errors += required_terms(
        text,
        ("3:2", "same", "TYPE / SETTING", "CRAFT & MATERIAL SIGNATURE", "PALETTE", "KEY LANDMARKS", "ATMOSPHERE", "establishing", "material", "lighting", "top-down"),
    )
    errors += prohibition_errors(text, ("people",))
    return errors + image_errors(selected_image(args), require_text=True)


def validate_object(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    errors += required_terms(text, ("3:2", "one", "three", "supplementary", "detail", "exact same"))
    errors += prohibition_errors(text, ("people", "hands", "text", "logo", "watermark"))
    return errors + image_errors(selected_image(args), forbid_text=True)


def validate_vfx(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    errors += required_terms(text, ("3:2", "VFX", "black", "effect", "source", "geometry", "optical", "STATES"))
    errors += prohibition_errors(text, ("people", "text", "logo", "watermark"))
    if not re.search(r"\b(?:uniform|perfectly\s+uniform)\s+black\s+background\b", text, re.IGNORECASE):
        errors.append("VFX sheet must specify a uniform black background")
    if re.search(r"(?:white|gray|grey)\s+background", text, re.IGNORECASE):
        errors.append("VFX sheet must specify a black background")
    topology_matches = TOPOLOGY_RE.findall(text)
    if len(topology_matches) != 1:
        errors.append("VFX TOPOLOGY field must appear exactly once")
    else:
        topology = topology_matches[0].strip()
        if not topology or re.search(r"<[^>\n]+>", topology):
            errors.append("VFX TOPOLOGY must be resolved to one effect or compatible effect family")
        elif (
            re.search(r"\b(?:two|multiple|separate|unrelated|another)\b", topology, re.IGNORECASE)
            or re.search(r"[;,/&|]", topology)
            or (
                re.search(r"\b(?:and|or|plus|with)\b", topology, re.IGNORECASE)
                and not re.search(r"\b(?:compatible|family)\b", topology, re.IGNORECASE)
            )
        ):
            errors.append("VFX TOPOLOGY must name one effect or compatible effect family")
    if re.search(r"\b(?:two|multiple|separate|unrelated)\s+(?:VFX\s+)?(?:effects?|topolog(?:y|ies))\b", text, re.IGNORECASE):
        errors.append("VFX sheet must contain one effect topology")
    if re.search(r"\bone\s+[^.\n]{0,60}\beffect\b[^.\n]{0,60}\band\s+one\s+[^.\n]{0,60}\beffect\b", text, re.IGNORECASE):
        errors.append("VFX sheet must contain one effect topology")
    effect_blocks = re.findall(r"(?im)^\s*(?:VFX\s+)?EFFECT\s+(?:[A-Z]|\d+)\s*:", text)
    if len(effect_blocks) > 1:
        errors.append("VFX sheet must contain one effect topology")
    return errors + image_errors(selected_image(args), forbid_text=True)


def validate_storyboard(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    errors += required_terms(text, ("3:2", "image-only", "white", "black", "monoline", "one principal action", "gutters", "No", "text", "digits", "shading", "color"))
    negative_words = r"(?:no|without|excluding|exclude|prohibit(?:ed)?|forbid(?:den)?|avoid|omit|remove|never|do\s+not|must\s+not|don't)"
    for term in ("text", "digits", "shading", "color"):
        negative = (
            rf"{negative_words}[^.\n]{{0,120}}\b{term}\b",
            rf"\b{term}\b[^.\n]{{0,80}}\b(?:is|are)\s+(?:not\s+allowed|not\s+permitted|prohibited|forbidden|excluded|absent)\b",
        )
        if not any(re.search(pattern, text, re.IGNORECASE) for pattern in negative):
            errors.append(f"image-only storyboard must explicitly prohibit {term}")
        affirmative = (
            rf"\b{term}\b[^.\n]{{0,80}}\b(?:is|are|may\s+be|can\s+be)\s+(?:allowed|permitted|included|present|visible)\b",
            rf"(?<!do not )(?<!must not )(?<!never )(?<!don't )(?<!not )\b(?:allow|include|permit|show|add)\b[^.\n]{{0,80}}\b{term}\b",
        )
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in affirmative):
            errors.append(f"image-only storyboard permits forbidden element: {term}")
    arrow = r"(?:camera\s+or\s+motion\s+|camera\s+|motion\s+)?arrows?"
    arrow_negative = (
        rf"{negative_words}[^.\n]{{0,120}}{arrow}[^.\n]{{0,80}}(?:inside|within)\s+(?:the\s+)?picture\s+panels?",
        rf"{arrow}[^.\n]{{0,80}}(?:inside|within)\s+(?:the\s+)?picture\s+panels?[^.\n]{{0,60}}(?:not\s+allowed|not\s+permitted|prohibited|forbidden|excluded)",
    )
    if not any(re.search(pattern, text, re.IGNORECASE) for pattern in arrow_negative):
        errors.append("image-only storyboard must prohibit arrows inside picture panels")
    arrow_affirmative = (
        rf"{arrow}[^.\n]{{0,80}}(?:inside|within)\s+(?:the\s+)?picture\s+panels?[^.\n]{{0,60}}(?:allowed|permitted|included|present|visible)",
        rf"(?<!never )(?<!do not )(?<!must not )(?<!don't )\b(?:place|put|draw|include|allow|show)\b[^.\n]{{0,80}}{arrow}[^.\n]{{0,80}}(?:inside|within)\s+(?:the\s+)?picture\s+panels?",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in arrow_affirmative):
        errors.append("image-only storyboard permits arrows inside picture panels")
    forbidden = (
        r"\bCUT\s+\d+\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\b(?:lens|camera\s+name)\b",
    )
    for pattern in forbidden:
        if re.search(pattern, text, re.IGNORECASE):
            errors.append(f"image-only storyboard contains forbidden production instruction: {pattern}")
    return errors + image_errors(selected_image(args), forbid_text=True)


def _seconds(minutes: str, seconds: str) -> int:
    value = int(seconds)
    if value >= 60:
        raise ValueError("seconds component must be below 60")
    return int(minutes) * 60 + value


def _normalize_text_storyboard_inline_code(text: str) -> tuple[str, list[str]]:
    """Remove one balanced line-level Markdown code wrapper without moving text."""
    normalized: list[str] = []
    errors: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        newline = raw_line[len(line) :]
        stripped = line.strip(" \t")
        if "`" not in stripped:
            normalized.append(raw_line)
            continue
        if stripped.startswith("`") and stripped.endswith("`") and stripped.count("`") == 2:
            start = line.index(stripped)
            end = start + len(stripped)
            inner = stripped[1:-1]
            normalized.append(line[:start] + " " + inner + " " + line[end:] + newline)
            continue
        instruction_candidate = stripped.lstrip("`").lstrip()
        if re.match(
            r"(?:CUT\s+\d+|\d+:[0-5]\d|映像：|画角：|カメラ：|(?:dialogue|narration|sound|audio|台詞|セリフ|ナレーション|音声|効果音)[ \t]*[:：])",
            instruction_candidate,
            re.IGNORECASE,
        ):
            errors.append("unbalanced Markdown inline-code wrapper")
        normalized.append(raw_line)
    return "".join(normalized), errors


def validate_text_storyboard(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    normalized_text, inline_code_errors = _normalize_text_storyboard_inline_code(text)
    errors += inline_code_errors
    panel_matches = list(PANEL_RE.finditer(normalized_text))
    panels = [(match.group(1), match.group(2)) for match in panel_matches]

    canonical_heading_count = 0
    for heading_match in PANEL_HEADING_LINE_RE.finditer(normalized_text):
        heading = heading_match.group(0).strip()
        if CANONICAL_PANEL_HEADING_RE.fullmatch(heading):
            canonical_heading_count += 1
        else:
            errors.append(f"malformed Panel heading: {heading}")
    if not panels:
        errors.append("no Panel N blocks found")
    if canonical_heading_count != len(panels):
        errors.append("Panel heading count does not match parsed panel count")

    for forbidden_match in TEXT_STORYBOARD_FORBIDDEN_FIELD_RE.finditer(normalized_text):
        panel_number = next(
            (
                panel_match.group(1)
                for panel_match in panel_matches
                if panel_match.start() <= forbidden_match.start() < panel_match.end()
            ),
            None,
        )
        prefix = f"Panel {panel_number}: " if panel_number is not None else ""
        field = f"{forbidden_match.group('label')}{forbidden_match.group('colon')}"
        errors.append(f"{prefix}extra field {field}")

    seen_cuts: set[str] = set()
    seen_panels: set[int] = set()
    previous_end: int | None = None
    for expected_panel, (panel_number, body) in enumerate(panels, start=1):
        panel_index = int(panel_number)
        if panel_index in seen_panels:
            errors.append(f"Panel {panel_number}: duplicate panel number")
        if panel_index != expected_panel:
            errors.append(f"Panel {panel_number}: panel numbers must be sequential")
        seen_panels.add(panel_index)
        if len(re.findall(r"CUT\s+\d+", body)) != 1:
            errors.append(f"Panel {panel_number}: CUT number must appear exactly once")
        for label in ("映像：", "画角：", "カメラ："):
            label_matches = list(re.finditer(rf"(?m)^\s*{re.escape(label)}(.*?)\s*$", body))
            if body.count(label) != 1 or len(label_matches) != 1:
                errors.append(f"Panel {panel_number}: {label} must appear exactly once")
            elif not label_matches[0].group(1).strip():
                errors.append(f"Panel {panel_number}: {label} must have a nonempty value")
            elif re.search(r"<[^>\n]+>", label_matches[0].group(1)):
                errors.append(f"Panel {panel_number}: unresolved placeholder in {label}")
        cut = re.search(r"CUT\s+(\d+)", body)
        if cut:
            if cut.group(1) in seen_cuts:
                errors.append(f"Panel {panel_number}: duplicate CUT {cut.group(1)}")
            seen_cuts.add(cut.group(1))
        timings = TIME_RE.findall(body)
        if not timings:
            errors.append(f"Panel {panel_number}: missing start-end timecode")
            continue
        if len(timings) != 1:
            errors.append(f"Panel {panel_number}: timecode must appear exactly once")
        timing = TIME_RE.search(body)
        if timing is None:
            continue
        try:
            start = _seconds(timing.group(1), timing.group(2))
            end = _seconds(timing.group(3), timing.group(4))
        except ValueError as exc:
            errors.append(f"Panel {panel_number}: {exc}")
            continue
        if end <= start:
            errors.append(f"Panel {panel_number}: end time must exceed start time")
        if previous_end is not None and start < previous_end:
            errors.append(f"Panel {panel_number}: overlaps previous panel")
        previous_end = end
    return errors


def _parse_duration_field(text: str) -> tuple[float | None, str | None]:
    matches = re.findall(r"(?im)^\s*Duration:\s*(.*?)\s*$", text)
    if len(matches) != 1:
        return None, "Duration: must be a numeric positive value"
    match = re.fullmatch(
        r"([+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?))(?:\s+seconds?)?",
        matches[0].strip(),
        re.IGNORECASE,
    )
    if not match:
        return None, "Duration: must be a numeric positive value"
    try:
        duration = float(match.group(1))
    except (OverflowError, ValueError):
        return None, "Duration: must be a numeric positive value"
    if not math.isfinite(duration):
        return None, "Duration: must be a numeric positive value"
    if duration <= 0:
        return None, "Duration: must be greater than zero"
    return duration, None


def duration_seconds(text: str) -> float | None:
    duration, error = _parse_duration_field(text)
    return duration if error is None else None


def profile_limit(name: str | None) -> tuple[float | None, str | None]:
    if not name:
        return None, None
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        profile = payload["profiles"][name]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return None, f"unknown generation profile: {name}"
    value = profile.get("max_duration_sec")
    return (float(value) if value is not None else None), None


def duration_profile_errors(text: str, profile: str | None, *, duration: float | None = None) -> list[str]:
    errors: list[str] = []
    limit, profile_error = profile_limit(profile)
    if profile_error:
        errors.append(profile_error)
    if limit is not None and duration is not None and duration > limit:
        errors.append(f"duration {duration:g}s exceeds {profile} profile limit {limit:g}s")
    return errors


def _reference_section_entries(text: str) -> list[str] | None:
    matches = list(REFERENCE_HEADING_RE.finditer(text))
    if len(matches) != 1:
        return None
    start = matches[0].end()
    entries: list[str] = []
    in_fence = False
    for raw_line in text[start:].splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            entries.append(line)
            in_fence = not in_fence
            continue
        if not in_fence and re.match(r"^#{1,6}\s+\S", line):
            break
        entries.append(line)
    return entries


def _reference_field_entries(text: str) -> list[str] | None:
    match = re.search(r"(?im)^\s*References:\s*(.*?)\s*$", text)
    if not match:
        return None
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _declared_reference_entries(text: str, kind: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    entries: list[str] = []
    if kind == "handoff":
        for field in ("Input references:", "Prompt artifact:"):
            matches = _handoff_field_matches(text, field)
            if len(matches) != 1:
                continue
            value = _handoff_field_value(text, field, matches[0])
            entries.extend(line.strip() for line in value.splitlines() if line.strip())
        return entries, errors

    section_entries = _reference_section_entries(text)
    if section_entries is None:
        section_entries = _reference_field_entries(text)
    start_matches = list(re.finditer(r"(?im)^\s*Start image:\s*(.*?)\s*$", text))
    if section_entries is None and not (kind == "cut-image-to-video" and len(start_matches) == 1):
        errors.append("missing References section")
    else:
        entries.extend(section_entries or [])

    if kind == "cut-image-to-video":
        if len(start_matches) == 1:
            entries.append(start_matches[0].group(1).strip())
    return entries, errors


def _reference_target_errors(raw: str, prompt: Path, root: Path) -> tuple[int, list[str]]:
    if raw.startswith("#"):
        return 0, []
    if re.match(r"(?i)^file:(?://)?", raw):
        return 0, [f"file URL reference is not allowed: {raw}"]
    if re.match(r"(?i)^https?://", raw):
        return 0, []
    local_raw = raw.split("#", 1)[0]
    if not local_raw:
        return 0, []
    if Path(local_raw).is_absolute():
        return 0, [f"absolute reference is not allowed: {raw}"]
    try:
        lexical_target = prompt.parent / local_raw
        if lexical_target.is_symlink() and not lexical_target.exists():
            return 1, [f"cannot resolve reference target: {raw}"]
        target = lexical_target.resolve()
    except (OSError, RuntimeError):
        return 1, [f"cannot resolve reference target: {raw}"]
    try:
        target.relative_to(root)
    except ValueError:
        return 0, [f"reference escapes project root: {raw}"]
    if not target.exists():
        return 1, [f"missing reference target: {raw}"]
    return 1, []


def reference_path_errors(prompt: Path, project_root: Path | None, *, kind: str = "cut-video") -> list[str]:
    if project_root is None:
        return ["--project-root is required when --check-paths is used"]
    try:
        root_path = project_root.expanduser()
        if root_path.is_symlink() and not root_path.exists():
            return [f"cannot resolve project root: {project_root}"]
        root = root_path.resolve()
    except (OSError, RuntimeError):
        return [f"cannot resolve project root: {project_root}"]
    if not root.is_dir():
        return [f"project root must be an existing directory: {project_root}"]
    try:
        prompt_path = prompt.expanduser()
        if prompt_path.is_symlink() and not prompt_path.exists():
            return [f"cannot resolve prompt path: {prompt}"]
        prompt_resolved = prompt_path.resolve()
    except (OSError, RuntimeError):
        return [f"cannot resolve prompt path: {prompt}"]
    try:
        prompt_resolved.relative_to(root)
    except ValueError:
        return [f"prompt is outside project root: {prompt}"]
    text, errors = read_prompt(prompt)
    if errors:
        return errors
    entries, entry_errors = _declared_reference_entries(text, kind)
    errors += entry_errors
    local_count = 0
    if not entries:
        errors.append("no parsed local references")
    section_entries = _reference_section_entries(text)
    start_image_values = {
        match.group(1).strip()
        for match in re.finditer(r"(?im)^\s*Start image:\s*(.*?)\s*$", text)
    }
    for entry in entries:
        canonical_list_entry = bool(re.match(r"^[-*+]\s+", entry))
        section_entry = section_entries is not None and entry not in start_image_values
        if section_entry and kind != "handoff" and not canonical_list_entry:
            errors.append(f"unparsed local reference entry; use a Markdown link: {entry}")
        value = re.sub(r"^\s*[-*+]\s*", "", entry).strip()
        if not value:
            continue
        links = list(MARKDOWN_LINK_RE.finditer(value))
        if not links:
            if EXTERNAL_URL_RE.search(value) and not RAW_PATH_RE.search(EXTERNAL_URL_RE.sub("", value)):
                continue
            raw_reference = value.rstrip(".,;")
            if (
                raw_reference == raw_reference.split()[0]
                and RAW_PATH_RE.search(raw_reference)
                and not re.match(r"(?i)^https?://", raw_reference)
            ):
                count, target_errors = _reference_target_errors(raw_reference, prompt, root)
                local_count += count
                errors += target_errors
            if not section_entry or canonical_list_entry or kind == "handoff":
                errors.append(f"unparsed local reference entry; use a Markdown link: {entry}")
            continue
        residual = MARKDOWN_LINK_RE.sub("", value)
        residual = EXTERNAL_URL_RE.sub("", residual)
        if RAW_PATH_RE.search(residual):
            errors.append(f"unparsed local reference entry; use a Markdown link: {entry}")
        for link in links:
            count, target_errors = _reference_target_errors(link.group(1).strip(), prompt, root)
            local_count += count
            errors += target_errors
    if local_count == 0:
        errors.append("no parsed local references")
    return errors


def _prompt_has_references(text: str, *, allow_start_image: bool = False) -> bool:
    return bool(
        _reference_section_entries(text) is not None
        or _reference_field_entries(text) is not None
        or (allow_start_image and re.search(r"(?im)^\s*Start image:\s*", text))
    )


def _anchored_field_matches(text: str, field: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"(?m)^[ \t]*{re.escape(field)}[ \t]*([^\r\n]*)[ \t]*$", text))


def _required_line_field_errors(text: str, fields: Iterable[str]) -> list[str]:
    errors: list[str] = []
    for field in fields:
        matches = _anchored_field_matches(text, field)
        if not matches:
            errors.append(f"missing required field: {field}")
            continue
        if len(matches) != 1:
            errors.append(f"required field must appear exactly once: {field}")
            continue
        value = matches[0].group(1).strip()
        if not value:
            errors.append(f"required field is empty: {field}")
        elif re.search(r"<[^>\n]+>", value):
            errors.append(f"placeholder remains in {field}")
    return errors


def _cut_identifier_errors(text: str) -> list[str]:
    references_heading = REFERENCE_HEADING_RE.search(text)
    header_text = text[: references_heading.start()] if references_heading else text
    heading_matches = list(re.finditer(r"(?im)^\s*#{1,6}\s+(CUT[_ -]?\d+)\b", header_text))
    field_matches = list(re.finditer(r"(?im)^[ \t]*(?:CUT|Cut) ID:[ \t]*([^\r\n]*)[ \t]*$", header_text))
    identifiers = [match.group(1) for match in heading_matches]
    for match in field_matches:
        value = match.group(1).strip()
        if re.fullmatch(r"CUT[_ -]?\d+", value, re.IGNORECASE):
            identifiers.append(value)
    if len(identifiers) != 1:
        return ["missing stable CUT identifier"] if not identifiers else ["stable CUT identifier must appear exactly once"]
    return []


def _reference_placeholder_errors(text: str, kind: str) -> list[str]:
    entries, _ = _declared_reference_entries(text, kind)
    if any(re.search(r"<[^>\n]+>", entry) for entry in entries):
        return ["placeholder remains in references"]
    return []


def validate_cut_prompt(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    kind = getattr(args, "kind", "video")
    fields_by_kind = {
        "image": ("Composition:", "Visible action:", "Shot and lens:", "Surface orientation:", "Style:", "Avoid:"),
        "image-to-video": ("Duration:", "Start image:", "Preserve:", "Subject motion:", "Camera:", "End state:", "Avoid:"),
        "video": ("Duration:", "Visual action:", "Shot and lens:", "Camera:", "Performance and blocking:", "Surface orientation:", "Style:", "Avoid:"),
    }
    required = fields_by_kind[kind]
    errors += _required_line_field_errors(text, required)
    if not _prompt_has_references(text, allow_start_image=kind == "image-to-video"):
        errors.append("missing References section")
    errors += _cut_identifier_errors(text)
    errors += _reference_placeholder_errors(text, f"cut-{kind}")
    if kind == "image":
        temporal_fields = ("Duration:", "Start image:", "Preserve:", "Subject motion:", "Camera:", "End state:")
        errors += [f"image kind forbids temporal field: {field}" for field in temporal_fields if text.count(field)]

    profile = getattr(args, "profile", None)
    duration: float | None = None
    if kind != "image":
        duration, duration_error = _parse_duration_field(text)
        if duration_error:
            errors.append(duration_error)
        errors += duration_profile_errors(text, profile, duration=duration)
    elif profile:
        _, profile_error = profile_limit(profile)
        if profile_error:
            errors.append(profile_error)

    if getattr(args, "check_paths", False):
        errors += reference_path_errors(args.prompt, getattr(args, "project_root", None), kind=f"cut-{kind}")
    return errors


def _range_seconds(raw: str) -> tuple[float, float] | None:
    match = RANGE_RE.fullmatch(raw.strip())
    if not match:
        return None

    def convert(value: str) -> float:
        if ":" in value:
            minutes, seconds = value.split(":", 1)
            return float(int(minutes) * 60 + int(seconds))
        result = float(value)
        if not math.isfinite(result):
            raise ValueError
        return result

    try:
        return convert(match.group(1)), convert(match.group(2))
    except (OverflowError, ValueError):
        return None


def validate_scene_prompt(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    required = ("Scene ID:", "Time range:", "Scene objective:", "Start state:", "End state:", "Visual progression:", "Continuity anchors:", "Cut order:", "Camera rhythm:", "Avoid:")
    errors += _required_line_field_errors(text, required)
    reference_entries = _reference_section_entries(text)
    if reference_entries is None:
        errors.append("missing References section")
    elif not reference_entries:
        errors.append("References section must contain at least one reference")
    errors += _reference_placeholder_errors(text, "scene")
    range_match = re.search(r"(?im)^\s*Time range:\s*(.*?)\s*$", text)
    duration: float | None = None
    if range_match:
        parsed = _range_seconds(range_match.group(1))
        if parsed is None:
            errors.append("Time range must contain numeric start and end values")
        else:
            start, end = parsed
            if end <= start:
                errors.append("Time range end must exceed start")
            duration = end - start
    errors += duration_profile_errors(text, getattr(args, "profile", None), duration=duration)
    for field in required:
        match = re.search(rf"(?m)^{re.escape(field)}\s*(.*)$", text)
        if match and match.group(1).strip().startswith("<"):
            errors.append(f"placeholder remains in {field}")
    if getattr(args, "check_paths", False):
        errors += reference_path_errors(args.prompt, getattr(args, "project_root", None), kind="scene")
    return errors


def _handoff_field_matches(text: str, field: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"(?im)^[ \t]*{re.escape(field)}[ \t]*(.*)$", text))


def _handoff_field_value(text: str, field: str, match: re.Match[str]) -> str:
    value = match.group(1).strip()
    if value:
        return value
    next_starts = [
        other_match.start()
        for other in HANDOFF_FIELDS
        for other_match in _handoff_field_matches(text, other)
        if other_match.start() > match.end()
    ]
    block_end = min(next_starts, default=len(text))
    continuation = [line.strip() for line in text[match.end() : block_end].splitlines() if line.strip()]
    return "\n".join(continuation)


def _parse_handoff_fields(text: str) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    for field in HANDOFF_FIELDS:
        matches = _handoff_field_matches(text, field)
        if len(matches) != 1:
            errors.append(f"required field must appear exactly once: {field}")
            continue
        value = _handoff_field_value(text, field, matches[0])
        values[field] = value
        if not value:
            errors.append(f"required field is empty: {field}")
    return values, errors


def _handoff_duration(value: str | None) -> tuple[float | None, str | None]:
    if not value:
        return None, "Duration: must be a numeric positive value"
    match = re.fullmatch(r"([+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?))(?:\s+seconds?)?", value.strip(), re.IGNORECASE)
    if not match:
        return None, "Duration: must be a numeric positive value"
    try:
        duration = float(match.group(1))
    except (OverflowError, ValueError):
        return None, "Duration: must be a numeric positive value"
    if not math.isfinite(duration):
        return None, "Duration: must be a numeric positive value"
    if duration <= 0:
        return None, "Duration: must be greater than zero"
    return duration, None


def validate_handoff(args: argparse.Namespace) -> list[str]:
    text, errors = read_prompt(args.prompt)
    fields, field_errors = _parse_handoff_fields(text)
    errors += field_errors
    if re.search(r"<[^>\n]+>", text):
        errors.append("handoff contains unresolved angle-bracket placeholder")
    embedded_profile = fields.get("Provider profile:", "")
    cli_profile = getattr(args, "profile", None)
    if embedded_profile and cli_profile and embedded_profile != cli_profile:
        errors.append(f"handoff Provider profile does not match --profile: {embedded_profile} != {cli_profile}")
    duration, duration_error = _handoff_duration(fields.get("Duration:"))
    if duration_error:
        errors.append(duration_error)
    if embedded_profile:
        errors += duration_profile_errors(text, embedded_profile, duration=duration)
    elif cli_profile:
        errors += duration_profile_errors(text, cli_profile, duration=duration)
    if re.search(r"(?i)(api[_ -]?key|access[_ -]?token|password|secret|bearer\s+[A-Za-z0-9._-]+)", text):
        errors.append("handoff contains credential-like material")
    submission = fields.get("Submission:")
    if submission is not None and re.sub(r"\s+", " ", submission.strip()).casefold() != PREPARATION_ONLY_SUBMISSION.casefold():
        errors.append("handoff submission field must remain preparation-only")
    if getattr(args, "check_paths", False):
        errors += reference_path_errors(args.prompt, getattr(args, "project_root", None), kind="handoff")
    return errors


EDITORIAL_SELECTION_FIELDS = frozenset({
    "schema_version",
    "mode",
    "package_id",
    "package_revision",
    "edit_style",
    "ordered_items",
    "missing_jobs",
    "expected_total_seconds",
})
EDITORIAL_ITEM_FIELDS = frozenset({
    "scene_id",
    "job_id",
    "take_id",
    "path",
    "sha256",
    "duration_seconds",
    "selection_status",
    "technical_qc",
    "perceptual_review",
    "approval_ref",
    "placement_reason",
    "overlap_with_previous_seconds",
})
EDITORIAL_MODES = {"draft", "final"}
EDITORIAL_EDIT_STYLES = {"straight_cuts", "overlap"}
EDITORIAL_SELECTION_STATUSES = {"provisional", "selected", "rejected"}
EDITORIAL_TECHNICAL_QC = {"not_checked", "pass", "fail"}
EDITORIAL_PERCEPTUAL_REVIEW = {"pending", "pass", "fail", "uncertain"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _read_editorial_json(path: Path) -> tuple[object | None, list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, parse_constant=_reject_nonfinite_json_constant), []
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return None, [f"cannot read editorial selection JSON: {path}: {exc}"]


def _finite_number(value: object, *, positive: bool = False, nonnegative: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return False
    if not math.isfinite(number):
        return False
    if positive and number <= 0:
        return False
    if nonnegative and number < 0:
        return False
    return True


def _editorial_number_error(value: object, field: str, *, positive: bool = False, nonnegative: bool = False) -> str | None:
    if not _finite_number(value, positive=positive, nonnegative=nonnegative):
        if positive:
            return f"{field} must be a finite number greater than zero"
        if nonnegative:
            return f"{field} must be a finite nonnegative number"
        return f"{field} must be a finite number"
    return None


def _editorial_nonempty_string(value: object, field: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return f"{field} must be a nonempty string"
    return None


def _editorial_path_errors(
    raw: object,
    *,
    root: Path | None,
    field: str,
    check_paths: bool,
    expected_sha256: object,
) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return [f"{field} must be a nonempty relative path"]
    if "\x00" in raw:
        return [f"{field} contains a NUL byte"]
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return [f"{field} is not a valid relative path"]
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return [f"{field} must be a relative filesystem path"]
    if raw.startswith(("/", "\\")) or WINDOWS_ABSOLUTE_PATH_RE.match(raw):
        return [f"{field} must be a relative filesystem path"]
    if root is None:
        return []
    try:
        candidate = (root / Path(raw)).resolve(strict=False)
        candidate.relative_to(root)
    except (OSError, RuntimeError):
        return [f"{field} cannot be resolved within project root"]
    except ValueError:
        return [f"{field} escapes project root"]
    if not check_paths:
        return []
    if not candidate.exists():
        return [f"{field} does not exist: {raw}"]
    if not candidate.is_file():
        return [f"{field} must identify a regular file: {raw}"]
    if expected_sha256 is None:
        return []
    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(expected_sha256):
        return []
    digest = hashlib.sha256()
    try:
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return [f"cannot hash {field}: {raw}: {exc}"]
    if digest.hexdigest().casefold() != expected_sha256.casefold():
        return [f"{field} sha256 does not match: {raw}"]
    return []


def _editorial_item_errors(
    item: object,
    index: int,
    *,
    root: Path | None,
    check_paths: bool,
) -> list[str]:
    prefix = f"ordered_items[{index}]"
    if not isinstance(item, dict):
        return [f"{prefix} must be an object"]
    errors: list[str] = []
    missing = EDITORIAL_ITEM_FIELDS - item.keys()
    extra = item.keys() - EDITORIAL_ITEM_FIELDS
    if missing:
        errors.append(f"{prefix} missing fields: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"{prefix} has unknown fields: {', '.join(sorted(extra))}")
    for field in ("scene_id", "job_id", "take_id"):
        error = _editorial_nonempty_string(item.get(field), f"{prefix}.{field}")
        if error:
            errors.append(error)
    path = item.get("path")
    sha256 = item.get("sha256")
    if path is not None:
        errors += _editorial_path_errors(
            path,
            root=root,
            field=f"{prefix}.path",
            check_paths=check_paths,
            expected_sha256=sha256,
        )
    if sha256 is not None and (not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256)):
        errors.append(f"{prefix}.sha256 must be a 64-character hexadecimal hash or null")
    duration = item.get("duration_seconds")
    if duration is not None:
        error = _editorial_number_error(duration, f"{prefix}.duration_seconds", positive=True)
        if error:
            errors.append(error)
    for field, choices in (
        ("selection_status", EDITORIAL_SELECTION_STATUSES),
        ("technical_qc", EDITORIAL_TECHNICAL_QC),
        ("perceptual_review", EDITORIAL_PERCEPTUAL_REVIEW),
    ):
        value = item.get(field)
        if not isinstance(value, str) or value not in choices:
            errors.append(f"{prefix}.{field} must be one of: {', '.join(sorted(choices))}")
    for field in ("approval_ref", "placement_reason"):
        value = item.get(field)
        if value is not None:
            error = _editorial_nonempty_string(value, f"{prefix}.{field}")
            if error:
                errors.append(error)
    overlap = item.get("overlap_with_previous_seconds")
    error = _editorial_number_error(
        overlap,
        f"{prefix}.overlap_with_previous_seconds",
        nonnegative=True,
    )
    if error:
        errors.append(error)
    return errors


def validate_editorial_selection(args: argparse.Namespace) -> list[str]:
    payload, errors = _read_editorial_json(args.selection)
    if errors:
        return errors
    if not isinstance(payload, dict):
        return ["editorial selection must be a JSON object"]
    missing = EDITORIAL_SELECTION_FIELDS - payload.keys()
    extra = payload.keys() - EDITORIAL_SELECTION_FIELDS
    if missing:
        errors.append(f"editorial selection missing fields: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"editorial selection has unknown fields: {', '.join(sorted(extra))}")

    schema_version = payload.get("schema_version")
    if schema_version != 1 or isinstance(schema_version, bool):
        errors.append("schema_version must be 1")
    mode = payload.get("mode")
    if not isinstance(mode, str) or mode not in EDITORIAL_MODES:
        errors.append("mode must be draft or final")
    edit_style = payload.get("edit_style")
    if not isinstance(edit_style, str) or edit_style not in EDITORIAL_EDIT_STYLES:
        errors.append("edit_style must be straight_cuts or overlap")
    for field in ("package_id", "package_revision"):
        error = _editorial_nonempty_string(payload.get(field), field)
        if error:
            errors.append(error)

    tolerance = getattr(args, "timing_tolerance", 0.1)
    tolerance_error = _editorial_number_error(tolerance, "timing tolerance", nonnegative=True)
    if tolerance_error:
        errors.append(tolerance_error)
        tolerance_value = 0.1
    else:
        tolerance_value = float(tolerance)

    root: Path | None = None
    project_root = getattr(args, "project_root", None)
    if project_root is None:
        errors.append("--project-root is required")
    else:
        try:
            root = Path(project_root).resolve()
        except (OSError, RuntimeError) as exc:
            errors.append(f"cannot resolve project root: {project_root}: {exc}")
        else:
            if not root.is_dir():
                errors.append(f"project root must be a directory: {project_root}")

    missing_jobs = payload.get("missing_jobs")
    missing_job_values: list[str] = []
    if not isinstance(missing_jobs, list):
        errors.append("missing_jobs must be an array of nonempty strings")
    else:
        for index, value in enumerate(missing_jobs):
            error = _editorial_nonempty_string(value, f"missing_jobs[{index}]")
            if error:
                errors.append(error)
            elif isinstance(value, str):
                missing_job_values.append(value)
        if len(missing_job_values) != len(set(missing_job_values)):
            errors.append("missing_jobs must not contain duplicate job IDs")

    ordered_items = payload.get("ordered_items")
    valid_items: list[dict[str, object]] = []
    if not isinstance(ordered_items, list):
        errors.append("ordered_items must be an array")
    else:
        for index, item in enumerate(ordered_items):
            errors += _editorial_item_errors(item, index, root=root, check_paths=bool(getattr(args, "check_paths", False)))
            if isinstance(item, dict):
                valid_items.append(item)

    expected_total = payload.get("expected_total_seconds")
    if expected_total is not None:
        error = _editorial_number_error(
            expected_total, "expected_total_seconds", positive=(mode == "final"), nonnegative=(mode != "final")
        )
        if error:
            errors.append(error)
    elif mode == "final":
        errors.append("final editorial selection requires expected_total_seconds")

    seen_takes: dict[tuple[object, object], int] = {}
    for index, item in enumerate(valid_items):
        job_id = item.get("job_id")
        take_id = item.get("take_id")
        if not isinstance(job_id, str) or not isinstance(take_id, str):
            continue
        key = (job_id, take_id)
        previous = seen_takes.get(key)
        if previous is None:
            seen_takes[key] = index
            continue
        for duplicate_index in (previous, index):
            reason = valid_items[duplicate_index].get("placement_reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(
                    f"ordered_items[{duplicate_index}] repeated job/take requires placement_reason"
                )

    durations: list[float | None] = []
    overlaps: list[float] = []
    for index, item in enumerate(valid_items):
        duration = item.get("duration_seconds")
        durations.append(float(duration) if _finite_number(duration, positive=True) else None)
        overlap = item.get("overlap_with_previous_seconds")
        overlaps.append(float(overlap) if _finite_number(overlap, nonnegative=True) else 0.0)
        if index == 0 and _finite_number(overlap, nonnegative=True) and float(overlap) != 0:
            errors.append("ordered_items[0].overlap_with_previous_seconds must be zero")
        if edit_style == "straight_cuts" and _finite_number(overlap, nonnegative=True) and float(overlap) != 0:
            errors.append(f"ordered_items[{index}].overlap_with_previous_seconds must be zero for straight_cuts")
        if index > 0 and durations[index] is not None and durations[index - 1] is not None:
            if overlaps[index] >= min(durations[index], durations[index - 1]):
                errors.append(
                    f"ordered_items[{index}].overlap_with_previous_seconds must be less than both adjacent durations"
                )

    if mode == "final":
        if not valid_items:
            errors.append("final editorial selection requires at least one ordered item")
        if isinstance(missing_jobs, list) and missing_jobs:
            errors.append("final editorial selection must not contain missing_jobs")
        for index, item in enumerate(valid_items):
            prefix = f"ordered_items[{index}]"
            if item.get("path") is None or item.get("sha256") is None:
                errors.append(f"{prefix} final selection requires path and sha256")
            if not _finite_number(item.get("duration_seconds"), positive=True):
                errors.append(f"{prefix} final selection requires a positive duration_seconds")
            if item.get("selection_status") != "selected":
                errors.append(f"{prefix} final selection requires selection_status=selected")
            if item.get("technical_qc") != "pass":
                errors.append(f"{prefix} final selection requires technical_qc=pass")
            if item.get("perceptual_review") != "pass":
                errors.append(f"{prefix} final selection requires perceptual_review=pass")
            if not isinstance(item.get("approval_ref"), str) or not item.get("approval_ref", "").strip():
                errors.append(f"{prefix} final selection requires approval_ref")

    if _finite_number(expected_total, nonnegative=True) and all(value is not None for value in durations):
        try:
            calculated_total = math.fsum(value for value in durations if value is not None) - math.fsum(overlaps)
        except (OverflowError, ValueError):
            calculated_total = math.inf
        if not math.isfinite(calculated_total):
            errors.append("ordered duration total must be finite")
        elif abs(calculated_total - float(expected_total)) > tolerance_value:
            errors.append(
                f"expected_total_seconds does not match ordered duration total: {calculated_total:g} != {float(expected_total):g}"
            )
    return errors


class _HTMLReferenceParser(HTMLParser):
    """Collect the structural parts needed for static reference validation."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.resources: list[tuple[str, str, str]] = []
        self.html_lang: str | None = None
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.title_depth = 0
        self.main_count = 0
        self.script_count = 0
        self.inline_event_attributes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value for name, value in attrs}
        tag = tag.casefold()
        if tag == "html":
            self.html_lang = attributes.get("lang")
        if tag == "main":
            self.main_count += 1
        if tag == "title":
            self.title_depth += 1
        if tag == "script":
            self.script_count += 1
        if "id" in attributes and attributes["id"] is not None:
            self.ids.append(attributes["id"] or "")
        for name in attributes:
            if name.startswith("on"):
                self.inline_event_attributes.append(name)
        if tag in {"a", "area"} and attributes.get("href") is not None:
            self.links.append((tag, attributes["href"] or ""))
        if tag == "link" and attributes.get("href") is not None:
            self.resources.append((tag, "href", attributes["href"] or ""))
        for attribute in HTML_RESOURCE_TAGS.get(tag, ()):
            if attributes.get(attribute) is not None:
                self.resources.append((tag, attribute, attributes[attribute] or ""))

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self.title_depth:
            self.title_parts.append(data)


def _resolve_local_reference(root: Path, base: Path, raw: str) -> tuple[Path | None, str | None, str | None]:
    """Return (target, fragment, error) for a relative local URL."""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None, None, "invalid"
    if parsed.scheme or parsed.netloc:
        return None, None, "external"
    path_part = unquote(parsed.path)
    if path_part.startswith("/"):
        return None, unquote(parsed.fragment) or None, "absolute"
    try:
        candidate = (base / path_part).resolve(strict=False)
    except (OSError, RuntimeError):
        return None, unquote(parsed.fragment) or None, "resolve"
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, unquote(parsed.fragment) or None, "escape"
    return candidate, unquote(parsed.fragment) or None, None


def _html_file_errors(root: Path, html_path: Path, known_ids: dict[Path, set[str]]) -> list[str]:
    relative = html_path.relative_to(root).as_posix()
    try:
        html_path.resolve(strict=False).relative_to(root)
    except ValueError:
        return [f"HTML reference escapes active skill: {relative}"]
    try:
        text = html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"cannot read HTML reference: {relative}: {exc}"]
    parser = _HTMLReferenceParser()
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, AssertionError) as exc:
        return [f"cannot parse HTML reference: {relative}: {exc}"]
    errors: list[str] = []
    ids = set(parser.ids)
    known_ids[html_path] = ids
    if any(not value for value in parser.ids):
        errors.append(f"HTML id must be nonempty: {relative}")
    if len(parser.ids) != len(ids):
        duplicates = sorted({value for value in parser.ids if parser.ids.count(value) > 1 and value})
        errors.append(f"duplicate HTML id: {relative}#{', #'.join(duplicates)}")
    if not parser.html_lang:
        errors.append(f"HTML page must declare lang: {relative}")
    if not parser.title_parts or not "".join(parser.title_parts).strip():
        errors.append(f"HTML page is missing a title: {relative}")
    if parser.main_count != 1:
        errors.append(f"HTML page must contain one main element: {relative}")
    if parser.script_count:
        errors.append(f"HTML scripts are not allowed: {relative}")
    if parser.inline_event_attributes:
        errors.append(f"HTML inline event handlers are not allowed: {relative}")

    for _, raw in parser.links:
        target, fragment, resolve_error = _resolve_local_reference(root, html_path.parent, raw)
        try:
            parsed = urlsplit(raw)
        except ValueError:
            errors.append(f"cannot resolve HTML reference: {relative} -> {raw}")
            continue
        if resolve_error == "external":
            if parsed.scheme.casefold() in {"http", "https", "mailto", "tel"}:
                continue
            errors.append(f"unsupported external HTML link: {relative} -> {raw}")
            continue
        if resolve_error in {"absolute", "escape"}:
            errors.append(f"HTML reference escapes active skill: {relative} -> {raw}")
            continue
        if resolve_error in {"invalid", "resolve"}:
            errors.append(f"cannot resolve HTML reference: {relative} -> {raw}")
            continue
        if target is None:
            errors.append(f"cannot resolve HTML reference: {relative} -> {raw}")
            continue
        if not target.exists():
            errors.append(f"broken HTML reference: {relative} -> {raw}")
            continue
        if fragment and target.suffix.casefold() == ".html":
            if fragment not in known_ids.get(target, set()):
                errors.append(f"broken HTML fragment: {relative} -> {raw}")

    for tag, attribute, raw in parser.resources:
        target, fragment, resolve_error = _resolve_local_reference(root, html_path.parent, raw)
        if resolve_error == "external":
            errors.append(f"external HTML asset is not allowed: {relative} -> {raw}")
            continue
        if resolve_error in {"absolute", "escape"}:
            errors.append(f"HTML asset escapes active skill: {relative} -> {raw}")
            continue
        if resolve_error in {"invalid", "resolve"}:
            errors.append(f"cannot resolve HTML asset: {relative} -> {raw}")
            continue
        if target is None:
            errors.append(f"cannot resolve HTML asset: {relative} -> {raw}")
            continue
        if not target.exists():
            errors.append(f"broken HTML asset: {relative} -> {raw}")
        elif not target.is_file():
            errors.append(f"HTML asset is not a regular file: {relative} -> {raw}")
        if fragment and target.suffix.casefold() == ".html" and fragment not in known_ids.get(target, set()):
            errors.append(f"broken HTML asset fragment: {relative} -> {raw}")
    return errors


def _knowledge_map_errors(root: Path, known_ids: dict[Path, set[str]]) -> list[str]:
    path = root / "data" / "knowledge-map.json"
    relative = path.relative_to(root).as_posix()
    try:
        path.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return [f"knowledge map escapes active skill: {relative}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"invalid knowledge map: {relative}: {exc}"]
    if not isinstance(payload, dict):
        return ["knowledge map must be an object"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("knowledge map schema_version must be 1")
    if payload.get("skill_name") != "ai-video-production":
        errors.append("knowledge map skill_name must be ai-video-production")
    topics = payload.get("topics")
    if not isinstance(topics, list):
        return errors + ["knowledge map topics must be an array"]
    ids: set[str] = set()
    paths: set[str] = set()
    for index, topic in enumerate(topics):
        prefix = f"knowledge map topic {index + 1}"
        if not isinstance(topic, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = KNOWLEDGE_MAP_FIELDS - topic.keys()
        extra = topic.keys() - KNOWLEDGE_MAP_FIELDS
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(sorted(missing))}")
        if extra:
            errors.append(f"{prefix} has unknown fields: {', '.join(sorted(extra))}")
        topic_id = topic.get("id")
        topic_path = topic.get("path")
        anchor = topic.get("anchor")
        if not isinstance(topic_id, str) or not topic_id:
            errors.append(f"{prefix} id must be a nonempty string")
        elif topic_id in ids:
            errors.append(f"duplicate knowledge map topic id: {topic_id}")
        else:
            ids.add(topic_id)
        if not isinstance(topic_path, str) or not topic_path:
            errors.append(f"{prefix} path must be a nonempty string")
            continue
        if topic_path in paths:
            errors.append(f"duplicate knowledge map path: {topic_path}")
        paths.add(topic_path)
        target, _, resolve_error = _resolve_local_reference(root, root, topic_path)
        if resolve_error in {"absolute", "escape"}:
            errors.append(f"knowledge map path escapes active skill: {topic_path}")
            continue
        if resolve_error == "external" or target is None:
            errors.append(f"knowledge map path must be relative: {topic_path}")
            continue
        if not target.exists():
            errors.append(f"knowledge map path does not exist: {topic_path}")
            continue
        if target.suffix.casefold() != ".html":
            errors.append(f"knowledge map path must target HTML: {topic_path}")
        markers = KNOWLEDGE_CONTENT_MARKERS.get(topic_path, ())
        try:
            topic_parser = _HTMLReferenceParser()
            topic_parser.feed(target.read_text(encoding="utf-8"))
            topic_parser.close()
            html_text = " ".join(topic_parser.text_parts).casefold()
        except (OSError, UnicodeError, ValueError, AssertionError) as exc:
            errors.append(f"cannot read knowledge topic HTML: {topic_path}: {exc}")
        else:
            for marker in markers:
                if marker.casefold() not in html_text:
                    errors.append(f"knowledge topic content missing: {topic_path} -> {marker}")
        if not isinstance(anchor, str) or not anchor:
            errors.append(f"{prefix} anchor must be a nonempty string")
        elif anchor not in known_ids.get(target, set()):
            errors.append(f"knowledge map anchor does not exist: {topic_path}#{anchor}")
        for field in ("legacy_sections", "source_refs"):
            value = topic.get(field)
            if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
                errors.append(f"{prefix} {field} must be a nonempty string array")
        status = topic.get("status")
        if status not in {"active", "historical"}:
            errors.append(f"{prefix} status must be active or historical")
    missing_paths = CANONICAL_KNOWLEDGE_PATHS - paths
    for missing in sorted(missing_paths):
        errors.append(f"knowledge map missing canonical topic: {missing}")
    references_root = root / "references"
    html_paths = {
        path.relative_to(root).as_posix()
        for path in references_root.rglob("*.html")
    } if references_root.is_dir() else set()
    for orphan in sorted(html_paths - paths):
        errors.append(f"knowledge map missing HTML topic: {orphan}")
    index_path = root / "references" / "index.html"
    index_targets: set[str] = set()
    if index_path.is_file():
        try:
            index_parser = _HTMLReferenceParser()
            index_parser.feed(index_path.read_text(encoding="utf-8"))
            index_parser.close()
            for _, raw in index_parser.links:
                target, _, resolve_error = _resolve_local_reference(root, index_path.parent, raw)
                if resolve_error is None and target is not None and target.suffix.casefold() == ".html":
                    index_targets.add(target.relative_to(root).as_posix())
        except (OSError, UnicodeError, ValueError, AssertionError) as exc:
            errors.append(f"cannot inspect knowledge map index: {exc}")
    for topic_path in sorted(paths - {"references/index.html"}):
        if topic_path in html_paths and topic_path not in index_targets:
            errors.append(f"knowledge map topic is unreachable from index: {topic_path}")
    return errors


def validate_references(args: argparse.Namespace) -> list[str]:
    try:
        root = args.root.resolve()
    except (OSError, RuntimeError) as exc:
        return [f"cannot resolve active skill root: {args.root}: {exc}"]
    required_paths = (
        "SKILL.md",
        "agents/openai.yaml",
        "assets/templates",
        "assets/templates/editorial-selection.json",
        "assets/knowledge-base.css",
        "schemas/editorial-selection.schema.json",
        "data/knowledge-map.json",
        "references/index.html",
        "references/core",
        "references/deliverables",
        "references/profiles/generation-profiles.json",
        "scripts/init_production_package.py",
        "scripts/validate_production_package.py",
        "scripts/validate_ai_video.py",
    )
    errors: list[str] = []
    for item in required_paths:
        candidate = root / item
        if not candidate.exists():
            errors.append(f"missing active skill path: {item}")
            continue
        try:
            candidate.resolve(strict=False).relative_to(root)
        except (OSError, RuntimeError, ValueError):
            errors.append(f"active skill path escapes root: {item}")
    markdown_files = [root / "SKILL.md"] + sorted((root / "references").rglob("*.md")) if (root / "references").is_dir() else []
    html_files = sorted((root / "references").rglob("*.html")) if (root / "references").is_dir() else []
    known_ids: dict[Path, set[str]] = {}
    for html_file in html_files:
        try:
            parser = _HTMLReferenceParser()
            parser.feed(html_file.read_text(encoding="utf-8"))
            parser.close()
            known_ids[html_file] = set(parser.ids)
        except (OSError, UnicodeError, ValueError, AssertionError):
            continue
    for html_file in html_files:
        errors += _html_file_errors(root, html_file, known_ids)
    for markdown in markdown_files:
        text, read_errors = read_prompt(markdown)
        errors += read_errors
        for raw in LINK_RE.findall(text):
            try:
                parsed = urlsplit(raw)
            except ValueError:
                errors.append(f"cannot resolve active reference: {markdown.relative_to(root)} -> {raw}")
                continue
            if parsed.scheme or parsed.netloc or raw.startswith("#"):
                continue
            target, fragment, resolve_error = _resolve_local_reference(root, markdown.parent, raw)
            if resolve_error in {"absolute", "escape"}:
                errors.append(f"reference escapes active skill: {markdown.relative_to(root)} -> {raw}")
                continue
            if resolve_error in {"invalid", "resolve"}:
                errors.append(f"cannot resolve active reference: {markdown.relative_to(root)} -> {raw}")
                continue
            if target is None or not target.exists():
                errors.append(f"broken active reference: {markdown.relative_to(root)} -> {raw}")
                continue
            if fragment and target.suffix.casefold() == ".html" and fragment not in known_ids.get(target, set()):
                errors.append(f"broken active reference fragment: {markdown.relative_to(root)} -> {raw}")
    active_parts: list[str] = []
    for active_path in markdown_files + html_files:
        try:
            if not active_path.is_file():
                continue
            active_path.resolve(strict=False).relative_to(root)
            active_parts.append(active_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, RuntimeError, ValueError):
            continue
    active_text = "\n".join(active_parts)
    map_path = root / "data" / "knowledge-map.json"
    if map_path.is_file():
        errors += _knowledge_map_errors(root, known_ids)
        try:
            active_text += "\n" + map_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            pass
    if re.search(r"\bSC\d+\b", active_text):
        errors.append("concrete scene identifier appears in active generic skill")
    if re.search(r"/Users/", active_text):
        errors.append("absolute user path appears in active generic skill")
    return errors


def validate_package(args: argparse.Namespace) -> list[str]:
    try:
        from validate_production_package import validate
    except ImportError as exc:
        return [f"cannot load package validator: {exc}"]
    root = args.root.resolve()
    if not root.is_dir():
        return ["project_root must be a directory"]
    return validate(root)


def print_result(errors: list[str], success: str) -> int:
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(success)
    return 0


def add_prompt_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser], name: str, function: Callable[[argparse.Namespace], list[str]], *, profile: bool = False, paths: bool = False, image: bool = False) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name)
    parser.set_defaults(function=function)
    parser.add_argument("prompt", type=Path)
    if image:
        parser.add_argument("image", type=Path, nargs="?")
        parser.add_argument("--image", dest="image_option", type=Path)
    if profile:
        parser.add_argument("--profile")
    if paths:
        parser.add_argument("--check-paths", action="store_true")
        parser.add_argument("--project-root", type=Path)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    package = subparsers.add_parser("package", aliases=["production-package"])
    package.set_defaults(function=validate_package)
    package.add_argument("root", type=Path)
    add_prompt_parser(subparsers, "character-sheet", validate_character, image=True)
    add_prompt_parser(subparsers, "environment-sheet", validate_environment, image=True)
    add_prompt_parser(subparsers, "object-sheet", validate_object, image=True)
    add_prompt_parser(subparsers, "vfx-sheet", validate_vfx, image=True)
    add_prompt_parser(subparsers, "storyboard", validate_storyboard, image=True)
    add_prompt_parser(subparsers, "text-storyboard", validate_text_storyboard)
    cut_prompt = add_prompt_parser(subparsers, "cut-prompt", validate_cut_prompt, profile=True, paths=True)
    cut_prompt.add_argument("--kind", choices=("image", "image-to-video", "video"), default="video")
    add_prompt_parser(subparsers, "scene-prompt", validate_scene_prompt, profile=True, paths=True)
    add_prompt_parser(subparsers, "handoff", validate_handoff, profile=True, paths=True)
    editorial = subparsers.add_parser("editorial-selection")
    editorial.set_defaults(function=validate_editorial_selection)
    editorial.add_argument("selection", type=Path)
    editorial.add_argument("--project-root", type=Path, required=True)
    editorial.add_argument("--check-paths", action="store_true")
    editorial.add_argument("--timing-tolerance", type=float, default=0.1)
    references = subparsers.add_parser("references")
    references.set_defaults(function=validate_references)
    references.add_argument("root", type=Path, nargs="?", default=SKILL_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = args.function(args)
    messages = {
        "package": "OK: production package structure and cut timing are valid",
        "production-package": "OK: production package structure and cut timing are valid",
        "character-sheet": "OK: minimal three-zone character sheet is valid",
        "environment-sheet": "OK: environment set-bible prompt and image are valid",
        "object-sheet": "OK: recurring-object board is valid",
        "vfx-sheet": "OK: VFX reference board is valid",
        "storyboard": "OK: image-only storyboard is text-free and structurally valid",
        "text-storyboard": "OK: text-storyboard panels are valid",
        "cut-prompt": "OK: cut prompt contract is valid",
        "scene-prompt": "OK: scene prompt contract is valid",
        "handoff": "OK: generation handoff is reviewable and preparation-only",
        "editorial-selection": (
            "OK: editorial selection structure is valid; requested path/hash checks passed where values were provided; unresolved media and timing fields remain unverified"
            if getattr(args, "check_paths", False)
            else "OK: editorial selection structure and known timing fields are valid; media paths were not checked"
        ),
        "references": "OK: active AI-video references are complete",
    }
    return print_result(errors, messages[args.command])


if __name__ == "__main__":
    raise SystemExit(main())
