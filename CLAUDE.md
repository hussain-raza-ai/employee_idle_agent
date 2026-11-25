# CLAUDE.md — Employee Idle Agent

Read this first in every new session. The Vast.ai GPU instance is **disposable**:
GitHub holds the code, a private B2/S3 bucket holds the video and run outputs.

## What this project does

On-prem CCTV agent, Phase 1 = employee idle time. It reads a video file or RTSP
stream, detects the one operator at a workstation, and emits timed events
(`IDLE`, `AWAY`, `PHONE`, `INTERACTING`, `OFF_SEAT`, `NOT_WORKING`), each with
`_STARTED` / `_ESCALATED` / `_ENDED`. Anonymous track IDs only, no face
recognition. Alert + supervisor review, never automatic discipline.

Current pilot: `cam-01`, zone `ws-counter-1` (a counter computer-operator desk).

## Where to start

- `docs/architecture.md` — intended design
- `docs/idle-rules.md` — thresholds and their rationale
- `docs/devlog.md` — **what happened in previous sessions and what is next**
- `src/idle_agent/pipeline.py` — the actual end-to-end loop

## What is built vs designed

**Built** (`src/idle_agent/`): video ingest, YOLOv8-pose + ByteTrack detection,
motion scoring, sticky primary-occupant tracking, pose behaviour signals, the
state machine, and local output (`output/events.jsonl`, `output/evidence/*.jpg`,
`output/preview.mp4`).

**Designed only** — described in `docs/` and `config/` but with no code yet:
ERP HTTPS adapter, Redis Streams queue, PostgreSQL audit store, FastAPI health
endpoint, the shift/break/holiday calendar (`BREAK` state), `zone_overrides`,
multi-camera loading from `cameras.yaml`, optical-flow motion, main-stream
snapshots. Do not assume these work — check the code before citing them.

## Known bugs (verified, not yet fixed)

1. **Orphan AWAY_ENDED.** An occupant who is IDLE, leaves for more than
   `debounce_leave_seconds` but less than `away_confirm_seconds`, and returns
   produces `IDLE_ENDED`, an `AWAY_ENDED` whose `AWAY_STARTED` was never
   emitted, and an immediate `IDLE_STARTED` with no confirm period.
   See `state_machine.py` lines ~201-217 and ~275-282.
2. **1970 timestamps.** Without `--clip-start`, `clip_start` defaults to the
   Unix epoch, so every `started_at` is `1970-01-01`. Live RTSP has the same
   problem because nothing reads the wall clock.
3. **Shifts and breaks ignored.** `config/idle_rules.yaml` defines shifts,
   breaks and weekly off, and `load_rules` sets `rules["ignore_shifts"]`, but no
   code reads any of it. Alerts fire during lunch.
4. **Motion window is frames, not seconds.** `motion_window_seconds: 3` becomes
   a deque of 3 samples (~0.4 s at 8 FPS). Unverified consequence: the
   `idle_threshold` of 0.08 may be far above any real per-frame score, which
   would mean `ACTIVE` arrives only via the wrist-in-work-polygon override.
   Check the `m=` values in `preview.mp4` against real footage before tuning.
5. **No RTSP reconnect.** A dropped stream ends the run. `Detector._prev_keypoints`
   grows without bound over a long session.
6. **Primary-track grace side effects.** `lost_grace_seconds: 60` keeps the last
   detection alive, so a departed operator can count as working for 60 s and
   `AWAY_STARTED` arrives ~60 s late. `assign_dwell_seconds: 0.5` lets a
   passer-by become the primary and reset the away timer.

## Rules

- **Never commit** `recordings/`, `output/`, `*.pt`, or any token or key. These
  are gitignored; keep it that way.
- **Calibration notes go in `docs/calibration/`**, not `recordings/calibration/`
  (that path is gitignored, so notes written there are lost with the instance).
- **Paths come from environment variables**, never hardcoded. See `.env.example`.
- **Branch, then PR.** Never commit to `main` or push to it directly. One
  logical change per branch: `fix/...`, `feat/...`, `chore/...`, `docs/...`.
- **Tests before the GPU.** `pytest -q` runs with no GPU and no torch. Run it
  after every change to `state_machine.py`, `zones.py` or `behaviors.py`.
- **Always pass `--clip-start`** when running a recording, or the events carry
  1970 timestamps.
- **Save every run**: `bash scripts/vast/save_run.sh` before the instance dies.
- **End every session** by updating `docs/devlog.md` and running
  `bash scripts/vast/end_session.sh`.
- Do not print thousands of log lines into the conversation. Summarise:
  event counts by type, and the first and last event.

## Commands

```bash
# setup (idempotent; safe to re-run)
bash scripts/vast/bootstrap.sh

# unit tests (no GPU, no torch)
pytest -q

# CPU smoke test, ~15 s
PYTHONPATH=src python -m idle_agent --source file --device cpu \
  --max-frames 120 --target-fps 4

# full clip on GPU
PYTHONPATH=src python -m idle_agent --source file --camera-id cam-01 \
  --device cuda:0 --target-fps 8 --preview-scale 0.5 \
  --clip-start "2026-11-18T15:00:05+05:00"

# live RTSP (needs LAN access to the camera; a cloud GPU cannot reach a private IP)
PYTHONPATH=src python -m idle_agent --source rtsp \
  --url "rtsp://USER:PASS@HOST:554/Streaming/Channels/102" --camera-id cam-01 \
  --clip-start "$(date --iso-8601=seconds)"

# save outputs to the bucket, then check it is safe to destroy the instance
bash scripts/vast/save_run.sh
bash scripts/vast/end_session.sh
```

## Event counts are the measure

When judging a change, compare event counts per type before and after, not the
preview video. A fix that removes a spurious `AWAY_ENDED` should show exactly
that in `output/events.jsonl`.
