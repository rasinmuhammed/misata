"""D12: throughput vs rows — Misata (closed-form, no training) vs SDV (fit+sample).
Measures wall-clock to produce N rows of a single-table outcome dataset. The point is
the *scaling shape*: closed-form generation is ~linear and training-free, whereas
learned methods pay a fit cost that dwarfs sampling. Real measurements, no estimates.
Run: PYTHONPATH=. .venv_specbench/bin/python3 research/specbench/throughput.py
"""
import warnings; warnings.filterwarnings("ignore")
import time, numpy as np, pandas as pd, misata

def misata_secs(n, seed=0):
    t0=time.perf_counter()
    misata.generate("An ecommerce store with revenue $50k in January rising to $200k in December",
                    rows=n, seed=seed)
    return time.perf_counter()-t0

def sdv_gc_secs(n, seed=0):
    import random; random.seed(seed); np.random.seed(seed)
    from sdv.metadata import Metadata
    from sdv.single_table import GaussianCopulaSynthesizer
    rng=np.random.default_rng(seed)
    df=pd.DataFrame({"amount":rng.lognormal(4,.6,n),"cat":rng.choice(list("ABCD"),n),
                     "d":pd.to_datetime("2024-01-01")+pd.to_timedelta(rng.integers(0,365,n),unit="D")})
    md=Metadata.detect_from_dataframe(df)
    t0=time.perf_counter(); s=GaussianCopulaSynthesizer(md); s.fit(df); s.sample(n)
    return time.perf_counter()-t0

print(f"{'rows':>8} {'misata_s':>10} {'sdv_gc_s':>10} {'speedup':>8}")
rows=[1000,5000,20000,50000]
out=[]
for n in rows:
    m=np.mean([misata_secs(n,s) for s in (0,1)])
    try: g=sdv_gc_secs(n,0)
    except Exception as e: g=float('nan')
    sp=g/m if m>0 and g==g else float('nan')
    out.append((n,m,g,sp))
    print(f"{n:>8} {m:>10.3f} {g:>10.3f} {sp:>7.1f}x")
pd.DataFrame(out,columns=["rows","misata_s","sdv_gc_s","speedup"]).to_csv(
    "research/specbench/throughput.csv",index=False)
print("\nwrote throughput.csv (note: SDV cannot even ingest the outcome target;")
print("this measures raw generation cost on a comparable single-table workload).")
