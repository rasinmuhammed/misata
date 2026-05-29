---
title: Generate Logistics & Supply Chain Synthetic Data in Python | Misata
description: Generate realistic logistics synthetic datasets in Python — drivers, vehicles, routes, and shipments with delivery time coherence, on-time rates, and fleet management distributions. No real fleet data required.
---

# Generate Logistics and Supply Chain Synthetic Data in Python

Logistics data connects physical assets — vehicles, drivers, and routes — with time-sensitive operations like shipments and deliveries. Building a fleet management system, training a route optimization model, or developing a supply chain analytics dashboard requires data where `delivered_at` is always after `shipped_at`, driver ratings are realistic, and route distances follow the right distribution. Misata generates all of it in one call.

The logistics domain generates four interconnected tables: drivers assigned to vehicles, shipments assigned to routes and drivers, all with FK integrity and realistic temporal constraints. On-time delivery rate is ~88% by default and configurable from your story.

```python
import misata

tables = misata.generate("A logistics company with 200 drivers and 50k shipments", rows=1000, seed=42)
print(list(tables.keys()))   # ['drivers', 'vehicles', 'routes', 'shipments']
print(tables["shipments"][["status", "weight_kg"]].describe())
```

## What Misata generates

Four tables: `drivers` → `vehicles`, `routes`, `shipments` (which reference both routes and drivers). Every shipment has a valid driver and route reference; temporal columns are always coherent.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `drivers` | `driver_id`, `name`, `license_type`, `rating`, `hire_date`, `vehicle_id` |
| `vehicles` | `vehicle_id`, `type`, `plate`, `capacity_kg`, `year`, `status` |
| `routes` | `route_id`, `origin`, `destination`, `distance_km`, `duration_hours`, `cost` |
| `shipments` | `shipment_id`, `route_id`, `driver_id`, `weight_kg`, `status`, `shipped_at`, `delivered_at` |

### Realistic distributions

- **On-time rate** is ~88% — configurable via story (`"95% on-time rate"`, `"frequent delays"`)
- **`delivered_at`** is always after `shipped_at` — enforced, not probabilistic
- **Route distances** lognormal — right mix of short urban hauls and long-distance routes
- **Driver ratings** beta-distributed in the 4.0–5.0 range — reflecting how platform ratings cluster high
- **Vehicle capacity** matches vehicle type — light vans have lower capacity than heavy trucks

## Quick start

```python
import misata
import pandas as pd

tables = misata.generate(
    "A logistics company with 300 drivers, mixed fleet, 10k shipments",
    rows=1000,
    seed=42,
)

# Verify temporal coherence
shipments = tables["shipments"].copy()
shipped = pd.to_datetime(shipments["shipped_at"])
delivered = pd.to_datetime(shipments["delivered_at"])
completed = shipments["status"] == "delivered"
assert (delivered[completed] >= shipped[completed]).all()

# On-time performance
on_time = shipments[shipments["status"] == "delivered"].shape[0]
total = shipments.shape[0]
print(f"On-time rate: {on_time/total:.1%}")
```

## Common use cases

- **Route optimization model training** — generate training data with distance, duration, cost, and driver ratings for last-mile delivery optimization
- **Fleet management dashboard development** — build vehicle utilization, driver performance, and route efficiency dashboards before your telematics data is connected
- **Supply chain simulation** — test warehouse management logic against thousands of inbound and outbound shipments with realistic weight and timing distributions
- **Delivery SLA monitoring** — validate your alerting and escalation logic against shipments in all status states (in transit, delayed, delivered, failed)
- **Driver scoring algorithm testing** — generate driver histories with varied ratings and delivery completion rates
- **Logistics ERP integration testing** — seed test databases with full driver-vehicle-route-shipment hierarchies for API validation

## Advanced: delay scenario modeling

```python
tables = misata.generate(
    "Logistics company with 500 drivers — delivery delays in December due to holiday volume surge, "
    "on-time rate drops to 70% in December, back to 90% in January",
    rows=2000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# German logistics — German city names, EU routes, EUR costs
tables = misata.generate("German parcel delivery company with 200 drivers, EU routes", rows=1000)

# Indian logistics — Indian cities, INR pricing, mixed vehicle types
tables = misata.generate("Indian last-mile delivery company with 300 drivers", rows=1500)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Logistics company with 500 drivers",
    min_quality_score=85,
    smart_correlations=True,  # auto-correlates distance↔duration, weight↔cost
    rows=2000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Localisation](../localisation.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
