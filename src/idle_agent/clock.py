"""Wall-clock helpers: the site timezone and when a recording started.

Every event carries a wall-clock time. For a recording that time is the
recording's real start plus the offset into the video; for a live stream it is
the moment the stream opened plus the time since. Nothing here may fall back to
the Unix epoch: an event dated 1970 is wrong data, not a default.
"""

from __future__ import annotations

import re
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_TIMEZONE = "Asia/Karachi"

# NVR exports carry the start (and end) as YYYYMMDDhhmmss, e.g.
# NVR-7BB9_ch12_main_20261118150005_20261118152059.mp4. The first stamp is the
# start. A run of exactly 14 digits, so a longer number cannot match by accident.
_STAMP = re.compile(r"(?<!\d)(\d{14})(?!\d)")


def site_tz(name: Optional[str] = None) -> tzinfo:
    """The IANA timezone for the site, e.g. Asia/Karachi.

    Raises with an actionable message when the timezone database is missing,
    which on Windows means the tzdata package is not installed.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    key = name or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            f"Timezone '{key}' not found. On Windows install the timezone "
            f"database with: pip install tzdata"
        ) from exc


def tz_from_rules_file(path: str | Path) -> tzinfo:
    """Read `timezone:` from idle_rules.yaml without loading the full rules."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        data = {}
    return site_tz(data.get("timezone"))


def now(tz: tzinfo) -> datetime:
    """Current wall-clock time in the site timezone, to the second."""
    return datetime.now(tz).replace(microsecond=0)


def aware(dt: datetime, tz: tzinfo) -> datetime:
    """Attach the site timezone to a naive datetime; leave an aware one alone."""
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def parse_iso(text: str, tz: tzinfo) -> datetime:
    """Parse an ISO-8601 time. A trailing Z is UTC; no offset means site time."""
    value = text.strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Invalid time '{text}'. Use ISO-8601, e.g. 2026-11-18T15:00:05+05:00"
        ) from exc
    return aware(dt, tz)


def clip_start_from_filename(path: str | Path, tz: tzinfo) -> Optional[datetime]:
    """Recording start from an NVR-style file name, read as site local time.

    Returns None when the name carries no valid YYYYMMDDhhmmss stamp.
    """
    for match in _STAMP.finditer(Path(path).name):
        try:
            return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=tz)
        except ValueError:
            continue  # 14 digits that are not a date, e.g. a serial number
    return None
