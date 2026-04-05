import pandas as pd

from misata.workflows import WorkflowEngine


def test_generate_event_stream_is_monotonic_per_entity():
    engine = WorkflowEngine()
    events = engine.generate_event_stream(entity_ids=[1, 2], workflow_name="order", start_date="2024-01-01")

    assert not events.empty
    for _, group in events.groupby("entity_id"):
        assert group["timestamp"].is_monotonic_increasing
