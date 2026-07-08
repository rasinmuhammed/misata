<!--
SEO meta (for Medium settings / cross-post):
  Title tag:        Synthetic Data for Analytics: Demo Numbers You Can Prove
  Meta description: Analytics, BI, and private equity teams sell trust in numbers but build and demo on data they cannot verify. Synthetic data with a known answer, proven through your pipeline, fixes that.
  Slug:             synthetic-data-for-analytics-companies
  Tags:             Synthetic Data, Analytics, Business Intelligence, Private Equity, SaaS
  Canonical URL:    https://medium.com/p/84ae358d6208  (published under own name, June 2026 — point all cross-posts here)
-->

# You Sell Trust in Numbers. You Demo on Numbers You Can't Trust.

*Synthetic data with a known answer, for analytics, BI, and private equity teams who live or die by the number on the screen.*

Every analytics company is in the business of vouching for numbers. The dashboard says churn is 3.2 percent. The report says revenue grew 41 percent. The model says this account is likely to expand next quarter. People look at those numbers and then they do things: they fire a campaign, they pull a budget, they call a customer, they tell a board. The entire product, whatever the logo on it, is a promise that the number on the screen is the right number.

And almost none of these companies can vouch for the numbers they build and demo on.

This is the quiet contradiction at the center of the analytics business, and once you see it you cannot unsee it. The data you use to develop the dashboard is not the data the dashboard is for. The data you use to demo the product is borrowed, masked, scrubbed, or invented. The data you test the metric layer against has no known answer, so when the metric layer returns a number, you have no way to say whether it is correct. You can only say it ran.

There is a way out of this, and it is not the obvious one. It is not more realistic fake data. It is data whose answer you decided in advance.

## The data whose answer you already know

Start with how data normally arrives. It shows up first, carrying its own truths, and your job is to discover them. You profile it, you chart it, you write tests that hope to catch it misbehaving. The data is the authority. You are the one asking it questions and hoping the answers are stable.

Now turn that around. Instead of receiving data and discovering its truth, you state a truth and let the data assemble itself to honor it. You say, monthly recurring revenue rises from 50,000 dollars in January to 200,000 by December. You say, churn is 7 percent in Q1 and falls to 4 percent after the new onboarding flow ships in Q3. You say, every customer's lifetime value equals the sum of their actual invoices. Then a tool generates thousands of individual rows, customers and subscriptions and invoices and events, whose aggregates land on exactly those targets, with every foreign key resolving and every rollup reconciling.

This is what I have been building with [Misata](https://github.com/rasinmuhammed/misata), an open source Python library, and I want to be honest that I have a stake in the idea. But the idea stands on its own whatever tool you reach for. The shift is small to describe and large in consequence: you write the answer key first, then generate the data around it. For an analytics company, that single property quietly solves a handful of problems the industry has always solved badly.

## Problem one: a demo has to tell a story, and real data refuses to

Watch a great product demo and notice what the data is doing. The churn chart dips right after the feature the rep is describing. The revenue line has a satisfying Black Friday spike. The cohort table shows retention improving down and to the right. The story the salesperson tells with their voice is the same story the data tells on the screen, and the alignment is what makes the demo land.

Now think about where that data came from. There are three usual options and all three are bad.

The first is anonymized production data from a friendly customer. It is real, which is the selling point, but real data is off message. It has the customer's actual messiness, their seasonal quirks, their one enterprise account that distorts every average. It tells the customer's story, not the story you need to tell. And it carries risk, because masked data has a way of remembering things you wish it had forgotten.

The second is a pile of random fake data from a mock-data generator. It is safe and it is fast, but it has no narrative. The churn line is flat noise. The revenue chart wanders. There is no spike, no dip, no improvement after Q3, because random data has no opinion about any of that. You cannot demo a turnaround on data that never turned.

The third is hand-built data, lovingly crafted by some engineer over two days, which works beautifully for exactly one demo until a prospect asks to see a different segment and the whole illusion falls apart, because the cross-table relationships were never real and the moment you slice it differently the numbers stop reconciling.

Declared synthetic data removes the tradeoff. You describe the story you want the data to tell, and the rows arrange themselves to tell it, across every table, with the relationships intact so the prospect can slice it any way they like.

```python
import misata
from misata import from_dict_schema

schema = from_dict_schema({
    # the story: churn starts high and falls after the Q3 onboarding revamp
    "__rate_curves__": [{
        "table": "subscriptions",
        "column": "churned",
        "time_column": "period",
        "time_unit": "month",
        "true_value": True,
        "rate_points": [
            {"period": "2025-01", "rate": 0.071},
            {"period": "2025-06", "rate": 0.068},
            {"period": "2025-09", "rate": 0.042},
            {"period": "2025-12", "rate": 0.038},
        ],
    }],
    # the story: revenue climbs through the year with a Q4 push
    "__outcome_curves__": [{
        "table": "invoices",
        "column": "amount",
        "time_column": "issued_at",
        "time_unit": "month",
        "value_mode": "absolute",
        "start_date": "2025-01-01",
        "avg_transaction_value": 180.0,
        "curve_points": [
            {"month": 1,  "target_value":  50_000.0},
            {"month": 6,  "target_value": 110_000.0},
            {"month": 12, "target_value": 200_000.0},
        ],
    }],
    "customers": {
        "__rows__": 1200,
        "id":    {"type": "integer", "primary_key": True},
        "name":  {"type": "string", "text_type": "name"},
        "plan":  {"type": "categorical", "choices": ["starter", "pro", "enterprise"]},
    },
    "subscriptions": {
        "__rows__": 1500,
        "id":          {"type": "integer", "primary_key": True},
        "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
        "period":      {"type": "date"},
        "churned":     {"type": "boolean"},
    },
    "invoices": {
        "__rows__": 9000,
        "id":          {"type": "integer", "primary_key": True},
        "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
        "amount":      {"type": "float", "min": 20, "max": 4000},
        "issued_at":   {"type": "date"},
    },
}, seed=42)

tables = misata.generate_from_schema(schema)
```

The churn line falls after Q3 because you said it should. The revenue line climbs to 200,000 in December because you said it should. Every invoice belongs to a customer who exists, every subscription too, and when the prospect asks to filter to enterprise accounts the numbers still hold, because the relationships were generated, not faked. You can ship the same demo to your whole sales team and every rep tells the same true story, because the story is baked into the data with a fixed seed and it regenerates identically forever.

## Problem two: you cannot QA a metric you cannot check

This is the one that should keep analytics teams up at night, and it is the one declared data solves most completely.

Your product computes a number. Monthly active users, net revenue retention, attribution by channel, whatever your product is famous for. You want to know it is correct. So you run it against some test data and it returns 3.2 percent. Is that right?

You have no idea. You do not know the true value in your test data, so the output is unfalsifiable. The test confirms the query executed. It cannot confirm the query is correct. A join that silently drops half the rows, a filter that double counts, a timezone bug that smears events across day boundaries, none of these will fail your test, because your test has nothing to compare against. It is checking that the machine produced a number, not that it produced the right number.

Now generate the test data with the answer decided in advance. You declared net revenue retention should be 112 percent for the 2024 cohort. You run your metric layer. If it returns 111.8 percent, your logic is sound: the cohort assignment held, the expansion and contraction netted correctly, the currency conversion behaved. If it returns 96 percent, something in your computation is wrong, and you caught it on a branch, on a laptop, before it ever shipped to a customer who would have made a decision on a false number.

```python
import pandas as pd

# you declared December revenue must total exactly 200,000
inv = tables["invoices"].copy()
inv["month"] = pd.to_datetime(inv["issued_at"]).dt.month
december = inv.loc[inv["month"] == 12, "amount"].sum()

# this is your product's metric layer, whatever it is, run against known-answer data
assert abs(december - 200_000) < 0.01, f"metric layer is wrong: got {december}"
```

That assertion is the difference between a test that says "it ran" and a test that says "it is correct." It is the difference between shipping a metric you hope is right and shipping a metric you have proven is right against a ground truth you authored yourself. For a company whose product is trust in numbers, that is not a nice-to-have. It is the foundation under the thing you sell.

There is a deeper version of this for teams that care. Generate a known-answer dataset, run it through your full transformation stack, and assert that the declared metric survives every layer. Each generation can also emit a proof report covering referential integrity, row counts, constraints, and reproducibility, so the ground truth is not just in your head, it is an artifact you can store in CI and diff across releases.

```python
oracle = misata.build_oracle_report(tables, schema, seed=schema.seed)
assert oracle["passed"]   # FK integrity, row counts, constraints, determinism
```

Wire that into your pipeline and your metric correctness becomes a thing that fails loudly on a pull request, instead of a thing a customer discovers in a board meeting.

## Problem three: proving your product works on data you will never be allowed to see

This is the version with the most money attached to it, and it is the one existing tools cannot touch.

Say your product does not just display numbers, it finds them. You sell a platform that surfaces the KPI that matters: the churn driver, the margin leak, the expansion signal nobody noticed. Or you are a consultancy, or a value-creation team inside a private equity firm, and the whole pitch is that you point your product at a portfolio company's data and tell them the thing they did not know about their own business.

Now try to demo that. The prospect's data is confidential. You will not see it before the deal, and often not after. So you reach for synthetic data to stand in for it, and here the difference between the two kinds of synthetic data becomes the difference between a demo that proves something and a demo that proves nothing.

If you use an imitation tool, the kind that learns from a sample and reproduces its shape, you get data that looks plausible and contains no answer. There is no planted churn driver, because nobody planted one. There is no margin leak to find, because the tool was copying distributions, not designing a business. So when you run it through your product, your product finds nothing in particular, because there was nothing in particular to find. You have not proven your product works. You have proven it runs.

Declared data is built the other way, and that is exactly what this demo needs. You design the business. You decide this company has EBITDA expansion concentrated in one segment, churn that hides a retention problem in a single cohort, headcount growing faster than revenue in one division. You plant the story, with real numbers, across customers and contracts and invoices and headcount, all reconciling. Then you point your product at it. If your product is as good as you say, it surfaces exactly the lever you planted, and the prospect watches it happen on data that is safe to share because it belongs to no one.

That is a demo that proves the product, not one that shows the interface.

But there is a harder bar, and it is the one that separates a real claim from a hopeful one. Does the scripted story survive the pipeline? The demo is worthless if the data only carries the right answer in the raw extract and loses it the moment it runs through Alteryx, dbt, a warehouse model, or whatever crunches it before your product ever sees it. Joins drop rows. Rollups re-aggregate. Time gets re-bucketed. If the planted KPI does not survive all of that, your product reads a number that no longer matches the story you meant to tell, and the demo dies in front of the buyer.

This is where outcome conformance earns its name, and where most generators quietly fail. A generator that simply writes the right total into a summary column has put the answer somewhere a pipeline will overwrite. Misata puts it where a pipeline cannot: every foreign key resolves, every parent summary reconciles to its children to the cent, every monthly curve is exact rather than approximate, so the answer was never sitting in a field waiting to be recomputed. It was distributed truthfully across the rows the whole time. When your pipeline groups, joins, and rolls the data back up, the planted answer is still standing on the other side. The story survives the crunch.

I will be straight about where this stands today, because this audience can smell aspiration from across the room. The primitives that make this possible, exact curves, per-period rates, cross-table rollups, referential integrity, and constraints, exist and work now, and a determined team can hand-script a portfolio scenario from them today. The turnkey layer, the one where you say "a PE-backed B2B SaaS company with EBITDA expansion and a failed Q3 pricing test" and get the whole reconciled world in a single line, is what we are building toward. The value is identified, the foundation is in place, and the convenience on top is the work in progress. I would rather tell you that than have you find out in a demo.

## Problem four: the cold start, when there is no data at all

Every analytics company begins with nothing. No customer, no data, and yet a product to build and a demo to give. The dashboard has to exist before the first account signs. The model has to be trained before there is anything real to train it on. The investor deck needs a screenshot that looks like a thriving business using your tool, months before a thriving business does.

This is the moment most teams reach for whatever fake data they can assemble, and it shows. The early demos look thin because the data is thin. The first model is trained on noise because noise was all there was.

Declared synthetic data covers the cold start honestly. You decide what a healthy account looks like inside your product, the engagement curve, the feature adoption, the expansion pattern, and you generate a whole population of them. Because you set every dial, you know what every downstream number is supposed to say, which means the dashboard you build against it can be checked the same way you would check it in production. You are not just filling space. You are building against a known world.

## But I could just write a Python script

Of course you could. Anyone who knows pandas can write a script that spits out a CSV with the numbers a pitch needs. The question was never whether you can write one. It is how many you are willing to write, and who keeps them alive after you do.

Think about what the second script costs. The first prospect was a SaaS company, so you wrote net revenue retention and cohorts and expansion revenue. The next is a fintech, and now you need fraud rates, chargebacks, account balances. After that comes an insurer who wants loss ratios and claims reserves, then a retailer who wants GMV, returns, and a Black Friday spike. Five sectors, five scripts, and not one of them is just numbers. Each one carries foreign keys that have to resolve, parent totals that have to reconcile with their child rows, dates that have to fall in a sane order, distributions that have to survive a skeptical reviewer, and a planted answer that has to live through your pipeline. That is not a snippet. It is a small unowned product, and it starts to rot the moment your real schema shifts underneath it.

Now hand those scripts to a solutions engineer who is brilliant at demos and was never hired to be a data engineer. Watch a column that got renamed three sprints ago quietly break the fintech demo live, in front of the buyer, because nobody kept the script in step with the product. The cost of the script was the afternoon you spent writing it. The cost of the scripts is everything after: the drift, the rebuilds, the single person who understands them, the demo that fails at the worst possible moment.

Declaring the scenario instead of coding it changes the unit of work. You stop writing generators and start writing specifications. A scenario becomes a short, readable file that states what must be true, the revenue curve, the churn rate, the relationships between the tables, and the engine turns it into rows. It carries across sectors because the vocabulary stays the same even when the story does not. It is reviewable, because a colleague can read the spec and see the claim. It is version controlled, because it is text. And it survives a schema change, because you fix one declaration instead of hunting through twenty scripts.

That is where the return lives. A solutions team that burned days per vertical building and rebuilding demo data spends minutes. A metric bug that would have reached a customer gets caught on a branch. A value-creation thesis gets rehearsed on a safe, reconciling replica before anyone touches the real company. None of that is measured in lines of code saved. It is measured in deals you can demo on the day they appear, in numbers you never had to walk back, in trust you did not have to rebuild.

I am building Misata in the open because the fastest way to make someone believe an idea is to let them hold it. But I will say what I actually think. The full version of this, the one a private equity firm or a serious analytics vendor needs, is larger than an open source library. It is a governed system: scenario libraries a whole team shares, approval and audit trails for what gets generated and shown, connectors into the pipelines you already run, and turnkey domain packs that turn one sentence into a reconciled world. The library is how you learn the value. A system like that is what the value is worth. And the ROI at that level is not an afternoon saved, it is every demo that fell apart, every number that had to be retracted, and every deal that stalled because you could not show the thing working, all of it simply stopping.

## Where this is the wrong tool, said plainly

I would rather lose you here than oversell you, because the honest boundary is part of why this works.

Declared data will not find a bug you did not think to model. If your attribution logic mishandles a channel you never put in the schema, synthetic data built from a clean spec will be innocent of that case, and your product will meet it for the first time in production. Use generated data to prove your logic against known inputs, not to discover the unknown ones. For surfacing the weird real cases, nothing replaces eventually testing against real systems.

It does not replace an integration test against your actual ingestion connectors. It exercises your computation, not your plumbing.

And if your need is a privacy-safe statistical twin of a specific customer's real dataset, that is a different job, the imitation job, where heavier generative synthesizers have spent years. Declared data starts from intent, not from a real table. Some teams want both, and that is fine. Just know which one you are reaching for and why.

## Early on purpose, building toward a solid core

I will not pretend this is finished, because the people who would get the most from it can tell when a roadmap is being sold to them as if it were a product.

Here is the honest map. Misata today is strong where it matters most and earliest, in the guarantees. Exact outcome curves, per-period rates, cross-table rollups that reconcile, referential integrity, constraints that hold on every row, locale-accurate values, and the same seed reproducing the same world byte for byte. Those are the hard, unglamorous things that have to be exactly true for anything else to mean anything, and they work now.

It is early where the convenience lives. The one-line domain scenarios, the turnkey private capital and insurance and fintech worlds, the layer that reads a plain request and routes it to the right guarantees, those are being built, in that order, deliberately. Get the things that must be exactly true exactly true first. Earn the bigger promises only as the engine can carry them without bluffing.

And there is a reason it is open that goes past generosity. Every real use case teaches the core a scenario it should have made trivial. Every sector someone tries to pitch on it, every pipeline someone runs it through, surfaces the next thing worth guaranteeing. We identified the value early. The scenarios that prove out the rest of it will arrive faster from people using it in the wild than from me imagining them alone. If you see the gap I see, the most useful thing you can do is point the tool at your hardest case and tell me exactly where it bends.

## The thing analytics companies are actually selling

Come back to the dashboard that says 3.2 percent. The reason that number is hard to trust during development is not that your engineers are careless. It is that nothing in the test could have told them it was wrong. The data had no opinion about the right answer, so the test could only confirm the machine was running, not that it was right.

What changes, when you generate data on purpose, is that the data starts to carry an opinion. You write down what should be true. The rows arrange themselves around it. And then your product has to earn that truth back out the other end, through every join and filter and rollup, and hand you the number you started with. The test can finally fail for the right reasons. The demo can finally tell the story you mean. The cold start can finally be built against a world you understand.

For most software, that is a convenience. For an analytics company, it is the whole job. You are in the business of vouching for numbers. It is worth being able to vouch for the ones you build on first.

If you want to try it, Misata is `pip install misata`, the source and runnable examples are on [GitHub](https://github.com/rasinmuhammed/misata), and the exact-aggregate mechanism behind the revenue curves is written up in an [arXiv preprint](https://arxiv.org/abs/2606.08736v1). Whatever you use, give the data an answer before you ask the product to find it.
