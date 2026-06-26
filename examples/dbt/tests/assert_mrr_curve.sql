-- Known-answer test.
--
-- The monthly_mrr model must reproduce the declared MRR curve
-- (seeds/expected_mrr.csv) to the cent. A dbt singular test passes when it
-- returns zero rows, so this fails the build the moment any month deviates.
--
-- This is the whole point of the pattern: the answer was declared in
-- misata.yaml before the data existed, so the test can prove the model's math
-- is correct, not merely that it ran.

with actual as (
    select
        cast(subscription_month as date) as subscription_month,
        total_mrr
    from {{ ref('monthly_mrr') }}
),

expected as (
    select
        cast(subscription_month as date) as subscription_month,
        expected_mrr
    from {{ ref('expected_mrr') }}
)

select
    e.subscription_month,
    e.expected_mrr,
    a.total_mrr,
    abs(coalesce(a.total_mrr, 0) - e.expected_mrr) as abs_error
from expected e
left join actual a on a.subscription_month = e.subscription_month
where abs(coalesce(a.total_mrr, 0) - e.expected_mrr) > 0.01
