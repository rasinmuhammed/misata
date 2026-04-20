# Supported Domains

Each domain produces a multi-table schema with realistic FK relationships, domain-calibrated distributions, and semantic column types.

## SaaS

**Trigger words:** saas, subscription, mrr, arr, churn

**Tables:** `users`, `subscriptions`

**Notable priors:** MRR follows a lognormal distribution. Churn rate configurable from story ("20% churn"). Outcome curves supported ("MRR rises from $50k in Jan to $200k in Dec").

```python
tables = misata.generate("A SaaS company with 5k users and 20% monthly churn")
```

---

## Ecommerce

**Trigger words:** ecommerce, orders, store, retail, cart

**Tables:** `customers`, `orders`

**Notable priors:** Order amounts are lognormal. Seasonal patterns supported. Customer LTV distribution calibrated.

```python
tables = misata.generate("An ecommerce store with 10k customers and seasonal sales peaks")
```

---

## Fintech

**Trigger words:** fintech, transactions, payments, banking, fraud, loans, credit

**Tables:** `customers`, `accounts`, `transactions`

**Notable priors:** Fraud rate ~2% (configurable). Credit scores follow real FICO distribution (mean ≈700, std ≈75). Transaction amounts lognormal. Account balances lognormal.

```python
tables = misata.generate("A fintech startup with 2k customers, 3% fraud rate")
```

---

## Healthcare

**Trigger words:** healthcare, patients, doctors, hospital, clinic, appointments

**Tables:** `doctors`, `patients`, `appointments`

**Notable priors:** Blood types match real ABO/Rh frequencies. Patient age distribution centred on chronic-care population. Appointment no-show rate ~15%.

```python
tables = misata.generate("A hospital with 500 patients and 50 doctors")
```

---

## HR / Workforce

**Trigger words:** hr, employees, payroll, workforce, hiring, headcount, salaries

**Tables:** `departments`, `employees`, `payroll`

**Notable priors:** Salary is conditional on seniority level (lognormal per role). Performance scores follow a beta distribution (right-skewed toward high performers). Tenure is exponential.

```python
tables = misata.generate("A tech company with 1000 employees and monthly payroll")
```

---

## Real Estate

**Trigger words:** real estate, housing, mortgage, realty

**Tables:** `agents`, `properties`, `transactions`

**Notable priors:** Home prices lognormal (US median ~$410k, heavy right tail). Days-on-market lognormal (median ~23 days). Agent ratings beta-distributed toward high end. ~60% of listings close.

```python
tables = misata.generate("A real estate agency with 200 properties listed")
```

---

## Social Media

**Trigger words:** social media, instagram, tiktok, influencer, followers, feed, reels

**Tables:** `users`, `posts`, `follows`, `reactions`, `comments`

**Notable priors:** Follower counts follow a Pareto (power-law) distribution — a small fraction of accounts capture most reach. Engagement rates beta-distributed (~1–5%). Like/comment/share counts lognormal.

```python
tables = misata.generate("A social media platform with 10k creators and viral content")
```

---

## Marketplace

**Trigger words:** marketplace, sellers, buyers, listings, gig, freelance

**Tables:** `sellers`, `buyers`, `listings`, `orders`

**Notable priors:** Seller ratings beta-distributed. Listing prices lognormal. Order completion rate ~85%.

```python
tables = misata.generate("A freelance marketplace with 500 sellers and 2000 buyers")
```

---

## Logistics

**Trigger words:** logistics, shipping, delivery, fleet, warehouse, routes, drivers

**Tables:** `drivers`, `vehicles`, `routes`, `shipments`

**Notable priors:** Delivery times lognormal. On-time rate ~88%. Route distances lognormal. Driver ratings beta-distributed.

```python
tables = misata.generate("A logistics company with 200 drivers and 50k shipments")
```

---

## No match → generic

If no domain keyword is detected, Misata emits a warning and generates a single generic table. Use explicit domain keywords or switch to `LLMSchemaGenerator` for open-ended stories.
