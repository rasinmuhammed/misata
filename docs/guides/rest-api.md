---
title: "REST API — Generate Synthetic Data Over HTTP"
description: "Use misata serve to expose a POST /generate endpoint. Send a story, get JSON tables back. Works with any language — JavaScript, Go, Ruby, curl."
---

# REST API

`misata serve` exposes a lightweight HTTP API that accepts a plain-English story and returns synthetic data as JSON. Any language that can make an HTTP request can use Misata — no Python required.

## Start the server

```bash
misata serve
# Listening on http://0.0.0.0:8000
# API docs: http://localhost:8000/docs
```

Custom host/port:

```bash
misata serve --port 3001 --host 127.0.0.1
```

## POST /generate

The primary endpoint. Send a story, get tables back.

**Request:**

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "story": "SaaS company with users and subscriptions",
    "rows": 500
  }'
```

**Response:**

```json
{
  "tables": {
    "users": [
      {"user_id": 1, "email": "wei.smith@gmail.com", "plan": "pro", ...},
      {"user_id": 2, "email": "priya.jones@outlook.com", "plan": "free", ...}
    ],
    "subscriptions": [
      {"sub_id": 1, "user_id": 1, "mrr": 149.0, "status": "active", ...}
    ]
  },
  "meta": {
    "domain": "saas",
    "story": "SaaS company with users and subscriptions",
    "row_counts": {"users": 500, "subscriptions": 1500}
  }
}
```

## Request schema

| Field | Type | Default | Description |
|---|---|---|---|
| `story` | string | required | Plain-English dataset description |
| `rows` | int | `1000` | Row count for the primary table |
| `seed` | int | `null` | Random seed for reproducible output |
| `format` | string | `"records"` | `"records"` (list of objects) or `"columns"` (dict of arrays) |

## Column-oriented format

Useful for charting libraries that expect arrays:

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"story": "gaming leaderboard", "rows": 100, "format": "columns"}'
```

```json
{
  "tables": {
    "players": {
      "player_id": [1, 2, 3, ...],
      "username":  ["shadow_42", "nova_x", ...],
      "level":     [34, 12, 67, ...]
    }
  }
}
```

## JavaScript / fetch

```javascript
const response = await fetch("http://localhost:8000/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    story: "food delivery app with restaurants and orders",
    rows: 200,
  }),
});

const { tables, meta } = await response.json();
console.log(`Generated ${meta.row_counts.orders} orders`);
console.log(tables.orders[0]);
```

## Go

```go
import (
    "bytes"
    "encoding/json"
    "net/http"
)

body, _ := json.Marshal(map[string]any{
    "story": "ecommerce store with 500 products",
    "rows":  500,
})
resp, _ := http.Post(
    "http://localhost:8000/generate",
    "application/json",
    bytes.NewBuffer(body),
)
// decode resp.Body as JSON
```

## Reproducibility

```bash
curl -X POST http://localhost:8000/generate \
  -d '{"story": "fintech transactions", "rows": 1000, "seed": 42}'
# Same seed → same data every call
```

## Health check

```bash
curl http://localhost:8000/api/health
# {"status": "healthy", "groq_configured": false, ...}
```

## Interactive docs

When the server is running, visit `http://localhost:8000/docs` for a full Swagger UI where you can try all endpoints interactively.

## All available endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/generate` | Story → JSON data (no API key) |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/generate-schema` | Story → schema JSON (LLM) |
| `POST` | `/api/generate-data` | Schema JSON → data |
| `GET` | `/docs` | Swagger UI |
