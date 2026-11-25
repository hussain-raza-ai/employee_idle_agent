#!/usr/bin/env python3
"""Primary-track diagnostic: does the tracker hold the operator, and when?

Prints occupancy, the locked primary ID, the zone state and the motion score
every 15 s of video, then a summary. Use it to check zone polygons and the
primary-track settings on a new camera before trusting any idle events.

    python scripts/diag_primary.py                       # first video under recordings/cam-01
    python scripts/diag_primary.py --video clip.mp4 --seconds 300 --device cpu
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from idle_agent.detect import Detector  # noqa: E402
from idle_agent.primary import ZonePrimaryTracker  # noqa: E402
from idle_agent.sources import VideoSource  # noqa: E402
from idle_agent.state_machine import ZoneStateMachine, load_rules  # noqa: E402
from idle_agent.zones import load_zones, person_in_zone  # noqa: E402


def _default_video(camera_id: str) -> str | None:
    rec = Path(os.environ.get("RECORDINGS_DIR", ROOT / "recordings")) / camera_id
    if not rec.is_dir():
        return None
    videos = sorted(
        p for p in rec.iterdir() if p.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov"}
    )
    return str(videos[0]) if videos else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--camera-id", default=os.environ.get("CAMERA_ID", "cam-01"))
    parser.add_argument("--video", default=os.environ.get("VIDEO"))
    parser.add_argument("--device", default=os.environ.get("DEVICE", "cuda:0"))
    parser.add_argument("--model", default=os.environ.get("MODEL", "yolov8s-pose.pt"))
    parser.add_argument("--target-fps", type=float, default=8.0)
    parser.add_argument("--seconds", type=float, default=180.0, help="video seconds to scan")
    parser.add_argument("--no-demo", action="store_true", help="skip demo_overrides.yaml")
    args = parser.parse_args()

    video = args.video or _default_video(args.camera_id)
    if not video or not Path(video).is_file():
        print(
            f"No video. Pass --video or put one under recordings/{args.camera_id}/",
            file=sys.stderr,
        )
        return 2

    zones = load_zones(ROOT / "config" / "zones.yaml", camera_id=args.camera_id)
    if not zones:
        print(f"No enabled zone for {args.camera_id} in config/zones.yaml", file=sys.stderr)
        return 2
    print("zones", [(z.id, z.polygon) for z in zones])

    demo = None if args.no_demo else ROOT / "config" / "demo_overrides.yaml"
    rules = load_rules(ROOT / "config" / "idle_rules.yaml", demo)
    pc = rules.get("primary_track", {})
    primary = ZonePrimaryTracker(
        enabled=True,
        lost_grace_seconds=float(pc.get("lost_grace_seconds", 5)),
        assign_dwell_seconds=float(pc.get("assign_dwell_seconds", 0.5)),
        match_center_dist=float(pc.get("match_center_dist", 0.08)),
        match_iou=float(pc.get("match_iou", 0.25)),
    )
    sm = ZoneStateMachine(args.camera_id, [z.id for z in zones], rules)
    conf = float(rules.get("evaluation", {}).get("person_confidence_min", 0.45))
    det = Detector(model_name=args.model, conf_min=conf, device=args.device)
    det.load()

    counts = {"occ": 0, "empty": 0}
    zone = zones[0]
    with VideoSource(video, "file") as src:
        every = max(1, int(round(src.source_fps / args.target_fps)))
        max_index = int(args.seconds * src.source_fps)
        print(f"video {video} @ {src.source_fps:.1f} fps, sampling every {every} frame(s)")
        for pkt in src.frames():
            if pkt.index >= max_index:
                break
            if pkt.index % every:
                continue
            people = det.infer(pkt.frame)
            occ, person, pid = primary.update(zone, pkt.timestamp_seconds, people)
            counts["occ" if occ else "empty"] += 1
            sm.update(
                zone.id,
                pkt.timestamp_seconds,
                occ,
                person.motion_score if person else 0.0,
                pid,
                person.confidence if person else 0.0,
            )
            state = sm.states_snapshot()[zone.id]
            if int(pkt.timestamp_seconds) % 15 == 0 and pkt.index % (every * 8) == 0:
                in_poly = sum(
                    1 for p in people if person_in_zone(p.center_norm[0], p.center_norm[1], zone)
                )
                motion = None if not person else round(person.motion_score, 4)
                print(
                    f"t={pkt.timestamp_seconds:.1f}s occ={occ} prim={pid} state={state} "
                    f"people={len(people)} in_poly={in_poly} m={motion}"
                )
    print("counts", counts, "final", sm.states_snapshot())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
