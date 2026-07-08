---
title: "Synthetic Data for Data Engineering: How to Test a Pipeline Before the Real Data Arrives"
published: false
description: "A field guide to synthetic data for data engineering. Why the most useful synthetic data is not the data that looks real, but the data whose answers you already know."
tags: dataengineering, testing, python, databricks
canonical_url: https://dev.to/<your-handle>/synthetic-data-for-data-engineering
cover_image: ""
---

There is a quiet absurdity at the center of most data work, and once you notice it you cannot stop seeing it.

You are asked to make sure a pipeline is correct. To do that, you need data to run it on. The only data that would truly prove anything is the real data, the production tables with their odd shapes and their long tails and their one customer in Belgium who somehow has forty thousand orders. And that is exactly the data you are not allowed to have. It sits behind an access request, a compliance review, a privacy policy, and a Slack thread that goes quiet after someone says "let me check with legal."

So you build the thing in the dark. You write twenty rows by hand and tell yourself they represent a million. You run a loop of fake names and random numbers and watch your joins quietly drop half the rows because none of the foreign keys point anywhere. You ship, and you wait, and you find out whether you were right when the real data finally lands and something downstream catches fire.

This is the part nobody puts in the job description. Most of data engineering is reasoning about data you cannot look at.

Synthetic data is usually sold as a machine learning trick. Train a model without touching real records. Get around the privacy rules. Pad out a dataset that is too small. All of that is real. But it hides the use that shows up far more often, in the ordinary Tuesday-afternoon work of building and testing pipelines. And the reframe that makes it click is small and a little beautiful.

## The data whose answers you already know

Here is the inversion. Normally data comes first and you spend your life trying to discover its truths. You profile it, you chart it, you write tests that hope to catch it lying. The data is the authority and you are the supplicant.

Generated data flips the direction of that relationship. You state a truth, and the data assembles itself to honor it.

Say you are testing a fraud aggregation. You run your pipeline against some test data and it reports three point one percent fraud last month. Is that correct? You have no idea. You do not know the true fraud rate of your test data, so the number is unfalsifiable. The test can confirm the code ran. It cannot confirm the code is right.

Now turn it around. Generate test data where you decided the fraud rate in advance. One point eight percent in January, climbing to four point one by June. Run the pipeline. If the gold table comes back at one point seven nine and four point oh nine, then your joins held, your filters were honest, your aggregation counted what it was supposed to count. If it comes back at two and a half, something in the middle is dropping or double counting fraud, and you caught it on a laptop, on a branch, before a single real record was at risk.

That is a real test for a data pipeline. Not "did it run" but "is it correct." And you cannot write it with a fake-data loop, because a fake-data loop cannot hand you a target to check against. The value here is not that the data looks real. It is that you wrote the answer key first.

## What this actually does on an ordinary day

A few jobs where this earns its place.

### Proving a pipeline is correct, on every commit

Declare the tables, the relationships between them, and the outcome you care about. Generate. Assert that your transformation reproduces the outcome. Here is the shape of it, using [Misata](https://github.com/rasinmuhammed/misata), an open source library I build (so take the pitch with the appropriate pinch of salt, though the idea holds whatever you reach for):

```python
import misata
from misata import from_dict_schema

schema = from_dict_schema({
    "__rate_curves__": [{
        "table": "transactions", "column": "is_fraud",
        "time_column": "txn_ts", "time_unit": "month", "true_value": True,
        "rate_points": [
            {"period": "2025-01", "rate": 0.018},
            {"period": "2025-06", "rate": 0.041},
        ],
    }],
    "customers": {
        "id": {"type": "integer", "primary_key": True},
        "email": {"type": "email"},
    },
    "transactions": {
        "id": {"type": "integer", "primary_key": True},
        "customer_id": {"type": "integer",
                        "foreign_key": {"table": "customers", "column": "id"}},
        "amount": {"type": "float", "distribution": "lognormal", "mu": 3.4, "sigma": 1.1},
        "txn_ts": {"type": "datetime", "start": "2025-01-01", "end": "2025-06-30"},
        "is_fraud": {"type": "boolean"},
    },
})

tables = misata.generate_from_schema(schema)
```

Every transaction points at a customer who exists. The monthly fraud rate follows the curve you declared. Run your silver and gold transforms on top, then assert the gold output lands on that curve within a tolerance. Wire it into CI and it runs forever, with no access to production and nothing to leak.

### Making a copy of data you have but cannot share

Sometimes the real table is right there on your screen and the problem is the opposite. You need to send it somewhere it should not go. To a vendor, into a public demo, onto the laptop of someone who started on Monday. The job now is a copy that keeps the statistical shape and the relationships between columns while carrying none of the actual rows.

```python
import pandas as pd
import misata

real = pd.read_csv("customers.csv")
synthetic = misata.mimic(real, rows=len(real))["table"]

print(misata.fidelity_report(synthetic, real, target_column="churned").summary())
print(misata.privacy_report(synthetic, real).summary())
```

The two report lines are the point. A copy is only worth using if you can measure that it matches the real distributions and the relationships inside them. It is only worth sharing if you can measure that it is not quietly memorizing real people. Numbers you can put in a pull request, not a feeling you defend in a meeting.

Honesty belongs here too, because this is the hard part of the whole field. Simple tabular structure reproduces beautifully: distributions, correlations between columns, values that shift by category. Complicated nonlinear or geographic structure is genuinely harder, and the right move is to measure the gap rather than pretend it closed. If your need is deep generative fidelity on messy real data, the heavier synthesizers like [SDV](https://github.com/sdv-dev/SDV) have spent years on exactly that.

### Filling the time before the data exists

Two more, quickly. Load testing wants volume with a believable shape, so you can watch a pipeline behave at a hundred million rows before the business actually sends them. And teams before launch have no data at all, yet still have to build the dashboard and train the first model. Declared synthetic data covers both, and since you set the dials, you know what every downstream number is supposed to say.

## Where it is the wrong tool, plainly

It will not find a bug you did not think to model. If an upstream system encodes dates in a way nobody documented, synthetic data built from a clean schema will be innocent of that sin, and your pipeline will meet it for the first time in production. Use generated data to prove your logic against known inputs, not to discover the unknown.

It does not replace an integration test against the real source systems. It exercises your transformations, not your connectors.

And a copy learned from real data is still a descendant of real data. Measure the privacy distance before you hand it over. Assume nothing.

## The small wonder of it

Come back to that two in the morning feeling, the green pipeline you did not trust. The reason you did not trust it was that nothing in the test could have told you it was wrong. The data had no opinion about the right answer.

What changes, when you generate data on purpose, is that the data starts to carry an opinion. You write down what should be true, the rows arrange themselves around it, and then your pipeline has to earn that truth back out the other end. The test can finally fail for the right reasons. That is a strange and slightly wonderful thing to be able to do, to know the answer before the data exists, and it turns the loneliest part of data engineering, reasoning in the dark about tables you cannot see, into something you can actually check.

If you want to try the examples, Misata is `pip install misata`, and there are runnable Databricks notebooks in the [repository](https://github.com/rasinmuhammed/misata). Whatever you use, give your pipelines a test that knows the answer.
