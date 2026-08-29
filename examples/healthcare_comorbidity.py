"""
Extends healthcare_hospital.py with two connections real EHR data has and a
uniform per-row draw cannot: diagnoses that cluster within a patient rather
than landing independently, and a length of stay that actually depends on
how sick the admission was.

Both numbers below are cited, not invented:

  * The "kidney-metabolic" comorbidity pattern (CKD + hypertension +
    diabetes) had 13.3% prevalence in a 163,626-patient elderly inpatient
    cohort (Xu et al., 2026, Food Science & Nutrition). Diabetes and
    hypertension co-occurring without CKD specifically was 17% among
    community-dwelling older adults (Pham et al., PubMed 30094913). These
    are two separate studies of overlapping but distinct populations,
    applied here as non-overlapping synthetic categories for construction
    -- a modeling simplification, stated plainly rather than left implicit.

  * APR-DRG's four severity-of-illness tiers (minor/moderate/major/extreme)
    are the real, standard hospital severity classification. The one
    length-of-stay figure with a citation is the top tier: patients at
    APR severity 4 ("extreme") have a mean length of stay of almost 17
    days. The other three tiers are a designed, monotonically increasing
    progression anchored at that one real number, not independently cited
    -- exactly the same honesty split as the bearing geometry being
    textbook while the damage trajectory shape is declared.

The property this earns, checked below: a patient's diagnoses are not an
independent draw per admission. They come from what that patient actually
has, which is the thing a uniform per-row draw structurally cannot produce.
"""

import numpy as np
import pandas as pd

import misata
from healthcare_hospital import DIAGNOSES, ICD_CODES, N_DIAGNOSES, SPECIALTIES, INSURANCE_PROVIDERS

RNG = np.random.default_rng(7)

# Indices into DIAGNOSES/ICD_CODES, confirmed against the real vocabulary.
T2DM, HYPERTENSION, CKD3 = 0, 1, 5
KIDNEY_METABOLIC_INDICES = [T2DM, HYPERTENSION, CKD3]
DIABETES_HYPERTENSION_INDICES = [T2DM, HYPERTENSION]

CLUSTER_WEIGHTS = {
    "kidney_metabolic": 0.133,        # cited: Xu et al. 2026
    "diabetes_hypertension": 0.17,    # cited: Pham et al., PubMed 30094913
    "independent": 1.0 - 0.133 - 0.17,
}

# Designed, not cited, except the last: mean days per APR-DRG severity tier.
SEVERITY_MEAN_LOS = {
    "minor": 2.5,
    "moderate": 5.0,
    "major": 9.0,
    "extreme": 17.0,   # cited: APR severity 4 mean LOS "almost 17 days"
}
SEVERITY_WEIGHTS = {"minor": 0.40, "moderate": 0.30, "major": 0.20, "extreme": 0.10}


def build(n_patients: int = 500, n_doctors: int = 50, seed: int = 7):
    schema = {
        "doctors": {
            "__rows__": n_doctors,
            "doctor_id": {"type": "integer", "primary_key": True},
            "specialty": {"type": "string", "enum": SPECIALTIES},
        },
        "patients": {
            "__rows__": n_patients,
            "patient_id": {"type": "integer", "primary_key": True},
            "insurance_provider": {"type": "string", "enum": INSURANCE_PROVIDERS},
            "comorbidity_cluster": {"type": "string",
                "enum": list(CLUSTER_WEIGHTS.keys()),
                "weights": list(CLUSTER_WEIGHTS.values())},
        },
        "admissions": {
            "__rows__": n_patients * 2,
            "admission_id": {"type": "integer", "primary_key": True},
            "patient_id": {"type": "integer", "foreign_key": {"table": "patients", "column": "patient_id"}},
            "doctor_id": {"type": "integer", "foreign_key": {"table": "doctors", "column": "doctor_id"}},
            "admit_date": {"type": "datetime", "min_date": "2025-01-01", "max_date": "2025-12-01"},
            "severity": {"type": "string",
                "enum": list(SEVERITY_WEIGHTS.keys()),
                "weights": list(SEVERITY_WEIGHTS.values())},
        },
        "diagnoses": {
            "__rows__": int(n_patients * 2 * 1.4),
            "diagnosis_row_id": {"type": "integer", "primary_key": True},
            "admission_id": {"type": "integer", "foreign_key": {"table": "admissions", "column": "admission_id"}},
            "diagnosis_index": {"type": "integer", "min": 0, "max": N_DIAGNOSES - 1},
            "is_primary": {"type": "boolean"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    # Length of stay is now DERIVED from each admission's severity, not
    # drawn independently -- the connection the docstring promises.
    admissions = tables["admissions"].copy()
    admissions["admit_date"] = pd.to_datetime(admissions["admit_date"])
    mean_los = admissions["severity"].map(SEVERITY_MEAN_LOS)
    # Lognormal-shaped scatter around the tier mean, floor of 1 day.
    admissions["length_of_stay_days"] = np.maximum(
        1, np.round(rng.lognormal(mean=np.log(mean_los), sigma=0.35))
    ).astype(int)
    admissions["discharge_date"] = admissions["admit_date"] + pd.to_timedelta(
        admissions["length_of_stay_days"], unit="D")
    tables["admissions"] = admissions

    # Diagnoses drawn preferentially from the ADMITTED PATIENT's own
    # comorbidity cluster -- the connection a uniform per-row draw cannot
    # produce, because a uniform draw does not know which patient this is.
    diagnoses = tables["diagnoses"].copy()
    patient_cluster = (tables["admissions"][["admission_id", "patient_id"]]
                        .merge(tables["patients"][["patient_id", "comorbidity_cluster"]], on="patient_id")
                        .set_index("admission_id")["comorbidity_cluster"])
    cluster_of_row = diagnoses["admission_id"].map(patient_cluster)

    def pick_index(cluster: str) -> int:
        if cluster == "kidney_metabolic":
            # Strongly weighted toward the cited three, not exclusively --
            # real patients in this cluster still have occasional unrelated
            # diagnoses recorded.
            if rng.random() < 0.8:
                return int(rng.choice(KIDNEY_METABOLIC_INDICES))
            return int(rng.integers(0, N_DIAGNOSES))
        if cluster == "diabetes_hypertension":
            if rng.random() < 0.8:
                return int(rng.choice(DIABETES_HYPERTENSION_INDICES))
            return int(rng.integers(0, N_DIAGNOSES))
        return int(rng.integers(0, N_DIAGNOSES))

    diagnoses["diagnosis_index"] = [pick_index(c) for c in cluster_of_row]
    diagnoses["diagnosis_name"] = diagnoses["diagnosis_index"].map(lambda i: DIAGNOSES[i])
    diagnoses["icd_code"] = diagnoses["diagnosis_index"].map(lambda i: ICD_CODES[i])
    diagnoses = diagnoses.drop(columns=["diagnosis_index"])
    tables["diagnoses"] = diagnoses

    return tables


def verify(tables: dict) -> bool:
    checks = []

    patients = tables["patients"]
    admissions = tables["admissions"]
    diagnoses = tables["diagnoses"]

    # 1. Cluster weights measured against the cited prevalence.
    measured = patients["comorbidity_cluster"].value_counts(normalize=True)
    for cluster, target in CLUSTER_WEIGHTS.items():
        ok = abs(measured.get(cluster, 0.0) - target) < 0.03
        checks.append((f"comorbidity_cluster '{cluster}' matches cited prevalence "
                        f"({measured.get(cluster,0):.3f} vs {target:.3f})", ok))

    # 2. The actual connection: does a patient's cluster predict what shows
    # up in their diagnoses, far above chance?
    diag_with_cluster = (diagnoses.merge(admissions[["admission_id", "patient_id"]], on="admission_id")
                                   .merge(patients[["patient_id", "comorbidity_cluster"]], on="patient_id"))
    for cluster, indices in [("kidney_metabolic", KIDNEY_METABOLIC_INDICES),
                             ("diabetes_hypertension", DIABETES_HYPERTENSION_INDICES)]:
        names = {DIAGNOSES[i] for i in indices}
        sub = diag_with_cluster[diag_with_cluster["comorbidity_cluster"] == cluster]
        rate = sub["diagnosis_name"].isin(names).mean() if len(sub) else 0.0
        baseline = len(indices) / N_DIAGNOSES
        checks.append((f"'{cluster}' patients show their cluster's diagnoses at "
                        f"{rate:.2f} vs a {baseline:.2f} random baseline "
                        f"({rate/baseline:.1f}x)", rate > baseline * 3))

    # 3. Severity tiers produce strictly increasing mean length of stay,
    # and the top tier lands near the one cited real number.
    by_severity = admissions.groupby("severity")["length_of_stay_days"].mean()
    order = ["minor", "moderate", "major", "extreme"]
    increasing = all(by_severity[order[i]] < by_severity[order[i+1]] for i in range(3))
    checks.append(("mean length of stay strictly increases minor -> extreme", increasing))
    extreme_mean = by_severity["extreme"]
    checks.append((f"'extreme' mean LOS ({extreme_mean:.1f}d) is close to the cited ~17d",
                    14 <= extreme_mean <= 20))

    # 4. Structural guarantees from healthcare_hospital.py still hold.
    checks.append(("admit precedes discharge on every row",
                    (admissions["admit_date"] < admissions["discharge_date"]).all()))
    checks.append(("length of stay reconciles on every row",
                    ((admissions["discharge_date"] - admissions["admit_date"]).dt.days
                     == admissions["length_of_stay_days"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_patients=2000, seed=7)
    print(f"patients: {len(tables['patients'])}  admissions: {len(tables['admissions'])}  "
          f"diagnoses: {len(tables['diagnoses'])}")
    print()
    ok = verify(tables)
    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
