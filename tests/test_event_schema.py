"""The emitted event must validate against schemas/idle_event.schema.json.

The schema is the contract with the ERP team, so a drift between the code and
the schema is a bug in whichever changed last. Skipped if jsonschema is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO / "schemas" / "idle_event.schema.json"
EXAMPLE_PATH = REPO / "schemas" / "examples" / "idle_started.json"

jsonschema = pytest.importorskip("jsonschema")


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_committed_example_validates(schema):
    example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(example, schema)


def test_emitted_events_validate(schema):
    """Run the state machine and validate what it actually produces."""
    from test_state_machine import SEATED_IDLE, LOW_MOTION, run_timeline  # noqa: E402
    from idle_agent.state_machine import load_rules

    rules = load_rules(REPO / "config" / "idle_rules.yaml")
    events, _ = run_timeline(rules, [(240, True, LOW_MOTION, SEATED_IDLE)])
    assert events, "expected at least one event"
    for ev in events:
        jsonschema.validate(ev.to_dict(), schema)


def test_schema_and_config_agree_on_event_types(schema):
    """Every event type in idle_rules.yaml must exist in the schema enum."""
    import yaml

    rules = yaml.safe_load(
        (REPO / "config" / "idle_rules.yaml").read_text(encoding="utf-8")
    )
    configured = set(rules["events"]["emit"])
    allowed = set(schema["properties"]["event_type"]["enum"])
    assert configured <= allowed, f"not in the schema: {sorted(configured - allowed)}"


def test_openapi_enum_matches_the_schema(schema):
    """The OpenAPI contract and the JSON Schema must list the same event types."""
    import yaml

    spec = yaml.safe_load(
        (REPO / "openapi" / "erp-events.yaml").read_text(encoding="utf-8")
    )
    openapi_enum = set(
        spec["components"]["schemas"]["IdleTimeVisionEvent"]["properties"][
            "event_type"
        ]["enum"]
    )
    assert openapi_enum == set(schema["properties"]["event_type"]["enum"])
