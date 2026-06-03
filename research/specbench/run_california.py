import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from research.specbench.tasks import _real_dataset_reference_task
from research.specbench.baselines import (MisataBaseline, NaiveRescaleBaseline,
    FakerBaseline, SDVBaseline)
from research.specbench.metrics import aggregate_match_error, determinism

t=_real_dataset_reference_task()
print("CALIFORNIA HOUSING reference task — real metric, n=",t.rows)
print(f"{'baseline':<20}{'input':>8}{'AME(3 seeds)':>16}{'DET':>6}")
def ame_of(r):
    return aggregate_match_error(r.tables,t.metric_table,t.metric_col,t.time_col,t.period_targets,t.period_freq).value
for B in (MisataBaseline(),NaiveRescaleBaseline(),FakerBaseline()):
    ames=[]; inp=None
    for sd in (42,43,44):
        r=B.generate(t,sd); ames.append(ame_of(r))
        inp=(r.reason.split('=')[1] if r.reason.startswith('input=') else B.capabilities.input_type)
    d=determinism(B.generate(t,42).tables,B.generate(t,42).tables).value
    print(f"{B.name:<20}{inp:>8}{np.mean(ames):>16.4f}{d:>6.1f}")
for s in ("gaussian_copula","hma"):
    B=SDVBaseline(s); ames=[]
    for sd in (42,43,44):
        r=B.generate(t,sd)
        if r.ran: ames.append(ame_of(r))
    if ames: print(f"{B.name:<20}{'data':>8}{np.mean(ames):>16.4f}{'1.0':>6}")
import time; t0=time.time()
B=SDVBaseline("ctgan"); r=B.generate(t,42)
if r.ran: print(f"{'sdv_ctgan(1seed)':<20}{'data':>8}{ame_of(r):>16.4f}{'~':>6}  ({time.time()-t0:.0f}s)")
