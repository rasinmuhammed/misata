"""
Healthcare Multi-Table Dataset
================================
Generates a 3-table relational dataset: doctors, patients, appointments.
Two foreign keys. Blood type distribution matches real-world ABO/Rh frequencies.
Patient age follows a normal distribution centered on 45 (chronic care skew).

Run:
    python examples/healthcare_multi_table.py
"""

import warnings
warnings.filterwarnings("ignore")

import misata
import pandas as pd
import numpy as np

# ── Generate ──────────────────────────────────────────────────────────────────

tables = misata.generate(
    "A hospital with 500 patients and doctors.",
    rows=500,
    seed=42,
)

doctors      = tables["doctors"]
patients     = tables["patients"]
appointments = tables["appointments"]

print()
print("━" * 64)
print("  Misata — Healthcare Multi-Table Demo")
print("━" * 64)
print(f"  Doctors:      {len(doctors):>6,}")
print(f"  Patients:     {len(patients):>6,}")
print(f"  Appointments: {len(appointments):>6,}")
print(f"  Ratio:        {len(appointments)/len(patients):.1f} appointments per patient")
print()

# ── Two independent FK edges ──────────────────────────────────────────────────

doc_ids  = set(doctors["doctor_id"])
pat_ids  = set(patients["patient_id"])
orphan_by_patient = (~appointments["patient_id"].isin(pat_ids)).sum()
orphan_by_doctor  = (~appointments["doctor_id"].isin(doc_ids)).sum()

print("  Referential integrity  (2 independent FK edges)")
print(f"  {'patients → appointments':<32} {'✓ 0 orphans' if orphan_by_patient == 0 else f'✗ {orphan_by_patient}':>16}")
print(f"  {'doctors → appointments':<32} {'✓ 0 orphans' if orphan_by_doctor == 0 else f'✗ {orphan_by_doctor}':>16}")
print()

# ── Blood type distribution vs real world ─────────────────────────────────────

REAL_BLOOD_TYPES = {
    "O+": 38.0, "A+": 34.0, "B+": 9.0, "AB+": 3.0,
    "O-": 7.0,  "A-": 6.0,  "B-": 2.0, "AB-": 1.0,
}

bt_counts = patients["blood_type"].value_counts()
bt_pct    = (bt_counts / len(patients) * 100).to_dict()

print("  Blood type distribution  (Misata uses real ABO/Rh frequencies)")
print(f"  {'Type':<6}  {'Generated':>10}  {'Real-world':>10}  {'Δ':>6}")
print(f"  {'─'*5}  {'─'*10}  {'─'*10}  {'─'*6}")
for bt, real_pct in REAL_BLOOD_TYPES.items():
    gen_pct = bt_pct.get(bt, 0.0)
    delta   = gen_pct - real_pct
    flag    = f"{delta:+.1f}%" if abs(delta) > 2 else "  ✓"
    print(f"  {bt:<6}  {gen_pct:>9.1f}%  {real_pct:>9.1f}%  {flag:>6}")
print()

# ── Patient age distribution ──────────────────────────────────────────────────

ages = patients["age"].dropna()
print(f"  Patient age distribution  (normal, centred on chronic-care population)")
print(f"  {'Metric':<10}  {'Value':>8}")
print(f"  {'─'*10}  {'─'*8}")
print(f"  {'Mean':<10}  {ages.mean():>7.1f}")
print(f"  {'Median':<10}  {ages.median():>7.1f}")
print(f"  {'Std dev':<10}  {ages.std():>7.1f}")
print(f"  {'Min / Max':<10}  {ages.min():>3.0f} / {ages.max():.0f}")

buckets = [(0,17,"0–17"),(18,34,"18–34"),(35,54,"35–54"),(55,74,"55–74"),(75,100,"75+")]
print()
for lo, hi, label in buckets:
    n   = ((ages >= lo) & (ages <= hi)).sum()
    pct = n / len(ages) * 100
    bar = "█" * int(pct / 2.5)
    print(f"  {label:<8}  {bar:<24}  {pct:>5.1f}%")
print()

# ── Appointment types ─────────────────────────────────────────────────────────

print("  Appointment type breakdown")
type_counts = appointments["type"].value_counts()
for atype, count in type_counts.items():
    pct = count / len(appointments) * 100
    bar = "█" * int(pct / 2)
    print(f"  {atype:<14}  {bar:<28}  {pct:>5.1f}%")

print()
print("━" * 64)
print()
