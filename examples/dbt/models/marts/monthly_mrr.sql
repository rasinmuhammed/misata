-- monthly_mrr.sql
-- Mart model: calculate Monthly Recurring Revenue (MRR).
--
-- This is the model you'd test with Misata's known-answer pattern:
-- declare the expected MRR curve, generate data that hits those targets,
-- then assert this model's output matches the declared values.

with subscriptions as (
    select * from {{ ref('stg_subscriptions') }}
),

monthly_mrr as (
    select
        subscription_month,
        count(distinct user_id) as active_subscribers,
        sum(amount)             as total_mrr,
        avg(amount)             as avg_revenue_per_user

    from subscriptions
    group by subscription_month
)

select
    subscription_month,
    active_subscribers,
    total_mrr,
    avg_revenue_per_user,

    -- Month-over-month growth
    total_mrr - lag(total_mrr) over (order by subscription_month) as mrr_change,
    case
        when lag(total_mrr) over (order by subscription_month) > 0
        then (total_mrr - lag(total_mrr) over (order by subscription_month))
             / lag(total_mrr) over (order by subscription_month) * 100
        else null
    end as mrr_growth_pct

from monthly_mrr
order by subscription_month
