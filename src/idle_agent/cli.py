"""CLI for the cam-01 offline spike (file) and future live RTSP."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_clip_start(
    source: str,
    url: str,
    clip_start_text: Optional[str],
    tz: tzinfo,
) -> Optional[datetime]:
    """Decide what wall-clock time video t=0 corresponds to.

    - An explicit --clip-start always wins; a bare time means site local time.
    - A recording with no --clip-start takes its start from an NVR-style file
      name (…_20261118150005_….mp4). If the name has no stamp, stop: guessing
      would put wrong times on every event.
    - A live stream returns None; the pipeline anchors it to the wall clock at
      the moment the stream opens.
    """
    from idle_agent import clock

    if clip_start_text:
        try:
            return clock.parse_iso(clip_start_text, tz)
        except ValueError as exc:
            raise SystemExit(f"--clip-start: {exc}") from exc
    if source == "file":
        derived = clock.clip_start_from_filename(url, tz)
        if derived is not None:
            print(f"Clip start read from the file name: {derived.isoformat()}")
            return derived
        raise SystemExit(
            f"Cannot tell when '{Path(url).name}' was recorded, so every event "
            f"time would be wrong.\nPass the recording's real start, e.g.\n"
            f'  --clip-start "2026-11-18T15:00:05+05:00"\n'
            f"or keep the NVR file name, which carries it "
            f"(…_YYYYMMDDhhmmss_….mp4)."
        )
    return None


def _default_cam01_video(root: Path) -> Path | None:
    cam_dir = root / "recordings" / "cam-01"
    if not cam_dir.is_dir():
        return None
    videos = sorted(
        [
            *cam_dir.glob("*.mp4"),
            *cam_dir.glob("*.avi"),
            *cam_dir.glob("*.mkv"),
            *cam_dir.glob("*.mov"),
        ]
    )
    return videos[0] if videos else None


def build_parser() -> argparse.ArgumentParser:
    root = _repo_root()
    default_video = _default_cam01_video(root)
    parser = argparse.ArgumentParser(
        description="Employee idle-time spike: file (cam-01) or RTSP → YOLO → events/preview",
    )
    parser.add_argument(
        "--source",
        choices=["file", "rtsp"],
        default="file",
        help="Video source type (default: file)",
    )
    parser.add_argument(
        "--url",
        default=str(default_video) if default_video else "",
        help="File path or RTSP URL (default: first mp4 under recordings/cam-01)",
    )
    parser.add_argument("--camera-id", default="cam-01")
    parser.add_argument(
        "--zones",
        default=str(root / "config" / "zones.yaml"),
    )
    parser.add_argument(
        "--idle-rules",
        default=str(root / "config" / "idle_rules.yaml"),
    )
    parser.add_argument(
        "--demo-overrides",
        default=str(root / "config" / "demo_overrides.yaml"),
        help="Short thresholds for offline testing; pass empty string to disable",
    )
    parser.add_argument(
        "--output-dir",
        default=str(root / "output"),
    )
    parser.add_argument("--model", default="yolov8s-pose.pt")
    parser.add_argument("--target-fps", type=float, default=8.0)
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional cap on source frames (useful for CPU smoke tests)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Torch device override, e.g. cuda:0 or cpu",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip writing output/preview.mp4",
    )
    parser.add_argument(
        "--clip-start",
        default=None,
        help=(
            "Wall-clock start of the recording (ISO-8601), e.g. "
            "2026-11-18T15:00:05+05:00. Optional for NVR-named files, which carry "
            "it; ignored for --source rtsp unless given."
        ),
    )
    parser.add_argument(
        "--preview-scale",
        type=float,
        default=0.5,
        help="Scale factor for preview.mp4 (default 0.5 to save disk on long clips)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Allow `python -m idle_agent.cli` when repo src/ is on PYTHONPATH
    root = _repo_root()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from idle_agent import clock

    args = build_parser().parse_args(argv)
    if not args.url:
        print(
            "No video URL/path provided and no file found in recordings/cam-01/. "
            "Place an MP4 there or pass --url.",
            file=sys.stderr,
        )
        return 2

    # Settle the clock before loading the model, so a missing start time fails
    # in a second instead of after a long model download.
    tz = clock.tz_from_rules_file(args.idle_rules)
    clip_start = resolve_clip_start(args.source, args.url, args.clip_start, tz)

    from idle_agent.pipeline import run_pipeline

    demo = args.demo_overrides if args.demo_overrides else None
    run_pipeline(
        source_type=args.source,
        source_uri=args.url,
        camera_id=args.camera_id,
        zones_path=args.zones,
        idle_rules_path=args.idle_rules,
        demo_overrides_path=demo,
        output_dir=args.output_dir,
        model_name=args.model,
        target_fps=args.target_fps,
        max_frames=args.max_frames,
        device=args.device,
        write_preview=not args.no_preview,
        clip_start=clip_start,
        preview_scale=args.preview_scale,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
