---
title: "Geospatial Realism — Realistic Coordinates, Postal Codes, and Location Data"
description: "Generate latitude/longitude that clusters around real cities, format-correct postal codes, and location data that makes maps look real."
---

# Geospatial Realism

Misata generates location data that makes geographic sense. Coordinates cluster around real cities with natural scatter, postal codes follow correct format patterns, and city/country pairs are consistent.

## Automatic detection

Add columns named `lat`, `latitude`, `lng`, `longitude`, `postal_code`, or `zip_code` and Misata infers the right generator automatically:

```python
from misata.schema import SchemaConfig, Table, Column

schema = SchemaConfig(
    name="Stores",
    tables=[Table(name="stores", row_count=500)],
    columns={"stores": [
        Column(name="store_id",    type="int", unique=True, distribution_params={"min": 1, "max": 501}),
        Column(name="city",        type="text", distribution_params={"text_type": "city"}),
        Column(name="lat",         type="float", distribution_params={"text_type": "latitude"}),
        Column(name="lng",         type="float", distribution_params={"text_type": "longitude"}),
        Column(name="postal_code", type="text", distribution_params={"text_type": "postal_code"}),
    ]},
    relationships=[],
)
```

## How coordinates are generated

Misata has a built-in dataset of 60+ major cities across 20 countries, each with real centroid coordinates. For each row:

1. A city is sampled (uniformly across the pool)
2. A small Gaussian offset is added (~0.25° lat, ~0.35° lng — roughly 20–35 km scatter)
3. Coordinates are rounded to 6 decimal places (~10 cm precision)

This means your data will produce realistic-looking clusters when plotted on a map — not random scattered points.

```python
# Coordinates cluster around real cities:
# Tokyo:     35.6762, 139.6503  ± scatter
# London:    51.5074,  -0.1278  ± scatter
# São Paulo: -23.5505, -46.6333 ± scatter
```

## Postal codes

Misata generates postal codes using the prefix pattern for each city's country:

| Country | Format | Example |
|---|---|---|
| United States | `{2-digit prefix}{3 digits}` | `10472` |
| United Kingdom | `{letter prefix}{digits}` | `EC2847` |
| India | `{3-digit prefix}{3 digits}` | `400315` |
| Germany | `{2-digit prefix}{3 digits}` | `10412` |
| Japan | `{3-digit prefix}{3 digits}` | `100542` |

## Explicit text_type usage

```python
Column(name="latitude",    type="float", distribution_params={"text_type": "latitude"})
Column(name="longitude",   type="float", distribution_params={"text_type": "longitude"})
Column(name="postal_code", type="text",  distribution_params={"text_type": "postal_code"})
```

## Supported cities (sample)

New York, Los Angeles, Chicago, Houston, London, Manchester, Toronto, Vancouver, Berlin, Munich, Mumbai, Delhi, Bangalore, Sydney, Melbourne, Tokyo, Osaka, Paris, São Paulo, Singapore, Dubai, Seoul, Amsterdam, and 40+ more across North America, Europe, Asia, and Oceania.

## Combining with other location columns

For fully consistent location rows, combine with `city` and `country` text types:

```python
columns = [
    Column(name="city",        type="text",  distribution_params={"text_type": "city"}),
    Column(name="country",     type="text",  distribution_params={"text_type": "country"}),
    Column(name="lat",         type="float", distribution_params={"text_type": "latitude"}),
    Column(name="lng",         type="float", distribution_params={"text_type": "longitude"}),
    Column(name="postal_code", type="text",  distribution_params={"text_type": "postal_code"}),
]
```

Note: city/country and lat/lng are sampled independently — for strict geographic consistency within a row, use a custom generator or the correlation engine.
