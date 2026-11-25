# Devlog

A Vast.ai instance is destroyed at the end of each session, and the Claude Code
conversation goes with it. This file is how the next session picks up where the
last one stopped. Newest entry first. One entry per working session.

Keep an entry to a few lines: what changed, what the numbers were, what is next.
Detail belongs in the PR description, which stays on GitHub.

---

## Next up

These need the GPU and real footage, so they belong on a Vast session.

1. **First real run.** Full cam-01 clip on the GPU. Compare the event counts
   with the run before these fixes (`save_run.sh` manifests in the bucket):
   expect fewer `AWAY_ENDED` (no orphans) and real 2026 timestamps.
2. **Calibrate the motion threshold** (CLAUDE.md bug 4). Read the `m=` values
   off `preview.mp4` for active work, still-at-desk and empty, and record the
   real range in `docs/calibration/notes.md`. Only then decide whether
   `idle_threshold: 0.08` means anything.
3. **Decide the counter-desk interacting policy.** At a service counter,
   talking to a customer is the job, and `interacting=True` switches off the
   wrist-in-work-polygon override. Measure it on real footage first.
4. **Primary-track grace and dwell** (bug 6). Measure how often a passer-by
   takes over the desk and how late `AWAY_STARTED` arrives with the 60 s grace.

CPU-only work that can be done anywhere: RTSP reconnect (bug 5), the ERP
adapter, `zone_overrides`.

## 2026-11-25 — three state-machine bugs fixed (CPU, no GPU run)

- **Orphan AWAY_ENDED:** a short absence from IDLE no longer emits an
  `AWAY_ENDED` without `AWAY_STARTED`, and a returning occupant serves a full
  idle confirm period. `IDLE_ENDED` is stamped when the occupant left.
- **1970 timestamps:** new `clock.py`. Recordings take `--clip-start` or the NVR
  file name, else the CLI stops before loading the model. Live RTSP anchors to
  the wall clock when the stream opens. Times are in the site timezone.
  `tzdata` added (Windows needs it).
- **Shift calendar:** new `shifts.py` and a `BREAK` state. Off duty closes open
  episodes with their `*_ENDED` and raises nothing; back on duty starts fresh.
  Demo overrides keep it off, so default recording runs are unchanged.
- Tests: 95 passing, no xfail. End-to-end pipeline run with a fake detector
  over a 12:58 clip with production rules: `NOT_WORKING` closed at 13:00,
  nothing during lunch, preview shows `BREAK break:lunch` in grey.

## 2026-11-25 — dev workflow setup

- Added `CLAUDE.md` (project rules, built-vs-designed, the six known bugs),
  `scripts/vast/{bootstrap,save_run,end_session}.sh`, `.claude/settings.json`,
  `.env.example`, a CPU test suite, and CPU-only CI.
- Replaced the hardcoded `/root/video` and `/workspace` paths in
  `remote_run_cam01.sh`, `remote_run_full_cam01.sh` and `diag_primary.py` with
  environment variables, so a script works on any instance.
- Moved calibration notes to `docs/calibration/` — the old path
  `recordings/calibration/` is gitignored, so anything written there died with
  the instance.
- Deleted `scripts/primary.py` (a stale copy of `src/idle_agent/primary.py`,
  missing the `seat_norm` zone test) and the duplicate root `diag_primary.py`
  (its `parents[1]` path was wrong).
- Tests: 34 passing, 2 `xfail` marking bugs 1 and 2. No GPU run this session.
