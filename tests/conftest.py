"""Test-suite configuration.

Force pandas string inference on so the local suite matches CI (and pandas 3.0,
where it becomes the default). Under string inference a string column has a
``str``/``string`` dtype rather than ``object``; code that gated on
``dtype == object`` silently skipped those columns, which produced CI-only
failures in tier monotonicity, state-machine label resolution, and the
coherence label-filler detector. Running with the option on here keeps that
class of bug visible locally.
"""
import pandas as pd

pd.set_option("future.infer_string", True)
