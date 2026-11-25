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
state machine, the shift/break/holiday calendar (`shifts.py`, `BREAK` state),
wall-clock handling (`clock.py`), and local output (`output/events.jsonl`,
`output/evidence/*.jpg`, `output/preview.mp4`).

**Designed only** — described in `docs/` and `config/` but with no code yet:
ERP HTTPS adapter, Redis Streams queue, PostgreSQL audit store, FastAPI health
endpoint, `zone_overrides`, multi-camera loading from `cameras.yaml`,
optical-flow motion, main-stream snapshots. Do not assume these work — check
the code before citing them.

## How time works

- Event times are wall-clock times in the site timezone (`timezone:` in
  `idle_rules.yaml`). Nothing falls back to 1970.
- Recording: `--clip-start` if given; else the start is read from an NVR-style
  file name (`…_20261118150005_….mp4`); else the CLI stops and asks for it.
- Live RTSP: t=0 is the moment the stream opens; frame times come from a
  monotonic clock, not frame count.
- The shift calendar uses that wall-clock time. `demo_overrides.yaml` sets
  `ignore_shifts: true`, so the default CLI run on a recording ignores shifts.
  Pass `--demo-overrides ""` to run with the production calendar.

## Known bugs (verified, not yet fixed)

Fixed so far: orphan `AWAY_ENDED` after a short absence, 1970 timestamps, and
the ignored shift calendar (see `docs/devlog.md`). Their tests are in `tests/`.

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
- **Pass `--clip-start`** for any recording whose file name is not an NVR
  export; the CLI refuses to guess.
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
  --max-frames 120 --target-fps 4 --clip-start "2026-11-18T15:00:05+05:00"

# same clip with the production shift calendar instead of demo overrides
PYTHONPATH=src python -m idle_agent --source file --demo-overrides "" \
  --clip-start "2026-11-18T15:00:05+05:00"

# full clip on GPU
PYTHONPATH=src python -m idle_agent --source file --camera-id cam-01 \
  --device cuda:0 --target-fps 8 --preview-scale 0.5 \
  --clip-start "2026-11-18T15:00:05+05:00"

# live RTSP (needs LAN access to the camera; a cloud GPU cannot reach a private IP)
# t=0 is anchored to the wall clock when the stream opens; no --clip-start needed.
PYTHONPATH=src python -m idle_agent --source rtsp \
  --url "rtsp://USER:PASS@HOST:554/Streaming/Channels/102" --camera-id cam-01 \
  --no-preview

# save outputs to the bucket, then check it is safe to destroy the instance
bash scripts/vast/save_run.sh
bash scripts/vast/end_session.sh
```

## Event counts are the measure

When judging a change, compare event counts per type before and after, not the
preview video. A fix that removes a spurious `AWAY_ENDED` should show exactly
that in `output/events.jsonl`.
