#!/usr/bin/env python3
"""Validate a mixcut plan and build JianYing Pro drafts without exporting."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def load_jianying_runtime():
    script_dir = Path(__file__).resolve().parent
    env_root = os.getenv("JY_SKILL_ROOT", "").strip()
    candidates = [
        Path(env_root) if env_root else None,
        script_dir.parent.parent / "jianying-editor",
        Path.home() / ".codex" / "skills" / "jianying-editor",
        Path.home() / ".agents" / "skills" / "jianying-editor",
        Path.cwd() / ".agent" / "skills" / "jianying-editor",
        Path.cwd() / "skills" / "jianying-editor",
    ]
    for candidate in candidates:
        if candidate and (candidate / "scripts" / "jy_wrapper.py").is_file():
            scripts_path = str((candidate / "scripts").resolve())
            if scripts_path not in sys.path:
                sys.path.insert(0, scripts_path)
            from jy_wrapper import JyProject, get_default_drafts_root
            import pyJianYingDraft as draft

            return JyProject, draft, get_default_drafts_root
    attempted = "\n- ".join(str(path) for path in candidates if path)
    raise ImportError(
        "Could not find jianying-editor/scripts/jy_wrapper.py. Tried:\n- " + attempted
    )


JyProject, draft, get_default_drafts_root = load_jianying_runtime()


def read_plan(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def absolute_media_path(value: str, field: str) -> Path:
    if value.lower().startswith("smb://"):
        raise ValueError(f"{field} must be a mounted local path, not an SMB URI: {value}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{field} must be an absolute path: {value}")
    if not path.is_file():
        raise FileNotFoundError(f"{field} does not exist: {path}")
    return path.resolve()


def timeline_duration(plan: dict, reference: Path) -> float:
    configured = plan.get("duration")
    if configured is not None:
        duration = float(configured)
    else:
        duration = draft.VideoMaterial(str(reference)).duration / 1_000_000
    if duration <= 0:
        raise ValueError("duration must be greater than zero")
    return round(duration, 6)


def validate_continuity(segments: Iterable[dict], duration: float, name: str) -> List[dict]:
    ordered = sorted(segments, key=lambda item: float(item["start"]))
    if not ordered:
        raise ValueError(f"Variant {name!r} has no segments")
    cursor = 0.0
    tolerance = 0.002
    for index, segment in enumerate(ordered):
        start = float(segment["start"])
        end = float(segment["end"])
        if end <= start:
            raise ValueError(f"Variant {name!r} segment {index} has end <= start")
        if abs(start - cursor) > tolerance:
            raise ValueError(
                f"Variant {name!r} has a gap or overlap at {cursor:.3f}s -> {start:.3f}s"
            )
        cursor = end
    if abs(cursor - duration) > tolerance:
        raise ValueError(
            f"Variant {name!r} ends at {cursor:.3f}s, expected {duration:.3f}s"
        )
    return ordered


def validate_subtitles(subtitles: Iterable[dict], duration: float) -> List[dict]:
    ordered = sorted(subtitles, key=lambda item: float(item["start"]))
    previous_end = 0.0
    for index, subtitle in enumerate(ordered):
        start = float(subtitle["start"])
        end = float(subtitle["end"])
        text = str(subtitle.get("text", "")).strip()
        if not text:
            raise ValueError(f"Subtitle {index} has no text")
        if start < 0 or end <= start or end > duration + 0.002:
            raise ValueError(f"Subtitle {index} has an invalid time range")
        if start < previous_end - 0.002:
            raise ValueError(f"Subtitle {index} overlaps the previous subtitle")
        previous_end = end
    return ordered


def validate_plan(plan: dict) -> Tuple[Path, float, List[dict], List[dict]]:
    reference = absolute_media_path(str(plan.get("reference_video", "")), "reference_video")
    duration = timeline_duration(plan, reference)
    width = int(plan.get("width", 1080))
    height = int(plan.get("height", 1920))
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive integers")

    subtitles = validate_subtitles(plan.get("subtitles", []), duration)
    variants = plan.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError("variants must be a non-empty list")

    normalized = []
    names = set()
    material_durations: Dict[Path, float] = {}
    for variant in variants:
        name = str(variant.get("name", "")).strip()
        if not name or "/" in name or "\\" in name:
            raise ValueError(f"Invalid draft name: {name!r}")
        if name in names:
            raise ValueError(f"Duplicate draft name: {name}")
        names.add(name)
        segments = validate_continuity(variant.get("segments", []), duration, name)
        normalized_segments = []
        for segment in segments:
            source_value = str(segment.get("source", "")).strip()
            is_reference = source_value == "reference"
            source = reference if is_reference else absolute_media_path(source_value, "segment.source")
            start = float(segment["start"])
            end = float(segment["end"])
            source_start = float(segment.get("source_start", start if is_reference else 0.0))
            if source_start < 0:
                raise ValueError(f"Negative source_start in {name}: {source_start}")
            if source not in material_durations:
                material_durations[source] = draft.VideoMaterial(str(source)).duration / 1_000_000
            required = source_start + (end - start)
            if required > material_durations[source] + 0.002:
                raise ValueError(
                    f"Source too short in {name}: {source.name}; need {required:.3f}s, "
                    f"have {material_durations[source]:.3f}s"
                )
            normalized_segments.append(
                {
                    "start": start,
                    "end": end,
                    "source": source,
                    "source_start": source_start,
                    "origin": str(segment.get("origin", "参考视频" if is_reference else "素材库")),
                    "is_reference": is_reference,
                }
            )
        normalized.append(
            {
                "name": name,
                "theme": str(variant.get("theme", "")).strip(),
                "segments": normalized_segments,
            }
        )
    return reference, duration, subtitles, normalized


def localize_media(source: Path, media_dir: Path, cache: Dict[Path, Path]) -> Path:
    if source in cache:
        return cache[source]
    destination = media_dir / f"{len(cache) + 1:02d}_{source.name}"
    shutil.copy2(source, destination)
    cache[source] = destination
    return destination


def extract_audio(ffmpeg: str, reference: Path, output: Path) -> None:
    copy_result = subprocess.run(
        [ffmpeg, "-y", "-i", str(reference), "-vn", "-c:a", "copy", str(output)],
        capture_output=True,
    )
    if copy_result.returncode == 0:
        return
    subprocess.run(
        [ffmpeg, "-y", "-i", str(reference), "-vn", "-c:a", "aac", "-b:a", "192k", str(output)],
        check=True,
        capture_output=True,
    )


def add_video_segment(project, path: Path, start: float, end: float, source_start: float) -> None:
    material = draft.VideoMaterial(str(path))
    duration_us = round((end - start) * 1_000_000)
    segment = draft.VideoSegment(
        material,
        draft.Timerange(round(start * 1_000_000), duration_us),
        source_timerange=draft.Timerange(round(source_start * 1_000_000), duration_us),
        volume=0,
    )
    project._ensure_track(draft.TrackType.video, "混剪画面")
    project.script.add_segment(segment, "混剪画面")


def count_segments(draft_info: Path) -> Dict[str, int]:
    data = json.loads(draft_info.read_text(encoding="utf-8"))
    counts = {"video": 0, "audio": 0, "text": 0}
    for track in data.get("tracks", []):
        track_type = track.get("type")
        if track_type in counts:
            counts[track_type] += len(track.get("segments", []))
    return counts


def build(plan_path: Path, plan: dict, overwrite: bool) -> List[dict]:
    import imageio_ffmpeg

    reference, duration, subtitles, variants = validate_plan(plan)
    width = int(plan.get("width", 1080))
    height = int(plan.get("height", 1920))
    drafts_root_value = plan.get("drafts_root")
    drafts_root = Path(drafts_root_value or get_default_drafts_root()).expanduser().resolve()
    output_value = plan.get("output_dir", "outputs")
    output_dir = Path(output_value).expanduser()
    if not output_dir.is_absolute():
        output_dir = (plan_path.parent / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    drafts_root.mkdir(parents=True, exist_ok=True)
    for variant in variants:
        target = drafts_root / variant["name"]
        if target.exists() and not overwrite:
            raise FileExistsError(f"Draft already exists: {target}")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    manifest = []
    for variant in variants:
        kwargs = {"width": width, "height": height, "overwrite": overwrite}
        kwargs["drafts_root"] = str(drafts_root)
        project = JyProject(variant["name"], **kwargs)
        project_dir = Path(project.draft_dir)
        media_dir = project_dir / "本地素材"
        media_dir.mkdir(parents=True, exist_ok=True)
        cache: Dict[Path, Path] = {}
        local_reference = localize_media(reference, media_dir, cache)
        audio_path = media_dir / "完整原口播及背景音.m4a"
        extract_audio(ffmpeg, local_reference, audio_path)
        audio = project.add_media_safe(
            str(audio_path),
            start_time="0s",
            duration=f"{duration}s",
            track_name="原口播及原背景音",
        )
        if not audio:
            raise RuntimeError(f"Audio import failed: {variant['name']}")

        cuts = []
        replaced_seconds = 0.0
        for segment in variant["segments"]:
            local_source = localize_media(segment["source"], media_dir, cache)
            add_video_segment(
                project,
                local_source,
                segment["start"],
                segment["end"],
                segment["source_start"],
            )
            if not segment["is_reference"]:
                replaced_seconds += segment["end"] - segment["start"]
            cuts.append(
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "source": str(segment["source"]),
                    "source_start": segment["source_start"],
                    "origin": segment["origin"],
                }
            )

        for subtitle in subtitles:
            project.add_text_simple(
                subtitle["text"],
                start_time=f"{float(subtitle['start'])}s",
                duration=f"{float(subtitle['end']) - float(subtitle['start'])}s",
                font_size=6.0,
                color_rgb=(1.0, 1.0, 1.0),
                clip_settings=draft.ClipSettings(transform_y=-0.72),
            )

        project.save()
        draft_info = project_dir / "draft_info.json"
        if not draft_info.is_file():
            raise RuntimeError(f"draft_info.json missing: {project_dir}")
        counts = count_segments(draft_info)
        expected_text = len(subtitles)
        if (
            counts["video"] != len(variant["segments"])
            or counts["audio"] != 1
            or counts["text"] < expected_text
        ):
            raise RuntimeError(
                f"Acceptance failed for {variant['name']}: {counts}, "
                f"expected video={len(variant['segments'])}, audio=1, text>={expected_text}"
            )
        manifest.append(
            {
                "name": variant["name"],
                "path": str(project_dir),
                "theme": variant["theme"],
                "duration": duration,
                "replaced_seconds": round(replaced_seconds, 3),
                "replacement_ratio": round(replaced_seconds / duration, 4),
                "track_segments": counts,
                "exported": False,
                "cuts": cuts,
            }
        )
        print(
            f"VERIFIED {variant['name']}: video={counts['video']} "
            f"audio={counts['audio']} subtitles={counts['text']}",
            flush=True,
        )

    manifest_path = output_dir / "build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MANIFEST {manifest_path}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a mixcut plan and create JianYing drafts without exporting."
    )
    parser.add_argument("plan", type=Path, help="Path to a UTF-8 JSON plan")
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate paths, timings, and source durations only"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite same-name drafts; requires explicit user authorization"
    )
    args = parser.parse_args()

    plan_path = args.plan.expanduser().resolve()
    if not plan_path.is_file():
        parser.error(f"Plan does not exist: {plan_path}")
    plan = read_plan(plan_path)
    reference, duration, subtitles, variants = validate_plan(plan)
    if args.validate_only:
        result = {
            "status": "valid",
            "reference_video": str(reference),
            "duration": duration,
            "variants": len(variants),
            "subtitles": len(subtitles),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    build(plan_path, plan, args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
