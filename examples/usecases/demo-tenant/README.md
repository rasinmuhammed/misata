---
title: A Demo Tenant That Tells a Story
description: Fill a demo account with customers who trial, convert, fall behind and churn in a legal order, a few whales who carry the revenue, and dates that end today, then prove it reads as real with the realism report.
---

# A demo tenant that tells a story

A demo account full of uniform noise makes every chart flat and every story
fall apart under the first question. "Why does this churned customer have a
renewal date?" Declare the story the demo needs to tell and the data keeps
it.

**Who:** sales engineers, product managers, anyone who demos a product with
charts in it.
**Time:** under 2 seconds.

## The declaration

Subscriptions move through a state machine: trial, active, past due,
churned. 60% are active and 26% churned, exactly. Payments come mostly from
a handful of large customers, and `preset: demo` moves every date so the
latest one is today.

```yaml
# misata.yaml
name: demo_tenant
seed: 404
preset: demo
tables:
  customers:
    rows: 1200
    columns:
      customer_id: {type: int, unique: true, min: 1, max: 1200}
      company: {type: text, text_type: company}
      industry: {type: categorical, choices: [software, retail, health, finance, logistics], probabilities: [0.34, 0.22, 0.16, 0.16, 0.12]}
      signed_up_at: {type: date, start: "2023-01-01", end: "2025-09-30"}
  subscriptions:
    rows: 1200
    columns:
      subscription_id: {type: int, unique: true, min: 1, max: 1200}
      customer_id: {type: foreign_key, unique: true}
      plan: {type: categorical, choices: [starter, growth, enterprise], probabilities: [0.55, 0.33, 0.12]}
      status: {type: categorical, choices: [trialing, active, past_due, churned]}
      started_at: {type: date, start: "2023-01-01", end: "2025-09-30", weekday_weights: [0.19, 0.2, 0.2, 0.18, 0.15, 0.04, 0.04]}
      activated_at: {type: date, nullable: true}
      past_due_at: {type: date, nullable: true}
      churned_at: {type: date, nullable: true}
  payments:
    rows: 18000
    columns:
      payment_id: {type: int, unique: true, min: 1, max: 1000000}
      customer_id: {type: foreign_key, sampling: pareto, alpha: 1.1}
      amount: {type: float, distribution: lognormal, mean: 900, std: 2200, min: 40, max: 60000, decimals: 2}
      paid_at: {type: datetime, start: "2023-01-01", end: "2025-10-20", weekday_weights: [0.17, 0.17, 0.17, 0.17, 0.16, 0.08, 0.08]}
relationships:
  - customers.customer_id -> subscriptions.customer_id
  - customers.customer_id -> payments.customer_id
lifecycles:
  - name: subscription
    table: subscriptions
    state_column: status
    start_column: started_at
    initial: trialing
    states:
      - {name: trialing}
      - {name: active, timestamp: activated_at}
      - {name: past_due, timestamp: past_due_at}
      - {name: churned, timestamp: churned_at, terminal: true}
    transitions:
      - [trialing, active]
      - [trialing, churned]
      - [active, past_due]
      - [active, churned]
      - [past_due, churned]
    weights: {trialing: 0.07, active: 0.6, past_due: 0.07, churned: 0.26}
```

## Run it

```bash
pip install "misata[duckdb]"
misata generate -c misata.yaml -o out --attest
```

## What the demo shows

- **A legal history on every subscription.** A churned subscription that
  was active carries its activation date, then its churn date, in that
  order. A trial that churned has no activation date. Nobody has a churn
  date without having churned.
- **Whales.** `sampling: pareto` on the foreign key concentrates payments:
  in this run the top 1% of paying customers bring 32.8% of revenue, and
  the median payment is 339 against a mean of 904.
- **Dates that end today.** Signups run up to today, so "last 30 days"
  filters show something on the day of the demo.
- **Weekly rhythm.** Subscriptions start mostly on weekdays and payments
  dip at weekends, as declared by `weekday_weights`.

## The check

```bash
misata realism out -s misata.yaml
misata audit out -s misata.yaml
```

```text
Realism score 0.96 across 13 checks: 12 pass, 1 warn, 0 fail
Coherence: clean, no reader-visible contradictions.
```

The realism report looks for the tells of generated data with no real data
to compare against: flat weekdays, uniform amounts, every customer with the
same number of orders, emails unrelated to names. The audit checks what a
reader would notice: a churn date on an active subscription, a payment
before its customer existed. The one warning is the weekday rhythm of the
lifecycle's activation dates, which no declaration in this file shapes.

`preset: demo` makes the output depend on the day you run it. Drop the
preset when you need the same bytes every time.
