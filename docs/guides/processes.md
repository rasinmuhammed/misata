# Processes and event logs

A lifecycle says which states a row's history contains. A **process** says
how that history unfolds: which step follows which, how often a case loops
back (a reopened ticket, a failed payment retried, a claim sent back for more
documents), and how long each step takes. It writes one row per event, the
shape process-mining tools read.

```yaml
tables:
  tickets:
    rows: 5000
    columns:
      ticket_id: {type: int, primary_key: true}
      opened_at: {type: datetime, start: "2024-01-01", end: "2024-06-30"}
      status: {type: text}

processes:
  - name: ticket_flow
    cases_table: tickets
    case_key: ticket_id
    start_column: opened_at          # the first event is at the case's start
    initial: opened
    transitions:                     # a state with no row is terminal (closed)
      opened:    {triaged: 1.0}
      triaged:   {resolved: 0.85, escalated: 0.15}
      escalated: {resolved: 1.0}
      resolved:  {closed: 0.9, reopened: 0.1}
      reopened:  {triaged: 1.0}
    dwell:                           # time in a state before leaving it
      opened: {distribution: lognormal, mu: 0, sigma: 0.8, unit: hours}
      "escalated->resolved": {distribution: exponential, scale: 2, unit: days}
    final_state_column: status       # the ticket agrees with its log
    max_steps: 25                    # bounds rework loops
```

This produces a `ticket_flow_events` table (`event_id`, `ticket_id`, `step`,
`activity`, `timestamp`; names configurable) next to `tickets`, from Python,
YAML, dict schemas and the CLI alike.

## What is exact and what is drawn

Exact, and re-checked from the rows by `misata.process_audit(events, spec,
cases)`:

- every case starts in `initial`, at or after its `start_column`;
- only declared transitions occur, numbered `1..n` per case;
- timestamps never go backwards, in whole seconds;
- every case ends in a terminal state or at `max_steps`;
- with `final_state_column`, the case row holds its log's last state.

Drawn from the declaration (emergent, not exact): which path each case takes,
so the share of escalations or reopens lands near, not on, 15% and 10%; and
each step's duration.

## Dwell times

Keyed by state (`opened`), or by one transition (`"escalated->resolved"`),
which wins. Distributions: `lognormal` (`mu`, `sigma`), `exponential`
(`scale`), `gamma` (`shape`, `scale`), `uniform` (`min`, `max`), `fixed`
(`value`), each with a `unit` of `seconds`, `minutes`, `hours` or `days`.
Steps without one take lognormal(0, 1) hours.

## Export for process mining

```python
misata.to_xes(tables["ticket_flow_events"], "tickets.xes", case_column="ticket_id")
```

writes IEEE 1849 XES, which ProM, PM4Py, Disco and Celonis import.

## What it is not

A semi-Markov chain, simulated for every case at once with numpy (200,000
tickets in about a second), not a discrete-event simulation. There are no
queues or shared resources, so a step does not take longer because the
system is busy. If waits that depend on load are what you need to test, that
is a simulator's job (SimPy, salabim); a process here gives you the event
log's structure and timing shape without one.
