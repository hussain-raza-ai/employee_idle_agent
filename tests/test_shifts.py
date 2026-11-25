"""Shift calendar and the BREAK state — no GPU, no torch."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from idle_agent import clock
from idle_agent.shifts import ShiftCalendar
from idle_agent.state_machine import ZoneStateMachine, load_rules
from test_state_machine import (
    FPS,
    LOW_MOTION,
    SEATED_IDLE,
    TYPING,
    ZONE,
    _assert_episodes_pair,
    _signals,
    types_of,
)

REPO = Path(__file__).resolve().parents[1]
PKT = timezone(timedelta(hours=5))
TZ = clock.site_tz("Asia/Karachi")


def at(y, mo, d, h, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=PKT)


# 2026-11-18 is a Wednesday, 2026-11-21 a Saturday, 2026-11-22 a Sunday.
WED, SAT, SUN = (2026, 11, 18), (2026, 11, 21), (2026, 11, 22)


@pytest.fixture(scope="module")
def rules():
    return load_rules(REPO / "config" / "idle_rules.yaml")


@pytest.fixture(scope="module")
def cal(rules):
    return ShiftCalendar.from_rules(rules, TZ)


# --- the calendar from config/idle_rules.yaml --------------------------------


@pytest.mark.parametrize(
    "when,expected",
    [
        (at(*WED, 9), (True, "shift:morning")),
        (at(*WED, 8, 0), (True, "shift:morning")),  # start is inclusive
        (at(*WED, 7, 59), (False, "outside_shift")),
        (at(*WED, 17, 0), (False, "outside_shift")),  # end is exclusive
        (at(*WED, 10, 30), (False, "break:tea-morning")),
        (at(*WED, 10, 45), (True, "shift:morning")),  # break end is exclusive
        (at(*WED, 13, 20), (False, "break:lunch")),
        (at(*WED, 15, 40), (False, "break:tea-afternoon")),
        (at(*SAT, 11), (True, "shift:morning")),
        (at(*SUN, 11), (False, "weekly_off")),
        (at(*WED, 23), (False, "outside_shift")),
    ],
)
def test_configured_calendar(cal, when, expected):
    assert cal.status(when) == expected


def test_status_converts_from_utc(cal):
    """04:00 UTC is 09:00 in Karachi: in shift."""
    assert cal.status(datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc))[0] is True


def test_ignore_shifts_turns_the_calendar_off(rules):
    cal = ShiftCalendar.from_rules({**rules, "ignore_shifts": True}, TZ)
    assert cal.status(at(*SUN, 3)) == (True, "calendar_off")


def test_demo_overrides_turn_the_calendar_off():
    rules = load_rules(
        REPO / "config" / "idle_rules.yaml", REPO / "config" / "demo_overrides.yaml"
    )
    assert ShiftCalendar.from_rules(rules, TZ).enabled is False


# --- calendar edge cases -----------------------------------------------------


def _cal(**extra):
    base = {
        "shifts": [{"id": "day", "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
                    "start": "08:00", "end": "17:00"}],
        "breaks": [],
        "holidays": {"weekly_off": ["sun"], "dates": []},
    }
    base.update(extra)
    return ShiftCalendar.from_rules(base, TZ)


def test_holiday_date_is_off():
    cal = _cal(holidays={"weekly_off": ["sun"], "dates": ["2026-11-18"]})
    assert cal.status(at(*WED, 9)) == (False, "holiday")
    assert cal.status(at(2026, 11, 19, 9)) == (True, "shift:day")


def test_unquoted_yaml_dates_are_accepted():
    """YAML turns an unquoted 2026-11-18 into a date object."""
    cal = _cal(holidays={"weekly_off": [], "dates": [date(2026, 11, 18)]})
    assert cal.status(at(*WED, 9)) == (False, "holiday")


def test_holiday_list_layout_is_accepted():
    cal = _cal(holidays=["2026-11-18"], weekly_off=["sun"])
    assert cal.status(at(*WED, 9)) == (False, "holiday")
    assert cal.status(at(*SUN, 9))[0] is False


def test_overnight_shift_after_midnight_belongs_to_the_start_day():
    """A Saturday 17:00-01:00 shift still runs at 00:30 on Sunday (weekly off)."""
    cal = _cal(
        shifts=[{"id": "evening", "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
                 "start": "17:00", "end": "01:00"}]
    )
    assert cal.status(at(*SAT, 23)) == (True, "shift:evening")
    assert cal.status(at(*SUN, 0, 30)) == (True, "shift:evening")
    assert cal.status(at(*SUN, 1, 0)) == (False, "weekly_off")
    assert cal.status(at(*SUN, 20)) == (False, "weekly_off")  # no Sunday shift


def test_overnight_break_crossing_midnight():
    cal = _cal(
        shifts=[{"id": "night", "start": "20:00", "end": "06:00"}],
        breaks=[{"id": "midnight-meal", "start": "23:45", "end": "00:15"}],
        holidays={"weekly_off": [], "dates": []},
    )
    assert cal.status(at(*WED, 23, 50)) == (False, "break:midnight-meal")
    assert cal.status(at(2026, 11, 19, 0, 10)) == (False, "break:midnight-meal")
    assert cal.status(at(2026, 11, 19, 0, 20)) == (True, "shift:night")


def test_no_shifts_configured_means_all_day():
    cal = _cal(shifts=[])
    assert cal.status(at(*WED, 3)) == (True, "shift:all_day")
    assert cal.status(at(*SUN, 3)) == (False, "weekly_off")


@pytest.mark.parametrize(
    "bad,match",
    [
        ({"shifts": [{"start": "8am", "end": "17:00"}]}, "HH:MM"),
        ({"shifts": [{"days": ["funday"], "start": "08:00", "end": "17:00"}]}, "unknown day"),
        ({"holidays": {"dates": ["25/12/2026"]}}, "YYYY-MM-DD"),
    ],
)
def test_bad_config_fails_loudly(bad, match):
    with pytest.raises(ValueError, match=match):
        _cal(**bad)


def test_describe_mentions_breaks_and_days_off(cal):
    text = cal.describe()
    assert "lunch 13:00-13:45" in text
    assert "sun" in text


# --- the BREAK state in the state machine ------------------------------------


def run_at(rules, start, timeline):
    sm = ZoneStateMachine("cam-01", [ZONE], rules, clip_start=start)
    events, states = [], []
    t = 0.0
    for duration, occupied, motion, signals in timeline:
        end = t + duration
        while t < end:
            events.extend(
                sm.update(ZONE, t, occupied, motion, "t-1" if occupied else None, 0.9, signals)
            )
            states.append(sm.states_snapshot()[ZONE])
            t += 1.0 / FPS
    return events, states, sm


def test_idle_running_into_lunch_ends_at_lunch(rules):
    """Idle from 12:50; lunch at 13:00 closes the episode, nothing during lunch."""
    events, states, _ = run_at(
        rules, at(*WED, 12, 50), [(30 * 60, True, LOW_MOTION, SEATED_IDLE)]
    )
    names = types_of(events)
    assert names.count("IDLE_STARTED") == 1
    assert names.count("IDLE_ENDED") == 1
    ended = next(e for e in events if e.event_type == "IDLE_ENDED")
    assert ended.ended_at.startswith("2026-11-18T13:00:00")
    assert "BREAK" in states
    _assert_episodes_pair(events)


def test_nothing_is_raised_during_a_break(rules):
    """A whole lunch hour with an empty desk: no AWAY at all."""
    events, states, sm = run_at(rules, at(*WED, 13, 0), [(44 * 60, False, 0.0, None)])
    assert events == []
    assert set(states) == {"BREAK"}
    assert sm.behavior_labels()[ZONE] == ["break:lunch"]


def test_leaving_for_lunch_early_does_not_count_as_away(rules):
    """Leave at 12:58, lunch starts 13:00: the absence never reaches AWAY."""
    events, _, _ = run_at(
        rules,
        at(*WED, 12, 50),
        [(8 * 60, True, LOW_MOTION, TYPING), (50 * 60, False, 0.0, None)],
    )
    assert "AWAY_STARTED" not in types_of(events)


def test_confirmed_away_is_closed_when_the_break_starts(rules):
    events, _, _ = run_at(
        rules,
        at(*WED, 12, 40),
        [(60, True, LOW_MOTION, TYPING), (25 * 60, False, 0.0, None)],
    )
    names = types_of(events)
    assert names.count("AWAY_STARTED") == 1
    assert names.count("AWAY_ENDED") == 1
    ended = next(e for e in events if e.event_type == "AWAY_ENDED")
    assert ended.ended_at.startswith("2026-11-18T13:00:00")


def test_active_behaviour_flags_close_at_the_break(rules):
    events, _, _ = run_at(
        rules, at(*WED, 12, 58), [(5 * 60, True, LOW_MOTION, _signals(phone=0.9))]
    )
    names = types_of(events)
    assert names.count("PHONE_STARTED") == 1
    assert names.count("PHONE_ENDED") == 1
    _assert_episodes_pair(events)


def test_after_the_break_idle_needs_a_fresh_confirm(rules):
    """Still at the desk through lunch: IDLE only 180 s after 13:45, not at 13:45."""
    events, _, _ = run_at(
        rules,
        at(*WED, 13, 40),
        [(10 * 60, True, LOW_MOTION, SEATED_IDLE)],  # 13:40-13:50
    )
    idle = [e for e in events if e.event_type == "IDLE_STARTED"]
    assert len(idle) == 1
    assert idle[0].started_at.startswith("2026-11-18T13:45:00")
    assert idle[0].duration_seconds >= 180


def test_sunday_raises_nothing(rules):
    events, states, _ = run_at(rules, at(*SUN, 10), [(20 * 60, False, 0.0, None)])
    assert events == []
    assert set(states) == {"BREAK"}


def test_before_the_shift_then_into_it(rules):
    """07:55 empty desk: BREAK until 08:00, then AWAY after a full 300 s."""
    events, states, _ = run_at(rules, at(*WED, 7, 55), [(15 * 60, False, 0.0, None)])
    assert states[0] == "BREAK"
    away = [e for e in events if e.event_type == "AWAY_STARTED"]
    assert len(away) == 1
    assert away[0].started_at.startswith("2026-11-18T08:00:")


def test_ignore_shifts_monitors_at_night(rules):
    night_rules = {**rules, "ignore_shifts": True}
    events, states, _ = run_at(
        night_rules, at(*SUN, 2), [(240, True, LOW_MOTION, SEATED_IDLE)]
    )
    assert "BREAK" not in states
    assert "IDLE_STARTED" in types_of(events)
