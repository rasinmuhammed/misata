---
title: Generate EdTech Synthetic Data in Python | Misata
description: Generate realistic EdTech synthetic datasets in Python, instructors, courses, students, enrollments, and quiz attempts with back-to-school seasonality, completion rate distributions, and referential integrity. No real student data required.
---

# Generate EdTech Synthetic Data in Python

EdTech platforms have a distinctive data model: instructors create courses, students enroll and progress at non-uniform rates, quiz scores cluster toward passing (most students who attempt pass), and enrollment spikes around the new year and back-to-school season. Misata generates a five-table EdTech dataset with all of this built in, instructors, courses, students, enrollments, and quiz attempts, with no orphaned foreign keys and realistic completion and certificate issuance rates.

```python
import misata

tables = misata.generate(
    "An edtech platform with 5k students and 200 courses",
    rows=5000,
    seed=42,
)
print(list(tables.keys()))   # ['instructors', 'courses', 'students', 'enrollments', 'quiz_attempts']
print(tables["enrollments"][["completion_pct", "certificate_issued"]].describe())
```

## What Misata generates

Five tables: `instructors` → `courses` → `enrollments` (linking students to courses) → `quiz_attempts`. Every enrollment references a real student and course; every quiz attempt references a real enrollment.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `instructors` | `instructor_id`, `name`, `email`, `specialty`, `rating`, `courses_taught` |
| `courses` | `course_id`, `instructor_id`, `title`, `category`, `price`, `difficulty`, `duration_hours`, `rating` |
| `students` | `student_id`, `name`, `email`, `country`, `joined_at`, `total_courses_enrolled` |
| `enrollments` | `enrollment_id`, `student_id`, `course_id`, `enrolled_at`, `completion_pct`, `completed_at`, `certificate_issued` |
| `quiz_attempts` | `attempt_id`, `enrollment_id`, `quiz_name`, `score`, `passed`, `attempted_at` |

### Realistic distributions

- **Enrollment timing** peaks in January (New Year learning resolutions) and August-September (back to school)
- **Completion rates** follow a realistic dropout curve: ~30% of enrollments reach 100% completion
- **`certificate_issued`** is only true for completed enrollments, conditional logic enforced
- **Quiz scores** cluster toward passing (60–85 range) with a realistic fail tail
- **Course prices** lognormal, free courses plus premium paid content

## Quick start

```python
import misata

tables = misata.generate(
    "An edtech platform with 5k students — back to school surge, New Year spike in programming courses",
    rows=5000,
    seed=42,
)

# Enrollment seasonality
import pandas as pd
enrollments = tables["enrollments"].copy()
enrollments["month"] = pd.to_datetime(enrollments["enrolled_at"]).dt.month
print(enrollments.groupby("month").size())   # spikes in Jan and Sep

# Certificate issuance rate
cert_rate = tables["enrollments"]["certificate_issued"].mean()
print(f"Certificate issuance rate: {cert_rate:.1%}")

# Quiz pass rate by difficulty
merged = tables["quiz_attempts"].merge(
    tables["enrollments"].merge(tables["courses"][["course_id", "difficulty"]], on="course_id"),
    on="enrollment_id"
)
print(merged.groupby("difficulty")["passed"].mean())
```

## Common use cases

- **LMS platform development**: seed a test database with instructors, courses, and enrollment histories before your platform has real users
- **Learning analytics dashboards**: build completion rate, dropout analysis, and learner progress reports on realistic enrollment data
- **Recommendation engine training**: use enrollment and quiz score histories to prototype course recommendation models
- **Revenue and subscription analytics**: test cohort revenue, course monetization, and refund rate calculations before real sales data exists
- **Adaptive learning system testing**: validate quiz difficulty adaptation logic against thousands of attempts with varied score distributions
- **GDPR-safe student data exports**: replace real student records with synthetic equivalents for vendor integrations and compliance audits

## Advanced: enrollment narrative curves

```python
tables = misata.generate(
    "Edtech platform with 10k students — January New Year resolution spike, "
    "August back-to-school surge, summer lull in June-July",
    rows=10_000,
    seed=42,
)
```

## Advanced: locale-aware generation

```python
# Indian edtech — Indian student names, INR course pricing, regional subjects
tables = misata.generate("Indian edtech platform with 5k students and coding courses", rows=5000)

# Global MOOC — students from US, UK, India, Nigeria, Brazil
tables = misata.generate("Global online learning platform with 10k students", rows=10_000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "EdTech platform with 5k students",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds completion_pct↔quiz score correlations
    rows=5000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Narrative Patterns](../guides/narrative-patterns.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
