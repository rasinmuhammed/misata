---
title: "Distribution Reference, Every Numeric Shape Misata Supports"
description: "The complete set of numeric distributions — normal, log-normal, uniform, exponential, poisson, binomial, zipf/pareto, beta, gamma — with their parameters and when to use each."
---

# Distribution Reference

Every `int`/`float` column carries a `distribution` in its `distribution_params`. Pick the shape that matches the real-world quantity; pass the listed parameters. All distributions honour `min`/`max` clamping and `decimals`.

```python
{"type": "integer", "distribution": "poisson", "lambda": 4, "min": 0}
```

---

## Continuous

| Distribution | Params | Use for |
|---|---|---|
| `normal` | `mean`, `std` | Symmetric quantities: age, height, test scores. |
| `lognormal` | `mu`, `sigma` | Right-skewed money: price, salary, order amount. |
| `uniform` | `min`, `max` | Flat ranges: latitude, a 1–5 rating. |
| `exponential` | `scale` | Wait times, inter-arrival gaps. |
| `beta` | `a`, `b` (scaled to `min`/`max`) | Bounded proportions, scores in a fixed band. |
| `gamma` | `shape`, `scale` | Positive skewed durations, insurance claim sizes. |

## Discrete

| Distribution | Params | Use for |
|---|---|---|
| `poisson` | `lambda` (alias `lam`) | Counts per interval: items per order, calls per hour. |
| `binomial` | `n`, `p` | Successes out of `n` trials: conversions, defects. |

## Heavy-tailed (power-law)

For "a few get most, most get very few" — views, followers, wealth, file sizes:

| Distribution | Params | Notes |
|---|---|---|
| `zipf` | `a` | Discrete power-law; larger `a` ⇒ steeper tail. |
| `pareto` / `power_law` | `alpha`, `scale` | Continuous heavy tail. |

```python
{"type": "integer", "distribution": "zipf", "a": 2.0, "min": 1}     # view counts
{"type": "integer", "distribution": "binomial", "n": 10, "p": 0.3}  # successes
```

---

## Conditional & correlated shapes

Distributions describe a single column's marginal. To make columns relate:

- **One column switches another's distribution** → [`depends_on`](conditional-columns.md).
- **Two numeric columns move together** → [correlations](correlations.md).
- **A quantity changes over time** → [outcome curves](outcome_curves.md) (magnitude) or [rate curves](rate_curves.md) (proportion).

## Parameter aliases

A couple of names are accepted both ways so hand-written and tool-generated schemas both work:

- Poisson rate: `lambda` **or** `lam`.
- Zipf shape: `a`; Pareto shape: `alpha`.

## In the studio

The column **Inspector** auto-suggests a distribution from the column name (e.g. `views` → power-law, `price` → log-normal) as a one-click preset, and the **Engine params** panel exposes the full distribution picker with the relevant shape fields.
