# Constraints

Enforce business rules that survive every row of generation. Constraints run at generation time, not as post-processing.

## Types

### InequalityConstraint

Ensures `column_a OP column_b` on every row. Violations are fixed by nudging `column_a`.

```python
from misata.constraints import InequalityConstraint

c = InequalityConstraint("price", ">", "cost")
df = c.apply(df)
```

In YAML:
```yaml
constraints:
  - name: profit_margin
    table: orders
    type: inequality
    column_a: amount
    operator: ">"
    column_b: cost
```

Operators: `>`, `>=`, `<`, `<=`

---

### ColumnRangeConstraint

Clips a column to `[low_col, high_col]` per row.

```python
from misata.constraints import ColumnRangeConstraint

c = ColumnRangeConstraint("price", low_col="min_price", high_col="max_price")
df = c.apply(df)
```

---

### RatioConstraint

Enforces a target proportion of a categorical value.

```python
from misata.constraints import RatioConstraint

c = RatioConstraint(column="plan", value="free", ratio=0.70)
df = c.apply(df)
# 70% of rows will have plan == "free"
```

---

### UniqueConstraint

Removes duplicate values (or duplicate composite keys).

```python
from misata.constraints import UniqueConstraint

c = UniqueConstraint(columns=["user_id", "date"])
df = c.apply(df)
```

---

### SumConstraint

Ensures values in a column sum to a target within a group.

```python
from misata.constraints import SumConstraint

c = SumConstraint(column="hours", group_by="employee_id", target=8.0)
df = c.apply(df)
# Total hours per employee == 8.0
```

---

### NotNullConstraint

Replaces nulls with a fallback value.

```python
from misata.constraints import NotNullConstraint

c = NotNullConstraint(column="email", fallback="unknown@example.com")
df = c.apply(df)
```

---

## Applying multiple constraints

```python
from misata.constraints import ConstraintEngine

engine = ConstraintEngine([
    InequalityConstraint("price", ">", "cost"),
    RatioConstraint("status", "active", 0.85),
    UniqueConstraint(["order_id"]),
])

df = engine.apply(df)
```
