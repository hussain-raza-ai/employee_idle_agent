# Devlog

A Vast.ai instance is destroyed at the end of each session, and the Claude Code
conversation goes with it. This file is how the next session picks up where the
last one stopped. Newest entry first. One entry per working session.

Keep an entry to a few lines: what changed, what the numbers were, what is next.
Detail belongs in the PR description, which stays on GitHub.

---

## Next up

1. **Fix the orphan `AWAY_ENDED`** (CLAUDE.md bug 1). The regression test is
   already written: remove the `xfail` from
   `tests/test_state_machine.py::test_short_absence_from_idle_is_clean` and make
   it pass. A short absence from IDLE must not invent an AWAY episode, and the
   returning occupant must serve the full idle confirm period again.
2. **Fix the 1970 timestamps** (bug 2). `clip_start` should default to the wall
   clock for a live RTSP source, and the CLI should refuse a file source with no
   `--clip-start` rather than silently dating events to the epoch. Test:
   `test_timestamps_are_not_epoch_without_clip_start`.
3. **Calibrate the motion threshold** (bug 4). Run the full cam-01 clip on the
   GPU, read the `m=` values off `preview.mp4`, and record the real range in
   `docs/calibration/notes.md`. Only then decide whether `idle_threshold: 0.08`
   means anything.
4. **Decide the counter-desk interacting policy** (see the repo review). At a
   service counter, talking to a customer is the job, and `interacting=True`
   currently switches off the wrist-in-work-polygon override. Measure it on real
   footage before changing a threshold.
5. **Implement the shift and break calendar** (bug 3), so no alerts fire during
   lunch or on a weekly off.

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
