# Idle Rules — Finalized Defaults

Config: [`config/idle_rules.yaml`](../config/idle_rules.yaml)

## States

| State | Meaning |
|-------|---------|
| `ACTIVE` | Person in zone AND motion ≥ `active_threshold` |
| `IDLE` | Person in zone AND motion ≤ `idle_threshold` for `idle_confirm_seconds` |
| `AWAY` | No person in zone for `away_confirm_seconds` during shift |
| `BREAK` | Outside shift, weekly off, holiday, or approved break — **no alerts** |

## Final thresholds (Phase 1)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Inference evaluation tick | 1 s | Stable state decisions |
| Motion window | 3 s | Smooth pose/flow noise |
| `idle_threshold` | 0.08 | Low joint displacement = idle |
| `active_threshold` | 0.12 | Hysteresis vs idle |
| `idle_confirm_seconds` | **180** (3 min) | Avoid chatter from brief pauses |
| `away_confirm_seconds` | **300** (5 min) | Short absences (washroom) ignored |
| `escalate_seconds` | **900** (15 min) | Supervisor escalation |
| `debounce_leave_seconds` | 5 | Ignore detection flicker |
| `end_grace_seconds` | 10 | Require sustained resume before END event |

## Shift & breaks (default)

- **Shift:** Mon–Sat 08:00–17:00 (`Asia/Karachi`)
- **Breaks:** 10:30–10:45, 13:00–13:45, 15:30–15:45
- **Weekly off:** Sunday
- **Holidays:** `holidays.dates` list, e.g. `["2026-12-25"]`
- Adjust in `config/idle_rules.yaml` to match ERP / HR schedule

What BREAK does (`src/idle_agent/shifts.py`, `state_machine.py`):

- Going off duty closes every open episode that had a `*_STARTED` — IDLE, a
  confirmed AWAY, PHONE, INTERACTING, OFF_SEAT, NOT_WORKING — with its `*_ENDED`
  at that moment. Unconfirmed candidates are dropped, so every `*_ENDED` still
  has a matching `*_STARTED`.
- Nothing is raised while off duty.
- Back on duty, the zone restarts from UNKNOWN: an idle or empty desk needs the
  full `idle_confirm_seconds` / `away_confirm_seconds` again, counted from the
  end of the break.
- A shift whose end is not after its start runs past midnight, and the hours
  after midnight count as the day it started.
- `ignore_shifts: true` (set in `demo_overrides.yaml`) turns the calendar off,
  so a recording is judged regardless of when it was made.

Example: idle from 12:50 → `IDLE_STARTED` at 12:53 → lunch at 13:00 closes it
with `IDLE_ENDED` (≈600 s) → nothing until 13:45 → still idle → new
`IDLE_STARTED` at 13:48, with `started_at` 13:45.

## Event timeline example

1. 10:00:00 — Worker stops moving → internal candidate IDLE  
2. 10:03:00 — Confirm → emit `IDLE_STARTED`  
3. 10:18:00 — Still idle → emit `IDLE_ESCALATED`  
4. 10:20:00 — Motion resumes 10s → emit `IDLE_ENDED` (duration ≈ 1200s)

## Policy

Phase 1 = **alert + supervisor review** only (`auto_discipline: false`).
