import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rates as R  # noqa: E402
from evaluator import (Workload, compliance_score, compute_discount, confidence,  # noqa: E402
                       evaluate, monthly_cost, weighted_score)


def test_single_vm_hand_check():
    """One 2 vCPU / 8 GB Linux VM, always on, US East, on-demand, on AWS.
    (2 x 0.0336 + 8 x 0.0045) x 730 = 0.1032 x 730 = 75.336 USD."""
    w = Workload(instances=1, vcpu=2, ram_gb=8, hours=730)
    cost = monthly_cost("aws", w)
    assert cost["compute"] == pytest.approx(75.336)
    assert sum(cost.values()) == pytest.approx(75.336)


def test_region_and_commitment_factors_apply():
    base = Workload(instances=1, vcpu=2, ram_gb=8, hours=730)
    uk_1yr = Workload(instances=1, vcpu=2, ram_gb=8, hours=730, region="uk", commitment="y1")
    expected = monthly_cost("aws", base)["compute"] * 1.16 * 0.70
    assert monthly_cost("aws", uk_1yr)["compute"] == pytest.approx(expected)


def test_free_egress_allowance():
    assert monthly_cost("aws", Workload(instances=0, egress_gb=100))["egress"] == 0
    assert monthly_cost("aws", Workload(instances=0, egress_gb=1100))["egress"] == pytest.approx(1000 * 0.09)


def test_azure_hybrid_benefit_waives_windows_licence():
    w = Workload(instances=2, vcpu=4, ram_gb=16, os="windows", owns_windows_licences=True)
    assert monthly_cost("azure", w)["licence"] == 0
    assert monthly_cost("aws", w)["licence"] > 0


def test_gcp_sustained_use_discount():
    assert compute_discount("gcp", "od", 730) == pytest.approx(0.80)
    assert compute_discount("gcp", "od", 100) == pytest.approx(1.0)
    assert compute_discount("gcp", "y1", 730) == R.COMMITMENTS["y1"]["gcp"]


def test_compliance_score():
    assert compliance_score("gcp", []) == 100
    assert compliance_score("gcp", ["fedramp"]) == 80
    assert compliance_score("azure", ["sovereign", "gdpr"]) == 100


def test_weighted_score_and_zero_weights():
    dims = {"cost": 100, "compliance": 50, "ecosystem": 50, "fit": 50}
    assert weighted_score(dims, {"cost": 1, "compliance": 1, "ecosystem": 1, "fit": 1}) == 62.5
    assert weighted_score(dims, {"cost": 0, "compliance": 0, "ecosystem": 0, "fit": 0}) == 0


def test_cheapest_gets_full_cost_score_and_results_are_ranked():
    ranked = evaluate(Workload(**R.PRESETS["Customer web app"]))
    assert max(r.dimensions["cost"] for r in ranked) == pytest.approx(100)
    assert [r.score for r in ranked] == sorted((r.score for r in ranked), reverse=True)


@pytest.mark.parametrize("preset, expected", [
    ("Customer web app", "azure"),
    ("Analytics platform", "gcp"),
    ("Windows .NET estate", "azure"),
    ("Healthcare data API", "aws"),
])
def test_preset_recommendations(preset, expected):
    assert evaluate(Workload(**R.PRESETS[preset]))[0].provider == expected


def test_budget_flag_uses_currency():
    w = Workload(**{**R.PRESETS["Customer web app"], "budget": 1, "currency": "GBP"})
    assert all(r.over_budget for r in evaluate(w))


def test_confidence_labels():
    ranked = evaluate(Workload(**R.PRESETS["Customer web app"]))
    label, _ = confidence(ranked)
    assert label in {"Clear lead", "Moderate lead", "Close call"}
