---
title: 18 Supported Domains — Misata Synthetic Data Generator
description: Misata generates realistic multi-table synthetic data for 18 business domains — SaaS, fintech, ecommerce, healthcare, HR, logistics, social, real estate, pharma, food delivery, edtech, gaming, CRM, crypto, insurance, travel, and streaming.
---

# Supported Domains

Misata detects your domain from the story and applies a pre-built schema with realistic FK relationships, domain-calibrated distributions, and semantic column types. Every domain generates data that passes referential integrity checks out of the box.

**How detection works:** each domain has a set of trigger keywords. The domain whose keywords appear most in the story wins. The literal domain name (e.g. `"saas"`, `"fintech"`) scores +5 points — always enough to override ambiguous keyword matches.

---

## SaaS

**Trigger keywords:** `saas`, `subscription`, `mrr`, `arr`, `churn`

**Tables:** `users`, `subscriptions`, `invoices`

| Table | Key columns |
|:--|:--|
| `users` | `user_id`, `name`, `email`, `plan`, `signup_date`, `country`, `is_active` |
| `subscriptions` | `subscription_id`, `user_id`, `plan`, `mrr`, `start_date`, `status`, `churned_at` |
| `invoices` | `invoice_id`, `subscription_id`, `amount`, `invoice_date`, `status` |

**Distributions:** MRR is lognormal (median ~$150/mo). Churn rate configurable from story. `churned_at` is only set for churned subscriptions. Plan distribution: free 55%, pro 30%, enterprise 15%.

**Narrative support:** MRR outcome curves — monthly anchors, quarterly patterns, multipliers, and named events all work on the `subscriptions.mrr` column.

```python
import misata

# Basic
tables = misata.generate("A SaaS company with 5k users and 20% monthly churn")

# With narrative curve
tables = misata.generate(
    "SaaS startup — MRR from $50k in Jan to $200k in Dec, Q3 slump, doubled by year end",
    rows=5000, seed=42
)
print(tables["subscriptions"][["mrr", "start_date"]].head())
```

---

## Ecommerce

**Trigger keywords:** `ecommerce`, `e-commerce`, `orders`, `cart`, `store`, `retail`, `shop`

**Tables:** `customers`, `products`, `orders`, `order_items`

| Table | Key columns |
|:--|:--|
| `customers` | `customer_id`, `name`, `email`, `city`, `country`, `signup_date`, `lifetime_value` |
| `products` | `product_id`, `name`, `category`, `price`, `cost`, `stock_count`, `rating` |
| `orders` | `order_id`, `customer_id`, `amount`, `status`, `ordered_at`, `shipped_at`, `delivered_at` |
| `order_items` | `item_id`, `order_id`, `product_id`, `quantity`, `unit_price`, `discount` |

**Distributions:** Order amounts lognormal (median ~$85). `shipped_at` is always after `ordered_at`; `delivered_at` always after `shipped_at`. ~88% of orders are delivered; ~8% returned.

**Narrative support:** Revenue and order volume curves. Named events (Black Friday, Christmas) are especially effective here.

```python
tables = misata.generate(
    "Ecommerce store with 10k customers — Black Friday spike, Christmas peak, Q1 slump",
    rows=10_000, seed=42
)
```

---

## Fintech

**Trigger keywords:** `fintech`, `transactions`, `payments`, `wallet`, `banking`, `loans`, `credit`, `fraud`

**Tables:** `customers`, `accounts`, `transactions`

| Table | Key columns |
|:--|:--|
| `customers` | `customer_id`, `name`, `email`, `date_of_birth`, `credit_score`, `kyc_status`, `country` |
| `accounts` | `account_id`, `customer_id`, `account_type`, `balance`, `currency`, `iban`, `opened_at` |
| `transactions` | `transaction_id`, `account_id`, `amount`, `type`, `status`, `is_fraud`, `transaction_date`, `merchant` |

**Distributions:** Credit scores lognormal centred on FICO mean (~700, σ=75). Fraud rate ~2% (configurable: `"3% fraud rate"`). Transaction amounts lognormal. IBAN format follows locale (DE: `DE##...`, BR: `BR##...`).

```python
tables = misata.generate(
    "Brazilian fintech with 2k customers, R$ payments, CPF verification, 3% fraud rate",
    rows=2000, seed=42
)
print(tables["customers"][["name", "credit_score", "country"]].head())
print(tables["transactions"][["amount", "is_fraud", "transaction_date"]].head())
```

---

## Healthcare

**Trigger keywords:** `healthcare`, `health`, `patients`, `doctors`, `hospital`, `clinic`, `appointments`, `medical`

**Tables:** `doctors`, `patients`, `appointments`

| Table | Key columns |
|:--|:--|
| `doctors` | `doctor_id`, `name`, `specialty`, `department`, `years_experience`, `rating` |
| `patients` | `patient_id`, `name`, `date_of_birth`, `blood_type`, `gender`, `diagnosis`, `insurance_provider` |
| `appointments` | `appointment_id`, `patient_id`, `doctor_id`, `scheduled_at`, `duration_minutes`, `status`, `notes` |

**Distributions:** Blood types match real ABO/Rh frequencies (O+ 37.4%, A+ 35.7%, B+ 8.5%, …). Patient ages centred on chronic-care population (μ=52, σ=18). No-show rate ~15%. Doctor specialties drawn from realistic distribution (internal medicine, cardiology, orthopedics, …).

```python
tables = misata.generate("A hospital with 500 patients and 50 doctors", rows=500, seed=42)
print(tables["patients"][["blood_type", "diagnosis"]].value_counts().head())
```

---

## Marketplace

**Trigger keywords:** `marketplace`, `gig`, `freelance`, `sellers`, `buyers`, `listings`

**Tables:** `sellers`, `buyers`, `listings`, `orders`

| Table | Key columns |
|:--|:--|
| `sellers` | `seller_id`, `name`, `email`, `rating`, `total_sales`, `joined_at`, `country` |
| `buyers` | `buyer_id`, `name`, `email`, `total_spent`, `joined_at` |
| `listings` | `listing_id`, `seller_id`, `title`, `category`, `price`, `status`, `created_at` |
| `orders` | `order_id`, `buyer_id`, `listing_id`, `amount`, `status`, `created_at`, `completed_at` |

**Distributions:** Seller ratings beta-distributed (skewed toward 4–5 stars). Listing prices lognormal. Order completion rate ~85%. Seller volume follows power-law (few top sellers, many occasional ones).

```python
tables = misata.generate("A freelance marketplace with 500 sellers and 2000 buyers")
```

---

## Logistics

**Trigger keywords:** `logistics`, `shipping`, `delivery`, `fleet`, `warehouse`, `supply chain`, `routes`, `drivers`

**Tables:** `drivers`, `vehicles`, `routes`, `shipments`

| Table | Key columns |
|:--|:--|
| `drivers` | `driver_id`, `name`, `license_type`, `rating`, `hire_date`, `vehicle_id` |
| `vehicles` | `vehicle_id`, `type`, `plate`, `capacity_kg`, `year`, `status` |
| `routes` | `route_id`, `origin`, `destination`, `distance_km`, `duration_hours`, `cost` |
| `shipments` | `shipment_id`, `route_id`, `driver_id`, `weight_kg`, `status`, `shipped_at`, `delivered_at` |

**Distributions:** Delivery times lognormal. On-time rate ~88%. Route distances lognormal. Driver ratings beta-distributed (4.0–5.0 range).

```python
tables = misata.generate("A logistics company with 200 drivers and 50k shipments")
```

---

## HR / Workforce

**Trigger keywords:** `hr`, `human resources`, `employees`, `payroll`, `workforce`, `hiring`, `headcount`, `salaries`, `onboarding`

**Tables:** `departments`, `employees`, `payroll`

| Table | Key columns |
|:--|:--|
| `departments` | `department_id`, `name`, `head_count`, `budget`, `location` |
| `employees` | `employee_id`, `department_id`, `name`, `email`, `role`, `seniority`, `hire_date`, `date_of_birth`, `salary`, `tenure_years` |
| `payroll` | `payroll_id`, `employee_id`, `period_start`, `gross_pay`, `tax_withheld`, `net_pay`, `pay_type` |

**Coherence rules:** `hire_date` is always after `date_of_birth + 18 years` and never in the future. `tenure_years` is derived from `hire_date` on the same row — no separate random distribution. `net_pay = gross_pay × (1 − tax_withheld)` is formula-consistent row by row.

**Distributions:** Salary lognormal by seniority (junior ~$65k, mid ~$95k, senior ~$140k, lead ~$180k). Tax rate Beta(3, 7) clipped to 18–40%.

```python
tables = misata.generate(
    "A tech company with 1000 employees, monthly payroll, and 4 departments",
    rows=1000, seed=42
)
# tenure_years derived from hire_date — no employees have negative tenure
print(tables["employees"][["role", "salary", "tenure_years"]].describe())
```

---

## Social Media

**Trigger keywords:** `social media`, `instagram`, `tiktok`, `twitter`, `feed`, `followers`, `likes`, `influencer`, `content creator`, `reels`

**Tables:** `users`, `posts`, `follows`, `reactions`, `comments`

| Table | Key columns |
|:--|:--|
| `users` | `user_id`, `username`, `display_name`, `bio`, `follower_count`, `following_count`, `is_verified`, `joined_at` |
| `posts` | `post_id`, `user_id`, `caption`, `media_type`, `like_count`, `comment_count`, `share_count`, `posted_at` |
| `follows` | `follow_id`, `follower_id`, `followee_id`, `followed_at` |
| `reactions` | `reaction_id`, `post_id`, `user_id`, `type`, `reacted_at` |
| `comments` | `comment_id`, `post_id`, `user_id`, `text`, `parent_comment_id`, `posted_at` |

**Distributions:** Follower counts follow a Pareto (power-law) — a small fraction of accounts captures most reach. Engagement rates beta-distributed (~1–5%). Captions are realistic social media text with hashtags and emoji, not lorem ipsum.

```python
tables = misata.generate("A social media app with 10k creators, posts, and viral content")
```

---

## Real Estate

**Trigger keywords:** `real estate`, `realty`, `housing`, `mortgage`, `homes for sale`, `property listing`

**Tables:** `agents`, `properties`, `transactions`

| Table | Key columns |
|:--|:--|
| `agents` | `agent_id`, `name`, `email`, `agency`, `rating`, `listings_sold`, `years_experience` |
| `properties` | `property_id`, `agent_id`, `address`, `city`, `state`, `price`, `bedrooms`, `bathrooms`, `sqft`, `listing_date`, `status` |
| `transactions` | `transaction_id`, `property_id`, `buyer_name`, `sale_price`, `close_date`, `commission_rate`, `days_on_market` |

**Distributions:** Home prices lognormal (US median ~$410k, heavy right tail). Days-on-market lognormal (median ~23 days). Agent ratings beta-distributed (skewed toward 4–5). ~60% of listings close.

```python
tables = misata.generate("A real estate agency with 500 properties and 50 agents")
print(tables["properties"][["price", "bedrooms", "status"]].describe())
```

---

## Pharma / Research

**Trigger keywords:** `pharma`, `research`, `clinical`, `trials`, `timesheet`

**Tables:** `researchers`, `projects`, `trials`, `timesheets`

| Table | Key columns |
|:--|:--|
| `researchers` | `researcher_id`, `name`, `email`, `department`, `seniority`, `publications` |
| `projects` | `project_id`, `name`, `status`, `phase`, `budget`, `start_date`, `end_date` |
| `trials` | `trial_id`, `project_id`, `phase`, `participants`, `success_rate`, `duration_weeks` |
| `timesheets` | `timesheet_id`, `researcher_id`, `project_id`, `week_start`, `hours_logged`, `task_type` |

```python
tables = misata.generate("A pharma research company with 200 researchers and clinical trials")
```

---

## Food Delivery

**Trigger keywords:** `food delivery`, `ubereats`, `doordash`, `grubhub`, `restaurant delivery`, `meal delivery`, `takeout`, `restaurants`, `menu items`

**Tables:** `restaurants`, `customers`, `couriers`, `orders`, `order_items`

| Table | Key columns |
|:--|:--|
| `restaurants` | `restaurant_id`, `name`, `cuisine`, `city`, `rating`, `avg_prep_time`, `is_active` |
| `customers` | `customer_id`, `name`, `email`, `phone`, `city`, `joined_at` |
| `couriers` | `courier_id`, `name`, `vehicle_type`, `rating`, `deliveries_completed` |
| `orders` | `order_id`, `customer_id`, `restaurant_id`, `courier_id`, `total_amount`, `delivery_fee`, `status`, `placed_at`, `delivered_at` |
| `order_items` | `item_id`, `order_id`, `name`, `quantity`, `unit_price` |

**Coherence rules:** `delivered_at` is always after `placed_at` — no negative delivery times. Cuisines drawn from realistic distribution (pizza, sushi, burgers, indian, chinese, …).

```python
tables = misata.generate(
    "A food delivery app with 500 restaurants, 2k customers, and 1k couriers"
)
```

---

## EdTech

**Trigger keywords:** `edtech`, `e-learning`, `lms`, `courses`, `students`, `instructors`, `lessons`, `enrollments`, `quizzes`, `learning platform`

**Tables:** `instructors`, `courses`, `students`, `enrollments`, `quiz_attempts`

| Table | Key columns |
|:--|:--|
| `instructors` | `instructor_id`, `name`, `email`, `specialty`, `rating`, `courses_taught` |
| `courses` | `course_id`, `instructor_id`, `title`, `category`, `price`, `difficulty`, `duration_hours`, `rating` |
| `students` | `student_id`, `name`, `email`, `country`, `joined_at`, `total_courses_enrolled` |
| `enrollments` | `enrollment_id`, `student_id`, `course_id`, `enrolled_at`, `completion_pct`, `completed_at`, `certificate_issued` |
| `quiz_attempts` | `attempt_id`, `enrollment_id`, `quiz_name`, `score`, `passed`, `attempted_at` |

**Narrative support:** Enrollment curves support `back to school` surge (August) and `New Year` spike (January).

```python
tables = misata.generate(
    "An edtech platform with 5k students, 200 courses — back to school surge, New Year spike"
)
```

---

## Gaming

**Trigger keywords:** `gaming`, `game`, `players`, `leaderboard`, `achievements`, `quests`, `guilds`, `matches`, `sessions`, `levels`, `esports`, `rpg`

**Tables:** `players`, `matches`, `sessions`, `achievements`

| Table | Key columns |
|:--|:--|
| `players` | `player_id`, `username`, `level`, `xp`, `rank`, `country`, `joined_at`, `last_active` |
| `matches` | `match_id`, `game_mode`, `map`, `duration_seconds`, `winner_team`, `started_at` |
| `sessions` | `session_id`, `player_id`, `match_id`, `kills`, `deaths`, `assists`, `score`, `result` |
| `achievements` | `achievement_id`, `player_id`, `name`, `category`, `unlocked_at`, `points` |

**Distributions:** Player levels follow a right-skewed lognormal (most players are low-level). XP follows Pareto. K/D ratio beta-distributed around 1.0.

```python
tables = misata.generate("A gaming platform with 10k players, matches, and leaderboards")
```

---

## CRM

**Trigger keywords:** `crm`, `salesforce`, `hubspot`, `contacts`, `deals`, `pipeline`, `leads`, `opportunities`, `sales pipeline`

**Tables:** `companies`, `contacts`, `deals`, `activities`

| Table | Key columns |
|:--|:--|
| `companies` | `company_id`, `name`, `industry`, `size`, `country`, `revenue`, `website` |
| `contacts` | `contact_id`, `company_id`, `name`, `email`, `phone`, `title`, `lead_source`, `created_at` |
| `deals` | `deal_id`, `contact_id`, `company_id`, `name`, `value`, `stage`, `probability`, `close_date`, `owner` |
| `activities` | `activity_id`, `deal_id`, `contact_id`, `type`, `subject`, `outcome`, `activity_date` |

**Distributions:** Deal values lognormal (median ~$25k). Pipeline stages: prospecting 35%, qualification 25%, proposal 20%, negotiation 12%, closed-won 8%. Activity types: email 40%, call 30%, meeting 20%, demo 10%.

```python
tables = misata.generate("A CRM with 500 companies, contacts, deals pipeline, and activities")
print(tables["deals"][["stage", "value", "probability"]].groupby("stage").mean())
```

---

## Crypto / Web3

**Trigger keywords:** `crypto`, `blockchain`, `web3`, `defi`, `nft`, `ethereum`, `bitcoin`, `solana`, `smart contract`, `dex`, `dao`

**Tables:** `wallets`, `tokens`, `transactions`, `token_prices`

| Table | Key columns |
|:--|:--|
| `wallets` | `wallet_id`, `address`, `chain`, `balance_usd`, `created_at`, `wallet_type` |
| `tokens` | `token_id`, `symbol`, `name`, `chain`, `contract_address`, `market_cap` |
| `transactions` | `tx_id`, `wallet_id`, `token_id`, `tx_hash`, `type`, `amount`, `gas_fee`, `timestamp`, `status` |
| `token_prices` | `price_id`, `token_id`, `price_usd`, `volume_24h`, `market_cap`, `recorded_at` |

**Distributions:** Wallet addresses are hex-format (40 chars, `0x` prefix). Gas fees lognormal. Token prices lognormal with high variance. Transaction types: transfer 60%, swap 25%, stake 10%, bridge 5%.

```python
tables = misata.generate(
    "A crypto exchange with wallets, blockchain transactions, and token prices",
    rows=2000, seed=42
)
print(tables["wallets"][["chain", "balance_usd"]].groupby("chain").describe())
```

---

## Insurance

**Trigger keywords:** `insurance`, `policy`, `claim`, `premium`, `coverage`, `underwriting`, `actuary`, `policyholder`

**Tables:** `customers`, `policies`, `claims`, `payments`

| Table | Key columns |
|:--|:--|
| `customers` | `customer_id`, `name`, `email`, `date_of_birth`, `gender`, `state`, `credit_score` |
| `policies` | `policy_id`, `customer_id`, `type`, `premium`, `coverage_amount`, `start_date`, `end_date`, `status` |
| `claims` | `claim_id`, `policy_id`, `incident_date`, `claim_date`, `amount`, `status`, `description` |
| `payments` | `payment_id`, `policy_id`, `amount`, `payment_date`, `method`, `status` |

**Distributions:** Premiums lognormal by policy type (auto ~$1.2k/yr, home ~$1.5k/yr, life ~$800/yr). Claim rate ~8% of active policies. Coverage amounts lognormal (heavy right tail).

```python
tables = misata.generate("An insurance company with 2k customers, policies, and claims")
print(tables["claims"][["status", "amount"]].groupby("status").describe())
```

---

## Travel

**Trigger keywords:** `travel`, `hotel`, `flights`, `bookings`, `airline`, `airbnb`, `booking.com`, `expedia`, `hospitality`, `reservations`, `trips`

**Tables:** `users`, `hotels`, `flights`, `bookings`, `reviews`

| Table | Key columns |
|:--|:--|
| `users` | `user_id`, `name`, `email`, `country`, `loyalty_tier`, `joined_at` |
| `hotels` | `hotel_id`, `name`, `city`, `country`, `stars`, `price_per_night`, `total_rooms` |
| `flights` | `flight_id`, `origin`, `destination`, `airline`, `departure_at`, `arrival_at`, `seat_class`, `price` |
| `bookings` | `booking_id`, `user_id`, `hotel_id`, `flight_id`, `check_in`, `check_out`, `total_price`, `status`, `cancellation_reason` |
| `reviews` | `review_id`, `booking_id`, `rating`, `title`, `body`, `reviewed_at` |

**Coherence rules:** `cancellation_reason` is `null` for non-cancelled bookings. Hotel `check_out` is always after `check_in`. Flight `arrival_at` is always after `departure_at`. Airport codes are realistic IATA format.

```python
tables = misata.generate(
    "A travel booking platform with 5k users, hotels, and international flights",
    rows=5000, seed=42
)
# cancellation_reason is only non-null for cancelled bookings
cancelled = tables["bookings"][tables["bookings"]["status"] == "cancelled"]
print(cancelled["cancellation_reason"].value_counts())
```

---

## Streaming

**Trigger keywords:** `streaming`, `netflix`, `spotify`, `watch history`, `content library`, `subscribers`, `watchlist`, `episodes`, `series`, `vod`, `ott`

**Tables:** `subscribers`, `content`, `watch_history`, `ratings`

| Table | Key columns |
|:--|:--|
| `subscribers` | `subscriber_id`, `name`, `email`, `plan`, `country`, `joined_at`, `is_churned`, `churned_at` |
| `content` | `content_id`, `title`, `type`, `genre`, `release_year`, `duration_minutes`, `rating`, `language` |
| `watch_history` | `view_id`, `subscriber_id`, `content_id`, `watched_at`, `watch_duration_minutes`, `completed`, `device` |
| `ratings` | `rating_id`, `subscriber_id`, `content_id`, `score`, `rated_at` |

**Coherence rules:** `churned_at` is `null` for active subscribers (`is_churned = false`). Content types: series 55%, movie 35%, documentary 10%. Watch completion rate ~65% for movies, ~45% per episode for series.

```python
tables = misata.generate(
    "A Netflix-like streaming service with 10k subscribers and a content library"
)
# churned_at is null for all active subscribers
active = tables["subscribers"][~tables["subscribers"]["is_churned"]]
assert active["churned_at"].isna().all()
```

---

## No match → generic table

If no domain keyword is detected, Misata emits a warning and generates a single generic table with inferred columns. A `DetectionReport` is returned with `domain_confidence: "none"` and an actionable warning message.

```python
report = misata.preview("quarterly sales data by region")
# ⚠ No domain detected — domain_confidence: "none"
# warnings: ["No domain detected. Falling back to a generic single-table schema..."]
```

**Fix options:**
1. Add a domain keyword: `"quarterly sales data by region — fintech"` or `"ecommerce quarterly sales by region"`
2. Use `LLMSchemaGenerator` for fully open-ended stories
3. Author a `misata.yaml` directly for complete control

---

## Combining domains with narrative curves

Every domain supports outcome curves on its primary metric column:

| Domain | Curve column | Table |
|:--|:--|:--|
| SaaS | `mrr` | `subscriptions` |
| Ecommerce | `amount` | `orders` |
| Fintech | `amount` | `transactions` |
| Healthcare | `duration_minutes` | `appointments` |
| HR | `gross_pay` | `payroll` |
| Marketplace | `amount` | `orders` |
| Logistics | `cost` | `shipments` |
| Real estate | `sale_price` | `transactions` |
| EdTech | revenue signals | `enrollments` |

```python
# SaaS with a full growth narrative
tables = misata.generate(
    "SaaS company with 5k users — MRR from $50k in Jan, strong Q4, doubled by December",
    rows=5000, seed=42
)
```

[Full narrative patterns reference →](generation/story.md#narrative-growth-curves)
