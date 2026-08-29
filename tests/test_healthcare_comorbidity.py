"""
The gap this closes: healthcare_hospital.py's diagnoses were an independent
uniform draw per row, so nothing connected a patient's condition list to
itself across admissions -- a patient with kidney disease was exactly as
likely to also show up with an unrelated broken bone as with hypertension.
Real comorbidity clusters, not independence, and real EHR data reflects that.

Two numbers are cited, not invented: 13.3% prevalence of the CKD +
hypertension + diabetes "kidney-metabolic" cluster in a 163,626-patient
elderly inpatient cohort (Xu et al., 2026), and a mean length of stay near
17 days for APR-DRG severity-of-illness level 4 ("extreme") -- the one tier
of the four with a cited figure; the other three are a designed,
monotonically increasing progression anchored at that real number.

These tests check the thing that actually matters: that a patient's
assigned cluster measurably concentrates their recorded diagnoses (not
merely that the enum draws at roughly the declared weight, which a plain
`enum`/`weights` column already guarantees), and that severity actually
drives length of stay rather than the two columns being independent.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))

from healthcare_comorbidity import (
    build, verify, CLUSTER_WEIGHTS, SEVERITY_MEAN_LOS,
    KIDNEY_METABOLIC_INDICES, DIABETES_HYPERTENSION_INDICES,
)
from healthcare_hospital import DIAGNOSES, N_DIAGNOSES


def test_full_verify_passes_on_a_fresh_run():
    # Same discipline as the predictive-maintenance suite: the example's
    # own verify() is the real test, run here so CI catches a regression
    # even if nobody remembers to run the script by hand.
    tables = build(n_patients=800, seed=3)
    assert verify(tables)


def test_cluster_weights_match_the_cited_prevalence():
    tables = build(n_patients=3000, seed=1)
    measured = tables["patients"]["comorbidity_cluster"].value_counts(normalize=True)
    for cluster, target in CLUSTER_WEIGHTS.items():
        assert abs(measured.get(cluster, 0.0) - target) < 0.03, (cluster, measured)


def test_diagnoses_concentrate_within_a_patients_own_cluster():
    # The actual claim: a kidney_metabolic patient's diagnoses land on
    # {T2DM, hypertension, CKD3} far more often than chance, because they
    # are drawn from that patient's own cluster -- not from the full
    # 50-item vocabulary independently of who the patient is.
    tables = build(n_patients=3000, seed=1)
    diag_with_cluster = (
        tables["diagnoses"]
        .merge(tables["admissions"][["admission_id", "patient_id"]], on="admission_id")
        .merge(tables["patients"][["patient_id", "comorbidity_cluster"]], on="patient_id")
    )
    for cluster, indices in [("kidney_metabolic", KIDNEY_METABOLIC_INDICES),
                             ("diabetes_hypertension", DIABETES_HYPERTENSION_INDICES)]:
        names = {DIAGNOSES[i] for i in indices}
        sub = diag_with_cluster[diag_with_cluster["comorbidity_cluster"] == cluster]
        rate = sub["diagnosis_name"].isin(names).mean()
        baseline = len(indices) / N_DIAGNOSES
        assert rate > baseline * 3, (cluster, rate, baseline)

    # And the control group: patients NOT in either cluster should show no
    # such concentration -- otherwise the "connection" would just be an
    # artifact of the vocabulary, not of the cluster assignment.
    independent = diag_with_cluster[diag_with_cluster["comorbidity_cluster"] == "independent"]
    km_names = {DIAGNOSES[i] for i in KIDNEY_METABOLIC_INDICES}
    rate = independent["diagnosis_name"].isin(km_names).mean()
    baseline = len(KIDNEY_METABOLIC_INDICES) / N_DIAGNOSES
    assert rate < baseline * 1.5, (rate, baseline)


def test_length_of_stay_increases_monotonically_with_severity():
    tables = build(n_patients=3000, seed=1)
    by_severity = tables["admissions"].groupby("severity")["length_of_stay_days"].mean()
    order = ["minor", "moderate", "major", "extreme"]
    means = [by_severity[s] for s in order]
    assert all(means[i] < means[i + 1] for i in range(3)), means


def test_extreme_severity_mean_los_lands_near_the_cited_figure():
    tables = build(n_patients=3000, seed=1)
    extreme_mean = tables["admissions"].groupby("severity")["length_of_stay_days"].mean()["extreme"]
    assert 14 <= extreme_mean <= 20, extreme_mean


def test_admit_precedes_discharge_and_los_reconciles_on_every_row():
    tables = build(n_patients=500, seed=2)
    adm = tables["admissions"]
    assert (adm["admit_date"] < adm["discharge_date"]).all()
    assert ((adm["discharge_date"] - adm["admit_date"]).dt.days
            == adm["length_of_stay_days"]).all()


def test_reproducible_with_the_same_seed():
    a = build(n_patients=300, seed=9)
    b = build(n_patients=300, seed=9)
    assert a["patients"]["comorbidity_cluster"].equals(b["patients"]["comorbidity_cluster"])
    assert a["admissions"]["length_of_stay_days"].equals(b["admissions"]["length_of_stay_days"])
