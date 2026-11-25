"""State machine behaviour, driven by synthetic signals — no GPU, no torch.

Each test feeds the machine a timeline of (duration, occupied, motion, signals)
at a fixed tick rate and asserts on the events that come out. Tests marked
xfail document bugs listed in CLAUDE.md; when one is fixed its marker goes away
and the assertion stands as the regression test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from idle_agent.state_machine import ZoneStateMachine, load_rules

REPO = Path(__file__).resolve().parents[1]
ZONE = "ws-counter-1"
FPS = 8.0


def _signals(*, seat=True, working=False, phone=0.0, interacting=False, hands=True):
    """One tick of BehaviorScorer output."""
    return SimpleNamespace(
        seat_occupied=seat,
        phone_score=phone,
        phone=phone >= 0.40,
        hands_known=hands,
        working=working,
        interacting=interacting,
        interaction_track_id=None,
        interaction_dist=0.0,
    )


SEATED_IDLE = _signals(working=False)  # hands visible, off the keyboard
TYPING = _signals(working=True)  # a wrist inside the work polygon
LOW_MOTION = 0.004  # a still seated person, well under idle_threshold

# A Wednesday morning inside the configured shift and clear of every break, so
# timelines of up to ~80 minutes never touch the shift calendar.
MONITORED_START = datetime(2026, 11, 18, 9, 0, 0, tzinfo=timezone(timedelta(hours=5)))


@pytest.fixture(scope="module")
def rules():
    return load_rules(REPO / "config" / "idle_rules.yaml")


def run_timeline(rules, timeline, clip_start=MONITORED_START):
    """Feed the machine a timeline; return the emitted events in order."""
    sm = ZoneStateMachine("cam-01", [ZONE], rules, clip_start=clip_start)
    events = []
    t = 0.0
    for duration, occupied, motion, signals in timeline:
        end = t + duration
        while t < end:
            events.extend(
                sm.update(
                    ZONE,
                    t,
                    occupied,
                    motion,
                    "t-1" if occupied else None,
                    0.9,
                    signals,
                )
            )
            t += 1.0 / FPS
    return events, sm.states_snapshot()[ZONE]


def types_of(events):
    return [e.event_type for e in events]


# --- the wrist-in-work-polygon override -------------------------------------


def test_typing_never_goes_idle(rules):
    """Low joint motion plus a wrist on the keyboard must stay ACTIVE.

    This is the override in state_machine.update: it is what keeps a typing
    operator from being reported as idle.
    """
    events, state = run_timeline(rules, [(600, True, LOW_MOTION, TYPING)])
    assert types_of(events) == []
    assert state == "ACTIVE"


def test_still_with_hands_off_keyboard_goes_idle(rules):
    """Same tiny motion, but hands away from the work polygon → IDLE."""
    events, state = run_timeline(rules, [(240, True, LOW_MOTION, SEATED_IDLE)])
    assert state == "IDLE"
    assert "IDLE_STARTED" in types_of(events)
    assert "NOT_WORKING_STARTED" in types_of(events)


def test_idle_confirm_waits_the_full_threshold(rules):
    """IDLE_STARTED must not arrive before idle_confirm_seconds."""
    confirm = float(rules["thresholds"]["idle_confirm_seconds"])
    events, _ = run_timeline(rules, [(confirm - 20, True, LOW_MOTION, SEATED_IDLE)])
    assert "IDLE_STARTED" not in types_of(events)


# --- away ------------------------------------------------------------------


def test_away_started_after_confirm(rules):
    """An empty zone past away_confirm_seconds emits AWAY_STARTED exactly once."""
    confirm = float(rules["thresholds"]["away_confirm_seconds"])
    events, state = run_timeline(
        rules,
        [(30, True, LOW_MOTION, TYPING), (confirm + 60, False, 0.0, None)],
    )
    assert state == "AWAY"
    assert types_of(events).count("AWAY_STARTED") == 1


def test_brief_dropout_does_not_emit_away(rules):
    """A dropout shorter than debounce_leave_seconds emits nothing."""
    debounce = float(rules["evaluation"]["debounce_leave_seconds"])
    events, _ = run_timeline(
        rules,
        [
            (30, True, LOW_MOTION, TYPING),
            (debounce - 2, False, 0.0, None),
            (30, True, LOW_MOTION, TYPING),
        ],
    )
    assert "AWAY_STARTED" not in types_of(events)
    assert "AWAY_ENDED" not in types_of(events)


def test_away_ends_when_occupant_returns(rules):
    """A real AWAY episode closes with AWAY_ENDED when someone comes back."""
    confirm = float(rules["thresholds"]["away_confirm_seconds"])
    events, state = run_timeline(
        rules,
        [
            (30, True, LOW_MOTION, TYPING),
            (confirm + 60, False, 0.0, None),
            (60, True, LOW_MOTION, TYPING),
        ],
    )
    assert state == "ACTIVE"
    assert types_of(events).count("AWAY_STARTED") == 1
    assert types_of(events).count("AWAY_ENDED") == 1


# --- leaving and returning ---------------------------------------------------


def test_short_absence_from_idle_is_clean(rules):
    """IDLE → leave briefly → return still.

    Correct behaviour: IDLE_ENDED, then the idle confirm timer restarts from
    scratch. No AWAY_* at all, because the absence never reached
    away_confirm_seconds.
    """
    confirm = float(rules["thresholds"]["idle_confirm_seconds"])
    events, _ = run_timeline(
        rules,
        [
            (confirm + 60, True, LOW_MOTION, SEATED_IDLE),
            (30, False, 0.0, None),
            (20, True, LOW_MOTION, SEATED_IDLE),
        ],
    )
    names = types_of(events)
    assert "AWAY_ENDED" not in names, "AWAY_ENDED without a matching AWAY_STARTED"
    assert "AWAY_STARTED" not in names
    assert names.count("IDLE_STARTED") == 1, "IDLE restarted with no confirm period"
    assert names.count("IDLE_ENDED") == 1


def test_returning_occupant_serves_a_fresh_idle_confirm(rules):
    """After a short absence, IDLE comes back only after the full confirm period."""
    confirm = float(rules["thresholds"]["idle_confirm_seconds"])
    events, state = run_timeline(
        rules,
        [
            (confirm + 60, True, LOW_MOTION, SEATED_IDLE),
            (30, False, 0.0, None),
            (confirm + 20, True, LOW_MOTION, SEATED_IDLE),
        ],
    )
    idle_starts = [e for e in events if e.event_type == "IDLE_STARTED"]
    assert len(idle_starts) == 2
    assert state == "IDLE"
    # The second episode starts when the occupant came back, and is announced a
    # full confirm period later — not on the first frame back.
    second = idle_starts[1]
    assert second.duration_seconds >= confirm


def test_idle_ends_when_the_occupant_left(rules):
    """IDLE_ENDED is stamped at the moment of leaving, not after the debounce."""
    from datetime import datetime

    confirm = float(rules["thresholds"]["idle_confirm_seconds"])
    stay = confirm + 60
    events, _ = run_timeline(
        rules,
        [(stay, True, LOW_MOTION, SEATED_IDLE), (30, False, 0.0, None)],
    )
    ended = next(e for e in events if e.event_type == "IDLE_ENDED")
    left_at = MONITORED_START.timestamp() + stay
    ended_at = datetime.fromisoformat(ended.ended_at).timestamp()
    assert abs(ended_at - left_at) <= 1.0 / FPS + 1e-6


def test_return_from_real_away_ends_it_then_waits_to_judge(rules):
    """A confirmed AWAY closes on return; the occupant is UNKNOWN, not IDLE."""
    confirm = float(rules["thresholds"]["away_confirm_seconds"])
    events, state = run_timeline(
        rules,
        [
            (30, True, LOW_MOTION, TYPING),
            (confirm + 60, False, 0.0, None),
            (20, True, LOW_MOTION, SEATED_IDLE),
        ],
    )
    names = types_of(events)
    assert names.count("AWAY_STARTED") == 1
    assert names.count("AWAY_ENDED") == 1
    assert "IDLE_STARTED" not in names, "IDLE must wait a full confirm period"
    assert state == "UNKNOWN"


def _assert_episodes_pair(events):
    """No *_ENDED without an open *_STARTED of the same kind."""
    open_episodes: set[str] = set()
    for name in types_of(events):
        prefix, _, suffix = name.rpartition("_")
        if suffix == "STARTED":
            open_episodes.add(prefix)
        elif suffix == "ENDED":
            assert prefix in open_episodes, f"{name} with no {prefix}_STARTED"
            open_episodes.discard(prefix)


@pytest.mark.parametrize("absence", [6, 30, 120, 290, 320, 900])
def test_every_ended_event_has_a_matching_started(rules, absence):
    """Idle, leave for various lengths, come back: episodes always pair up."""
    confirm = float(rules["thresholds"]["idle_confirm_seconds"])
    events, _ = run_timeline(
        rules,
        [
            (confirm + 60, True, LOW_MOTION, SEATED_IDLE),
            (absence, False, 0.0, None),
            (confirm + 30, True, LOW_MOTION, SEATED_IDLE),
            (60, True, LOW_MOTION, TYPING),
        ],
    )
    _assert_episodes_pair(events)


# --- behaviour flags -------------------------------------------------------


def test_phone_confirm_and_end(rules):
    """A phone episode opens after its confirm window and closes after grace."""
    phone_cfg = rules["behaviors"]["phone"]
    confirm = float(phone_cfg["confirm_seconds"])
    events, _ = run_timeline(
        rules,
        [
            (confirm + 10, True, LOW_MOTION, _signals(phone=0.8)),
            (60, True, LOW_MOTION, TYPING),
        ],
    )
    names = types_of(events)
    assert names.count("PHONE_STARTED") == 1
    assert names.count("PHONE_ENDED") == 1


def test_phone_below_min_score_does_not_trigger(rules):
    """A score under min_score must never open an episode."""
    confirm = float(rules["behaviors"]["phone"]["confirm_seconds"])
    events, _ = run_timeline(
        rules, [(confirm + 60, True, LOW_MOTION, _signals(phone=0.30))]
    )
    assert "PHONE_STARTED" not in types_of(events)


def test_off_seat_when_hips_leave_the_seat_polygon(rules):
    """Standing inside the workstation but off the chair → OFF_SEAT."""
    confirm = float(rules["behaviors"]["off_seat"]["confirm_seconds"])
    events, _ = run_timeline(
        rules,
        [(confirm + 10, True, LOW_MOTION, _signals(seat=False, working=False))],
    )
    assert "OFF_SEAT_STARTED" in types_of(events)


def test_unknown_hands_are_not_counted_as_not_working(rules):
    """hands_known=False means 'cannot tell', which must not become an event."""
    confirm = float(rules["behaviors"]["not_working"]["confirm_seconds"])
    events, _ = run_timeline(
        rules,
        [(confirm + 60, True, LOW_MOTION, _signals(hands=False, working=False))],
    )
    assert "NOT_WORKING_STARTED" not in types_of(events)


def test_escalation_fires_once(rules):
    """A long idle episode escalates exactly once."""
    escalate = float(rules["thresholds"]["escalate_seconds"])
    events, _ = run_timeline(
        rules, [(escalate + 120, True, LOW_MOTION, SEATED_IDLE)]
    )
    assert types_of(events).count("IDLE_ESCALATED") == 1


# --- event payload ---------------------------------------------------------


def test_event_dict_has_the_schema_required_fields(rules):
    """Every emitted event must carry the fields the JSON Schema requires."""
    required = {
        "event_id",
        "event_type",
        "camera_id",
        "zone_id",
        "started_at",
        "duration_seconds",
        "confidence",
        "idempotency_key",
    }
    events, _ = run_timeline(rules, [(240, True, LOW_MOTION, SEATED_IDLE)])
    assert events, "expected at least one event"
    for ev in events:
        missing = required - ev.to_dict().keys()
        assert not missing, f"{ev.event_type} missing {missing}"


def test_idempotency_key_is_built_from_identity_and_start(rules):
    events, _ = run_timeline(rules, [(240, True, LOW_MOTION, SEATED_IDLE)])
    ev = events[0].to_dict()
    assert ev["idempotency_key"] == (
        f"{ev['camera_id']}:{ev['zone_id']}:{ev['event_type']}:{ev['started_at']}"
    )


# --- bug 2 in CLAUDE.md: 1970 timestamps -----------------------------------


@pytest.mark.xfail(
    reason="CLAUDE.md bug 2: without clip_start, started_at falls back to the "
    "Unix epoch instead of the wall clock",
    strict=True,
)
def test_timestamps_are_not_epoch_without_clip_start(rules):
    sm = ZoneStateMachine("cam-01", [ZONE], rules)
    assert not sm._iso(0).startswith("1970"), "epoch timestamp"


def test_clip_start_anchors_timestamps(rules):
    """With clip_start given, video time maps onto real wall-clock time."""
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 11, 18, 15, 0, 5, tzinfo=timezone(timedelta(hours=5)))
    events, _ = run_timeline(
        rules, [(240, True, LOW_MOTION, SEATED_IDLE)], clip_start=start
    )
    assert events[0].started_at.startswith("2026-11-18T15:0")


# --- config loading --------------------------------------------------------


def test_demo_overrides_merge_over_production_rules():
    merged = load_rules(
        REPO / "config" / "idle_rules.yaml", REPO / "config" / "demo_overrides.yaml"
    )
    base = load_rules(REPO / "config" / "idle_rules.yaml")
    # The demo file shortens the primary-track grace; the production shift
    # calendar must survive the merge.
    assert merged["primary_track"]["lost_grace_seconds"] == 60
    assert merged["shifts"] == base["shifts"]
    assert merged["ignore_shifts"] is True
