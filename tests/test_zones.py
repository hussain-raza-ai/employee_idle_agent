"""Zone polygon loading and point-in-polygon tests — no GPU, no torch."""

from __future__ import annotations

from pathlib import Path

import pytest

from idle_agent.zones import load_zones, point_in_polygon

REPO = Path(__file__).resolve().parents[1]
ZONES_YAML = REPO / "config" / "zones.yaml"

SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]


@pytest.mark.parametrize(
    "x,y,expected",
    [
        (0.5, 0.5, True),  # centre
        (0.25, 0.25, True),  # just inside a corner
        (0.1, 0.5, False),  # left of the polygon
        (0.9, 0.5, False),  # right of it
        (0.5, 0.1, False),  # above it
        (0.5, 0.9, False),  # below it
    ],
)
def test_point_in_polygon(x, y, expected):
    assert point_in_polygon(x, y, SQUARE) is expected


def test_degenerate_polygon_contains_nothing():
    assert point_in_polygon(0.5, 0.5, [(0.0, 0.0), (1.0, 1.0)]) is False


def test_load_zones_filters_by_camera_and_enabled():
    """cam-01 yields the enabled counter desk; cam-02's placeholders are off."""
    cam01 = load_zones(ZONES_YAML, camera_id="cam-01")
    assert [z.id for z in cam01] == ["ws-counter-1"]

    cam02 = load_zones(ZONES_YAML, camera_id="cam-02")
    assert cam02 == [], "cam-02 placeholder zones are disabled until calibration"


def test_counter_zone_has_seat_and_work_subregions():
    """The pilot zone defines both sub-polygons explicitly in zones.yaml."""
    zone = load_zones(ZONES_YAML, camera_id="cam-01")[0]
    assert zone.work_polygon, "work polygon drives the 'working' signal"
    assert zone.seat_polygon, "seat polygon drives the 'off seat' signal"
    # Both sub-regions must lie inside the zone's bounding box, or the
    # behaviour signals can never fire.
    zx = [p[0] for p in zone.polygon]
    zy = [p[1] for p in zone.polygon]
    for name, poly in (("work", zone.work_polygon), ("seat", zone.seat_polygon)):
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        assert min(zx) <= cx <= max(zx), f"{name} polygon centre outside the zone in x"
        assert min(zy) <= cy <= max(zy), f"{name} polygon centre outside the zone in y"


@pytest.mark.parametrize(
    "who,x,y,inside",
    [
        # Points measured on NVR-7BB9_ch15 frames (normalised).
        ("seated operator, body centre", 0.43, 0.40, True),
        ("seated operator, seat point", 0.43, 0.48, True),
        ("operator leaning to the lower keyboard", 0.40, 0.50, True),
        ("neighbouring operator at the upper desk", 0.375, 0.26, False),
        ("customer standing at the counter", 0.26, 0.45, False),
        ("customer further down the queue", 0.25, 0.70, False),
        ("staff walking behind the operator", 0.50, 0.35, False),
        ("pharmacist at the laptop desk below", 0.52, 0.80, False),
    ],
)
def test_counter_zone_covers_the_operator_not_the_customers(who, x, y, inside):
    """ws-counter-1 must sit on the staff side of the counter.

    The original rectangle covered the customer queue: customers stood inside
    it and the operator's chair was outside. These points pin the redraw.
    """
    zone = load_zones(ZONES_YAML, camera_id="cam-01")[0]
    assert point_in_polygon(x, y, zone.polygon) is inside, who


def test_counter_zone_work_and_seat_match_the_desk():
    zone = load_zones(ZONES_YAML, camera_id="cam-01")[0]
    # Hands on either keyboard count as working; hands in the lap do not.
    assert point_in_polygon(0.37, 0.38, zone.work_polygon), "upper keyboard"
    assert point_in_polygon(0.37, 0.50, zone.work_polygon), "lower keyboard"
    assert not point_in_polygon(0.44, 0.44, zone.work_polygon), "lap"
    # Seated hips are on the seat; a customer's are not.
    assert point_in_polygon(0.43, 0.45, zone.seat_polygon), "seated hips"
    assert not point_in_polygon(0.26, 0.55, zone.seat_polygon), "customer"


def test_polygon_coordinates_are_normalised():
    """Every coordinate must be a 0-1 fraction, not a pixel value."""
    for zone in load_zones(ZONES_YAML, camera_id="cam-01"):
        for poly in (zone.polygon, zone.work_polygon, zone.seat_polygon):
            for x, y in poly or []:
                assert 0.0 <= x <= 1.0, f"{zone.id}: x={x} is not normalised"
                assert 0.0 <= y <= 1.0, f"{zone.id}: y={y} is not normalised"


def test_defaults_are_derived_when_subregions_are_omitted(tmp_path):
    """A zone with only a polygon still gets a seat and work band."""
    yaml_text = """
version: "1.0"
zones:
  - id: ws-test
    name: "Test desk"
    camera_id: cam-test
    enabled: true
    polygon:
      - [0.1, 0.1]
      - [0.9, 0.1]
      - [0.9, 0.9]
      - [0.1, 0.9]
"""
    path = tmp_path / "zones.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    zone = load_zones(path, camera_id="cam-test")[0]
    assert zone.work_polygon and zone.seat_polygon
    # The seat band sits below the work band — the chair is nearer the camera.
    work_mid = sum(p[1] for p in zone.work_polygon) / len(zone.work_polygon)
    seat_mid = sum(p[1] for p in zone.seat_polygon) / len(zone.seat_polygon)
    assert seat_mid > work_mid


def test_pixel_polygon_scales_to_frame_size():
    zone = load_zones(ZONES_YAML, camera_id="cam-01")[0]
    pts = zone.to_pixel_polygon(1920, 1080)
    assert len(pts) == len(zone.polygon)
    for (px, py), (nx, ny) in zip(pts, zone.polygon):
        assert px == int(nx * 1920)
        assert py == int(ny * 1080)
