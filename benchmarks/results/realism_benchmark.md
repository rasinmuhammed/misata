Misata 0.9.7, seed 7.

### olist: Olist Brazilian e-commerce, real orders 2016-2018 (30,000 rows)

Story given to `misata_story`: *"A Brazilian e-commerce marketplace with 29651 customers, 14749 products and 30000 orders"*

| Metric | `real_train` | `misata_story` | `misata_schema` | `faker_script` | `misata_mimic` | `sdv_copula` |
|---|---|---|---|---|---|---|
| Amount shape (KS) | 0.008 | 0.169 | 0.051 | 0.191 | 0.024 | 0.072 |
| Hour profile (TVD) | 0.018 | 0.149 | 0.145 | 0.289 | 0.017 | 0.286 |
| Weekday profile (TVD) | 0.010 | 0.046 | 0.048 | 0.054 | 0.009 | 0.057 |
| Customer fan-out (ΔGini) | 0.001 | n/a | 0.256 | 0.237 | n/a | n/a |
| Product fan-out (ΔGini) | 0.003 | 0.440 | 0.028 | 0.149 | n/a | n/a |
| Category balance (Δ) | 0.003 | n/a | 0.481 | 0.500 | 0.001 | 0.003 |
| Detection AUC | 0.500 | 0.732 | 0.629 | 0.785 | 0.533 | 0.708 |
| Tells score ↑ | 1.000 | 0.942 | 1.000 | 0.333 | 1.000 | 0.750 |

### taxis: NYC yellow/green taxi trips, March 2019 (seaborn sample) (6,389 rows)

Story given to `misata_story`: *"A New York taxi company with 6389 taxi rides, fares and payment types"*

| Metric | `real_train` | `misata_story` | `misata_schema` | `faker_script` | `misata_mimic` | `sdv_copula` |
|---|---|---|---|---|---|---|
| Amount shape (KS) | 0.015 | 0.225 | 0.251 | 0.217 | 0.025 | 0.135 |
| Hour profile (TVD) | 0.039 | 0.237 | 0.082 | 0.193 | 0.060 | 0.189 |
| Weekday profile (TVD) | 0.026 | 0.074 | 0.030 | 0.033 | 0.054 | 0.049 |
| Customer fan-out (ΔGini) | n/a | n/a | n/a | n/a | n/a | n/a |
| Product fan-out (ΔGini) | n/a | n/a | n/a | n/a | n/a | n/a |
| Category balance (Δ) | 0.003 | n/a | 0.130 | 0.140 | 0.009 | 0.003 |
| Detection AUC | 0.497 | 0.805 | 0.750 | 0.792 | 0.530 | 0.676 |
| Tells score ↑ | 1.000 | 1.000 | 0.667 | 0.400 | 1.000 | 0.667 |
