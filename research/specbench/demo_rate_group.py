"""I3 demo: outcome conformance generalizes beyond temporal sums to RATES and GROUP
SHARES. Shows the engine (declarative path) hits a declared churn RATE and a declared
plan-distribution exactly-to-sampling-noise; contrasts with an uncontrolled draw.
Run: PYTHONPATH=. .venv_specbench/bin/python3 research/specbench/demo_rate_group.py
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, misata
from misata.schema import SchemaConfig, Table, Column
from research.specbench.metrics import rate_conformance_error, group_distribution_conformance

def engine_rate(target, n=20000, seed=0):
    cfg=SchemaConfig(name="r",tables=[Table(name="u",row_count=n)],
      columns={"u":[Column(name="churned",type="categorical",
        distribution_params={"choices":[True,False],"probabilities":[target,1-target]})]})
    return misata.generate_from_schema({**{}, } and cfg if False else cfg)

print("=== RCE: declared churn RATE (engine, declarative) ===")
for tgt in (0.05,0.10,0.20,0.35):
    t=engine_rate(tgt,seed=1)
    r=rate_conformance_error(t,"u","churned",True,tgt)
    print(f"  target={tgt:.2f}  {r.detail}  RCE={r.value:.4f}")

print("\n=== GDC: declared plan SHARE (engine, declarative) ===")
shares={"free":0.6,"pro":0.3,"ent":0.1}
cfg=SchemaConfig(name="g",tables=[Table(name="u",row_count=20000)],
  columns={"u":[Column(name="plan",type="categorical",
    distribution_params={"choices":list(shares),"probabilities":list(shares.values())})]})
t=misata.generate_from_schema(cfg)
g=group_distribution_conformance(t,"u","plan",shares)
print(f"  {g.detail}  GDC(TVD)={g.value:.4f}")

print("\n=== contrast: uncontrolled draw (no target ingestion) ===")
rng=np.random.default_rng(0)
import pandas as pd
bad={"u":pd.DataFrame({"churned":rng.random(20000)<0.5})}
print("  churn target 0.20 vs uncontrolled 50/50: RCE=",
      round(rate_conformance_error(bad,"u","churned",True,0.20).value,3))
