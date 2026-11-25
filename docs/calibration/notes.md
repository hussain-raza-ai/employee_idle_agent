# Calibration notes

Thresholds set from real footage, not guesses. This file is committed on
purpose: `recordings/calibration/` is gitignored, so notes written there vanish
with the instance.

`docs/pilot-recordings.md` describes which clips to collect and the procedure.

## How to read a motion score

Run a clip and watch the `m=` number drawn next to each person in
`output/preview.mp4`:

```bash
PYTHONPATH=src python -m idle_agent --source file --camera-id cam-01 \
  --device cuda:0 --target-fps 8 --preview-scale 0.5 \
  --clip-start "2026-11-18T15:00:05+05:00"
```

`motion_score` is the mean per-frame keypoint displacement divided by the frame
diagonal, so it is a small number and it scales with the sampling rate. Note the
`--target-fps` you used: the same person sampled at 4 FPS moves roughly twice as
far between samples as at 8 FPS, so a threshold tuned at one rate does not carry
to the other.

## Observations

Fill one row per clip. `motion p50`/`p90` are the values seen while the operator
was doing that thing.

| Date | Clip | Camera / zone | FPS | Scenario | motion p50 | motion p90 | Notes |
|------|------|---------------|-----|----------|-----------|-----------|-------|
|      |      |               |     |          |           |           | _not yet measured_ |

## Threshold decisions

| Parameter | Default | Chosen | Evidence |
|-----------|---------|--------|----------|
| `motion.idle_threshold` | 0.08 | — | — |
| `motion.active_threshold` | 0.12 | — | — |
| `thresholds.idle_confirm_seconds` | 180 | — | — |
| `thresholds.away_confirm_seconds` | 300 | — | — |
| `behaviors.phone.min_score` | 0.40 | — | — |
| `behaviors.interacting.max_center_dist` | 0.16 | — | — |
| `primary_track.lost_grace_seconds` | 60 | — | — |
| `primary_track.assign_dwell_seconds` | 0.5 | — | — |

The defaults above are untested against footage. Two of them are open questions
rather than numbers to nudge:

- **`idle_threshold` may be unreachable.** If real per-frame scores sit far
  below 0.08, every frame counts as low motion and `ACTIVE` arrives only through
  the wrist-in-work-polygon override. Measure before tuning.
- **`interacting` at a service counter.** Talking to a customer is the job here,
  and while `interacting` is true the work-polygon override is disabled, so a
  mostly still operator can start counting toward IDLE. Decide from footage
  whether to disable the signal for counter zones or restrict it to staff.

## False positives seen

| Date | Event | Clip time | What was really happening | Fix |
|------|-------|-----------|---------------------------|-----|
|      |       |           |                           |     |
