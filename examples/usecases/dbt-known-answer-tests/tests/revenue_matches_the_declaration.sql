-- The declared answer key: monthly revenue from misata.yaml, split by the
-- declared channel shares. Any row returned is a month the model got wrong.
with declared as (
    select * from (values
        (date '2025-01-01', 82000.00), (date '2025-02-01', 88500.00),
        (date '2025-03-01', 97250.00), (date '2025-04-01', 101000.00),
        (date '2025-05-01', 112400.00), (date '2025-06-01', 125000.00)
    ) as t(month, revenue)
),
modelled as (
    select month, sum(revenue) as revenue
    from {{ ref('fct_monthly_revenue') }}
    group by 1
)
select declared.month, declared.revenue as declared, modelled.revenue as modelled
from declared
left join modelled using (month)
where modelled.revenue is null or abs(modelled.revenue - declared.revenue) > 0.005
