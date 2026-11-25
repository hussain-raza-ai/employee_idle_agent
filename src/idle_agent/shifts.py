"""Shift calendar: when monitoring is on, and why it is off when it is not.

Built from the `shifts`, `breaks` and `holidays` blocks of idle_rules.yaml.
Outside a shift, during an approved break, on a weekly off day or on a holiday
the state machine is in BREAK and raises no alerts.

A shift whose end is not after its start runs past midnight; the hours after
midnight belong to the day the shift started, so a Saturday night shift that
ends at 01:00 Sunday is still Saturday's shift even with Sunday off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import FrozenSet, List, Optional, Tuple

_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _hhmm(value: object, where: str) -> time:
    text = str(value).strip()
    try:
        hours, minutes = text.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{where}: '{value}' is not a HH:MM time") from exc


def _days(values: object, where: str) -> FrozenSet[int]:
    out = set()
    for value in values or []:
        key = str(value).strip().lower()[:3]
        if key not in _DAYS:
            raise ValueError(f"{where}: unknown day '{value}' (use mon, tue, … sun)")
        out.add(_DAYS[key])
    return frozenset(out)


def _date(value: object, where: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value  # YAML parses an unquoted 2026-12-25 into a date
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{where}: '{value}' is not a YYYY-MM-DD date") from exc


@dataclass(frozen=True)
class Window:
    """A daily time window, optionally limited to some weekdays."""

    id: str
    start: time
    end: time
    days: Optional[FrozenSet[int]] = None  # None: every day

    def _on(self, weekday: int) -> bool:
        return self.days is None or weekday in self.days

    def match(self, local: datetime) -> Optional[date]:
        """The day this window started on, if `local` falls inside it."""
        t = local.time()
        today = local.date()
        if self.start < self.end:
            return today if self.start <= t < self.end and self._on(today.weekday()) else None
        # Runs past midnight (an end equal to the start means all 24 hours).
        if t >= self.start and self._on(today.weekday()):
            return today
        yesterday = today - timedelta(days=1)
        if t < self.end and self._on(yesterday.weekday()):
            return yesterday
        return None


class ShiftCalendar:
    def __init__(
        self,
        tz: tzinfo,
        shifts: List[Window],
        breaks: List[Window],
        weekly_off: FrozenSet[int] = frozenset(),
        holidays: FrozenSet[date] = frozenset(),
        enabled: bool = True,
    ):
        self.tz = tz
        self.shifts = shifts
        self.breaks = breaks
        self.weekly_off = weekly_off
        self.holidays = holidays
        self.enabled = enabled

    @classmethod
    def from_rules(cls, rules: dict, tz: tzinfo) -> "ShiftCalendar":
        shifts = [
            Window(
                id=str(item.get("id", f"shift-{i}")),
                start=_hhmm(item.get("start"), f"shifts[{i}].start"),
                end=_hhmm(item.get("end"), f"shifts[{i}].end"),
                days=_days(item.get("days"), f"shifts[{i}].days") if item.get("days") else None,
            )
            for i, item in enumerate(rules.get("shifts") or [])
        ]
        breaks = [
            Window(
                id=str(item.get("id", f"break-{i}")),
                start=_hhmm(item.get("start"), f"breaks[{i}].start"),
                end=_hhmm(item.get("end"), f"breaks[{i}].end"),
                days=_days(item.get("days"), f"breaks[{i}].days") if item.get("days") else None,
            )
            for i, item in enumerate(rules.get("breaks") or [])
        ]
        # Two accepted layouts:
        #   holidays: {weekly_off: [sun], dates: ["2026-12-25"]}
        #   holidays: ["2026-12-25"]   with weekly_off at the top level
        raw = rules.get("holidays") or {}
        if isinstance(raw, dict):
            dates = raw.get("dates") or []
            weekly = raw.get("weekly_off") or rules.get("weekly_off") or []
        else:
            dates = raw
            weekly = rules.get("weekly_off") or []
        return cls(
            tz=tz,
            shifts=shifts,
            breaks=breaks,
            weekly_off=_days(weekly, "holidays.weekly_off"),
            holidays=frozenset(_date(d, "holidays.dates") for d in dates),
            enabled=not bool(rules.get("ignore_shifts", False)),
        )

    def status(self, when: datetime) -> Tuple[bool, str]:
        """(monitored, reason) at an aware instant.

        reason is `shift:<id>` when monitored, otherwise one of
        `outside_shift`, `weekly_off`, `holiday`, or `break:<id>`.
        """
        if not self.enabled:
            return True, "calendar_off"
        local = when.astimezone(self.tz)

        if self.shifts:
            shift_day, shift_id = None, None
            for shift in self.shifts:
                day = shift.match(local)
                if day is not None:
                    shift_day, shift_id = day, shift.id
                    break
            if shift_day is None:
                if local.weekday() in self.weekly_off:
                    return False, "weekly_off"
                if local.date() in self.holidays:
                    return False, "holiday"
                return False, "outside_shift"
        else:
            # No shifts configured: monitor all day, still honouring days off.
            shift_day, shift_id = local.date(), "all_day"

        if shift_day.weekday() in self.weekly_off:
            return False, "weekly_off"
        if shift_day in self.holidays:
            return False, "holiday"
        for brk in self.breaks:
            if brk.match(local) is not None:
                return False, f"break:{brk.id}"
        return True, f"shift:{shift_id}"

    def describe(self) -> str:
        if not self.enabled:
            return "Shift calendar: OFF (ignore_shifts) — monitoring around the clock"
        names = {v: k for k, v in _DAYS.items()}

        def fmt(w: Window) -> str:
            days = "" if w.days is None else " " + ",".join(names[d] for d in sorted(w.days))
            return f"{w.id} {w.start:%H:%M}-{w.end:%H:%M}{days}"

        shifts = "; ".join(fmt(s) for s in self.shifts) or "all day"
        breaks = "; ".join(fmt(b) for b in self.breaks) or "none"
        off = ",".join(names[d] for d in sorted(self.weekly_off)) or "none"
        return (
            f"Shift calendar: shifts [{shifts}]  breaks [{breaks}]  "
            f"weekly off [{off}]  holidays [{len(self.holidays)}]"
        )
