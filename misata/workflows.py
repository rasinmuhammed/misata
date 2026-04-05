"""Explicit workflow state machines for realism-aware generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class WorkflowState:
    """A workflow state."""

    name: str
    is_terminal: bool = False


@dataclass
class WorkflowTransition:
    """A transition between two workflow states."""

    from_state: str
    to_state: str
    probability: float
    min_hours: float = 0.5
    max_hours: float = 48.0


@dataclass
class Workflow:
    """A named workflow preset."""

    name: str
    states: List[WorkflowState]
    transitions: List[WorkflowTransition]
    initial_state: str
    status_column: str = "status"

    def get_transitions_from(self, state: str) -> List[WorkflowTransition]:
        return [transition for transition in self.transitions if transition.from_state == state]

    def is_terminal(self, state: str) -> bool:
        return any(workflow_state.name == state and workflow_state.is_terminal for workflow_state in self.states)


WORKFLOW_PRESETS: Dict[str, Workflow] = {}


def _register(workflow: Workflow) -> None:
    WORKFLOW_PRESETS[workflow.name] = workflow


_register(
    Workflow(
        name="order",
        initial_state="pending",
        states=[
            WorkflowState("pending"),
            WorkflowState("confirmed"),
            WorkflowState("processing"),
            WorkflowState("shipped"),
            WorkflowState("delivered", is_terminal=True),
            WorkflowState("cancelled", is_terminal=True),
            WorkflowState("refunded", is_terminal=True),
        ],
        transitions=[
            WorkflowTransition("pending", "confirmed", 0.85, 0.5, 4),
            WorkflowTransition("pending", "cancelled", 0.15, 0.1, 8),
            WorkflowTransition("confirmed", "processing", 0.95, 1, 8),
            WorkflowTransition("confirmed", "cancelled", 0.05, 1, 12),
            WorkflowTransition("processing", "shipped", 0.97, 4, 48),
            WorkflowTransition("processing", "cancelled", 0.03, 1, 12),
            WorkflowTransition("shipped", "delivered", 0.93, 24, 120),
            WorkflowTransition("shipped", "refunded", 0.07, 24, 168),
        ],
    )
)

_register(
    Workflow(
        name="support_ticket",
        initial_state="open",
        states=[
            WorkflowState("open"),
            WorkflowState("assigned"),
            WorkflowState("in_progress"),
            WorkflowState("waiting"),
            WorkflowState("escalated"),
            WorkflowState("resolved", is_terminal=True),
            WorkflowState("closed", is_terminal=True),
        ],
        transitions=[
            WorkflowTransition("open", "assigned", 0.9, 0.5, 6),
            WorkflowTransition("open", "closed", 0.1, 0.1, 2),
            WorkflowTransition("assigned", "in_progress", 0.85, 1, 12),
            WorkflowTransition("assigned", "escalated", 0.15, 1, 6),
            WorkflowTransition("in_progress", "resolved", 0.75, 4, 72),
            WorkflowTransition("in_progress", "waiting", 0.2, 1, 24),
            WorkflowTransition("in_progress", "escalated", 0.05, 1, 8),
            WorkflowTransition("waiting", "in_progress", 0.8, 4, 48),
            WorkflowTransition("waiting", "closed", 0.2, 1, 24),
            WorkflowTransition("escalated", "resolved", 0.35, 2, 24),
            WorkflowTransition("escalated", "in_progress", 0.65, 1, 12),
        ],
    )
)

_register(
    Workflow(
        name="subscription",
        initial_state="trial",
        states=[
            WorkflowState("trial"),
            WorkflowState("active"),
            WorkflowState("past_due"),
            WorkflowState("paused"),
            WorkflowState("cancelled", is_terminal=True),
            WorkflowState("expired", is_terminal=True),
        ],
        transitions=[
            WorkflowTransition("trial", "active", 0.6, 24 * 14, 24 * 14),
            WorkflowTransition("trial", "cancelled", 0.4, 24 * 14, 24 * 14),
            WorkflowTransition("active", "past_due", 0.08, 24 * 30, 24 * 30),
            WorkflowTransition("active", "paused", 0.04, 24 * 30, 24 * 30),
            WorkflowTransition("active", "cancelled", 0.05, 24 * 30, 24 * 90),
            WorkflowTransition("past_due", "active", 0.6, 1, 72),
            WorkflowTransition("past_due", "cancelled", 0.4, 24 * 7, 24 * 30),
            WorkflowTransition("paused", "active", 0.7, 24 * 7, 24 * 60),
            WorkflowTransition("paused", "cancelled", 0.3, 24 * 30, 24 * 90),
        ],
    )
)


class WorkflowEngine:
    """Applies workflow rules and emits event streams."""

    COMPLETION_TIMESTAMPS = {
        "delivered": "delivered_at",
        "resolved": "resolved_at",
        "closed": "closed_at",
        "cancelled": "cancelled_at",
        "refunded": "refunded_at",
        "expired": "expired_at",
    }

    def __init__(self, rng: Optional[np.random.Generator] = None):
        self.rng = rng or np.random.default_rng(42)

    def apply_workflow(
        self,
        df: pd.DataFrame,
        workflow_name: str,
        *,
        protected_columns: Optional[set[str]] = None,
    ) -> pd.DataFrame:
        if df.empty or workflow_name not in WORKFLOW_PRESETS:
            return df

        protected_columns = protected_columns or set()
        workflow = WORKFLOW_PRESETS[workflow_name]
        output = df.copy()
        status_column = workflow.status_column
        if status_column not in output.columns or status_column in protected_columns:
            return output

        output[status_column] = output[status_column].astype(str).str.lower()
        output = self._fix_terminal_timestamps(output, workflow, protected_columns)
        return output

    def generate_event_stream(
        self,
        entity_ids: Any,
        workflow_name: str,
        start_date: str = "2024-01-01",
        max_events_per_entity: int = 20,
    ) -> pd.DataFrame:
        if workflow_name not in WORKFLOW_PRESETS:
            raise ValueError(f"Unknown workflow '{workflow_name}'")

        workflow = WORKFLOW_PRESETS[workflow_name]
        base_timestamp = pd.Timestamp(start_date)
        rows = []

        for entity_id in entity_ids:
            state = workflow.initial_state
            current_timestamp = base_timestamp + pd.Timedelta(hours=float(self.rng.uniform(0, 24 * 30)))
            sequence_number = 0

            while sequence_number < max_events_per_entity:
                rows.append(
                    {
                        "entity_id": entity_id,
                        "state": state,
                        "timestamp": current_timestamp,
                        "sequence_num": sequence_number,
                    }
                )
                sequence_number += 1

                if workflow.is_terminal(state):
                    break

                transitions = workflow.get_transitions_from(state)
                if not transitions:
                    break
                probabilities = np.array([transition.probability for transition in transitions], dtype=float)
                probabilities /= probabilities.sum()
                chosen = transitions[int(self.rng.choice(len(transitions), p=probabilities))]
                current_timestamp = current_timestamp + pd.Timedelta(
                    hours=float(self.rng.uniform(chosen.min_hours, chosen.max_hours))
                )
                state = chosen.to_state

        if not rows:
            return pd.DataFrame(columns=["entity_id", "state", "timestamp", "sequence_num"])
        return pd.DataFrame(rows).sort_values(["entity_id", "timestamp"]).reset_index(drop=True)

    def _fix_terminal_timestamps(
        self,
        df: pd.DataFrame,
        workflow: Workflow,
        protected_columns: set[str],
    ) -> pd.DataFrame:
        status_column = workflow.status_column
        created_column = "created_at" if "created_at" in df.columns else None

        for terminal_state, timestamp_column in self.COMPLETION_TIMESTAMPS.items():
            if timestamp_column not in df.columns or timestamp_column in protected_columns:
                continue

            terminal_mask = df[status_column].astype(str).str.lower() == terminal_state
            df.loc[~terminal_mask, timestamp_column] = pd.NaT
            if created_column is None:
                continue

            created = pd.to_datetime(df[created_column], errors="coerce")
            missing = terminal_mask & df[timestamp_column].isna() & created.notna()
            if missing.any():
                offsets = self.rng.uniform(1, 72, size=int(missing.sum()))
                df.loc[missing, timestamp_column] = created.loc[missing] + pd.to_timedelta(offsets, unit="h")

        return df
