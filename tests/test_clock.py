"""Wall-clock handling: no event may be dated 1970 — no GPU, no torch."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from idle_agent import clock
from idle_agent.cli import resolve_clip_start
from idle_agent.state_machine import ZoneStateMachine, load_rules

REPO = Path(__file__).resolve().parents[1]
PKT = timezone(timedelta(hours=5))


@pytest.fixture(scope="module")
def tz():
    return clock.site_tz("Asia/Karachi")


# --- file names --------------------------------------------------------------


def test_nvr_file_name_gives_the_start(tz):
    name = "NVR-7BB9_ch12_main_20261118150005_20261118152059.mp4"
    start = clock.clip_start_from_filename(name, tz)
    assert start == datetime(2026, 11, 18, 15, 0, 5, tzinfo=PKT)


def test_only_the_file_name_is_searched(tz):
    """Digits in a directory name must not be mistaken for the start."""
    path = Path("/data/20991231235959/clip_20261118150005.mp4")
    assert clock.clip_start_from_filename(path, tz).year == 2026


@pytest.mark.parametrize(
    "name",
    [
        "cam01_full_h264.mp4",  # no stamp at all
        "clip_2026111815000.mp4",  # 13 digits
        "clip_202611181500055.mp4",  # 15 digits: not a stamp
        "serial_99999999999999.mp4",  # 14 digits that are not a date
    ],
)
def test_names_without_a_valid_stamp_give_none(name, tz):
    assert clock.clip_start_from_filename(name, tz) is None


# --- parsing ----------------------------------------------------------------


def test_parse_iso_keeps_an_explicit_offset(tz):
    dt = clock.parse_iso("2026-11-18T15:00:05+05:00", tz)
    assert dt.utcoffset() == timedelta(hours=5)


def test_parse_iso_reads_z_as_utc(tz):
    dt = clock.parse_iso("2026-11-18T10:00:05Z", tz)
    assert dt == datetime(2026, 11, 18, 15, 0, 5, tzinfo=PKT)


def test_parse_iso_treats_a_bare_time_as_site_time(tz):
    dt = clock.parse_iso("2026-11-18T15:00:05", tz)
    assert dt.utcoffset() == timedelta(hours=5)


def test_parse_iso_rejects_garbage(tz):
    with pytest.raises(ValueError, match="ISO-8601"):
        clock.parse_iso("yesterday afternoon", tz)


def test_unknown_timezone_says_how_to_fix_it():
    with pytest.raises(RuntimeError, match="tzdata"):
        clock.site_tz("Not/A_Zone")


def test_timezone_is_read_from_the_rules_file():
    tz = clock.tz_from_rules_file(REPO / "config" / "idle_rules.yaml")
    assert datetime(2026, 11, 18, 12, tzinfo=tz).utcoffset() == timedelta(hours=5)


# --- the CLI's decision -------------------------------------------------------


def test_cli_explicit_clip_start_wins(tz):
    got = resolve_clip_start(
        "file", "NVR_20261118150005.mp4", "2026-01-01T08:00:00+05:00", tz
    )
    assert got == datetime(2026, 1, 1, 8, 0, tzinfo=PKT)


def test_cli_file_falls_back_to_the_file_name(tz):
    got = resolve_clip_start(
        "file", "recordings/cam-01/NVR-7BB9_ch12_main_20261118150005_x.mp4", None, tz
    )
    assert got == datetime(2026, 11, 18, 15, 0, 5, tzinfo=PKT)


def test_cli_file_without_any_start_stops_with_instructions(tz):
    with pytest.raises(SystemExit) as exc:
        resolve_clip_start("file", "cam01_full_h264.mp4", None, tz)
    assert "--clip-start" in str(exc.value)


def test_cli_live_stream_is_left_for_the_pipeline_to_anchor(tz):
    assert resolve_clip_start("rtsp", "rtsp://cam/stream", None, tz) is None


def test_cli_bad_clip_start_is_a_clean_error(tz):
    with pytest.raises(SystemExit, match="--clip-start"):
        resolve_clip_start("file", "x.mp4", "not-a-date", tz)


# --- the state machine --------------------------------------------------------


def test_state_machine_without_clip_start_uses_now():
    rules = load_rules(REPO / "config" / "idle_rules.yaml")
    before = datetime.now(timezone.utc) - timedelta(seconds=2)
    sm = ZoneStateMachine("cam-01", ["z"], rules)
    after = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert before <= sm.clip_start <= after


def test_naive_clip_start_takes_the_site_timezone():
    rules = load_rules(REPO / "config" / "idle_rules.yaml")
    sm = ZoneStateMachine("cam-01", ["z"], rules, clip_start=datetime(2026, 11, 18, 15))
    assert sm._iso(0) == "2026-11-18T15:00:00+05:00"


def test_event_times_are_in_site_time_even_from_a_utc_start():
    rules = load_rules(REPO / "config" / "idle_rules.yaml")
    utc_start = datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc)  # 09:00 PKT
    sm = ZoneStateMachine("cam-01", ["z"], rules, clip_start=utc_start)
    assert sm._iso(90) == "2026-11-18T09:01:30+05:00"
