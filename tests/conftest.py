"""Test-suite configuration.

Two pandas options are forced on so the local suite matches CI, where the
latest pandas / numpy are installed and both behaviours are already the
default. Turning them on locally keeps two classes of CI-only bug visible on
a developer's machine.

1. ``future.infer_string``: a string column gets a ``str``/``string`` dtype
   rather than ``object``. Code that gated on ``dtype == object`` silently
   skipped those columns, which produced CI-only failures in tier
   monotonicity, state-machine label resolution, and the coherence
   label-filler detector.

2. ``mode.copy_on_write``: ``Series.to_numpy()`` returns a read-only view, so
   mutating it in place (``arr[idx] = ...``) raises instead of quietly
   succeeding. This is exactly what broke the group-shares pass on CI in
   0.8.4 while passing on a local numpy 1.26 build; a bare ``.to_numpy()``
   that is later written to must use ``copy=True``. Verified that this option
   reproduces the read-only array on numpy 1.26 too, so the guard is real.
"""
import pandas as pd

pd.set_option("future.infer_string", True)
pd.set_option("mode.copy_on_write", True)
