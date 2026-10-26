select
    date_trunc('month', ordered_at)::date as month,
    channel,
    round(sum(amount), 2) as revenue
from {{ ref('orders') }}
group by 1, 2
