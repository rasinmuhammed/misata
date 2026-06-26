-- stg_subscriptions.sql
-- Staging model: clean and type-cast raw subscription data from seeds.

with source as (
    select * from {{ ref('subscriptions') }}
),

staged as (
    select
        subscription_id,
        user_id,
        plan,
        amount,
        cast(start_date as date) as start_date,

        -- Derive month for aggregation
        date_trunc('month', cast(start_date as date)) as subscription_month

    from source
    where amount > 0  -- Exclude free-tier for MRR calculation
)

select * from staged
