"""Pure cost and scoring functions for the Cloud Workload Evaluator.

No Streamlit imports here, so everything can be unit tested and reused
(for example behind an API later). All costs are monthly, in USD, and are
estimates based on the tables in rates.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import rates as R


@dataclass
class Workload:
    wtype: str = "web"
    region: str = "us"
    instances: int = 1
    vcpu: int = 2
    ram_gb: float = 8
    hours: float = 730
    gpus: int = 0
    os: str = "linux"  # "linux" or "windows"
    owns_windows_licences: bool = False  # enables Azure Hybrid Benefit
    commitment: str = "od"  # "od", "y1", "y3"
    block_gb: float = 0
    object_gb: float = 0
    egress_gb: float = 0
    compliance: list[str] = field(default_factory=list)
    estate: str = "none"
    budget: float = 0  # monthly, in `currency`
    currency: str = "USD"


@dataclass
class Result:
    provider: str
    breakdown: dict[str, float]
    total: float
    dimensions: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    over_budget: bool = False

    @property
    def name(self) -> str:
        return R.PROVIDER_NAMES[self.provider]


def compute_discount(provider: str, commitment: str, hours: float) -> float:
    """Multiplier for compute and GPU cost, including Google's sustained-use discount."""
    if provider == "gcp" and commitment == "od":
        utilisation = min(hours / 730, 1.0)
        ramp = max(0.0, min(1.0, (utilisation - 0.25) / 0.75))
        return 1 - R.GCP_MAX_SUSTAINED_USE_DISCOUNT * ramp
    return R.COMMITMENTS[commitment][provider]


def monthly_cost(provider: str, w: Workload, rates: dict | None = None) -> dict[str, float]:
    """Monthly cost breakdown in USD for one provider."""
    rates = rates or R.RATES
    rate = {k: v[provider] for k, v in rates.items()}
    region = R.REGIONS[w.region][provider]
    discount = compute_discount(provider, w.commitment, w.hours)
    instance_hours = w.instances * min(w.hours, 744)

    compute = instance_hours * (w.vcpu * rate["vcpu_hr"] + w.ram_gb * rate["ram_gb_hr"]) * region * discount
    gpu = instance_hours * w.gpus * rate["gpu_hr"] * region * discount
    licence = 0.0
    if w.os == "windows" and not (provider == "azure" and w.owns_windows_licences):
        licence = instance_hours * w.vcpu * rate["win_vcpu_hr"] * region
    storage = (w.block_gb * rate["block_gb_month"] + w.object_gb * rate["object_gb_month"]) * region
    egress = max(0.0, w.egress_gb - R.FREE_EGRESS_GB) * rate["egress_gb"] * region

    return {"compute": compute, "gpu": gpu, "licence": licence, "storage": storage, "egress": egress}


def compliance_score(provider: str, requirements: list[str]) -> float:
    """0 to 100. If no requirements are selected, every provider scores 100."""
    if not requirements:
        return 100.0
    total = sum(R.COMPLIANCE[r][provider] for r in requirements)
    return 100.0 * total / (5 * len(requirements))


def weighted_score(dimensions: dict[str, float], weights: dict[str, float]) -> float:
    wsum = sum(weights.values()) or 1
    return sum(dimensions[k] * weights[k] for k in weights) / wsum


def to_usd(amount: float, currency: str) -> float:
    return amount / R.FX[currency]


def from_usd(amount: float, currency: str) -> float:
    return amount * R.FX[currency]


def evaluate(w: Workload, weights: dict[str, float] | None = None, rates: dict | None = None) -> list[Result]:
    """Score every provider and return results ranked best first."""
    weights = weights or R.DEFAULT_WEIGHTS
    results = []
    for p in R.PROVIDERS:
        breakdown = monthly_cost(p, w, rates)
        results.append(Result(provider=p, breakdown=breakdown, total=sum(breakdown.values())))

    cheapest = min(r.total for r in results)
    budget_usd = to_usd(w.budget, w.currency) if w.budget else 0

    for r in results:
        cost = 100.0 * cheapest / r.total if r.total > 0 else 100.0
        r.dimensions = {
            "cost": cost,
            "compliance": compliance_score(r.provider, w.compliance),
            "ecosystem": float(R.ECOSYSTEM_FIT[w.estate][r.provider]),
            "fit": float(R.WORKLOAD_FIT[w.wtype][r.provider]),
        }
        r.score = weighted_score(r.dimensions, weights)
        r.over_budget = budget_usd > 0 and r.total > budget_usd

    return sorted(results, key=lambda r: r.score, reverse=True)


def confidence(ranked: list[Result]) -> tuple[str, str]:
    """Label and explanation based on the gap between first and second place."""
    top, second = ranked[0], ranked[1]
    gap = top.score - second.score
    if gap >= 8:
        return "Clear lead", (f"{top.name} leads {second.name} by {gap:.1f} points. "
                              "The recommendation holds under modest changes to the weights.")
    if gap >= 3:
        return "Moderate lead", (f"{top.name} leads {second.name} by {gap:.1f} points. "
                                 "Test the weights with the customer before committing.")
    return "Close call", (f"Only {gap:.1f} points separate {top.name} and {second.name}. "
                          "Decide on non-price factors and run a short proof of concept on both.")


def reasons(ranked: list[Result], w: Workload) -> list[str]:
    top = ranked[0]
    by_cost = sorted(ranked, key=lambda r: r.total)
    out = []
    if top.provider == by_cost[0].provider:
        nxt = by_cost[1]
        pct = round(100 * (nxt.total - top.total) / nxt.total) if nxt.total else 0
        out.append(f"Lowest estimated cost, about {pct}% below {nxt.name} for this workload.")
    else:
        cheapest = by_cost[0]
        pct = round(100 * (top.total - cheapest.total) / cheapest.total) if cheapest.total else 0
        out.append(f"Costs about {pct}% more than {cheapest.name}, which the other priorities outweigh.")
    out.append(R.WORKLOAD_NOTES[w.wtype][top.provider])
    estate_note = R.ESTATE_NOTES.get(w.estate, {}).get(top.provider)
    if estate_note:
        out.append(estate_note)
    if w.os == "windows" and w.owns_windows_licences and top.provider == "azure":
        out.append("Azure Hybrid Benefit removes Windows licence charges, which the other clouds still bill.")
    if w.compliance and all(R.COMPLIANCE[c][top.provider] == 5 for c in w.compliance):
        out.append("Meets every selected compliance requirement with mainstream, well-documented service coverage.")
    return out[:4]


def risks(ranked: list[Result], w: Workload) -> list[str]:
    top = ranked[0]
    out = []
    if top.over_budget:
        over = from_usd(top.total, w.currency) - w.budget
        out.append(f"Over budget by about {over:,.0f} {w.currency} a month. "
                   "Consider a longer commitment, rightsizing or spot capacity.")
    if w.gpus > 0:
        out.append("GPU capacity is often quota-limited. Confirm quota and availability in the target region early.")
    if top.provider == "gcp" and w.egress_gb > 5000:
        out.append("Google Cloud premium-tier egress is priced higher; check whether standard tier or a CDN fits.")
    if w.commitment != "od":
        out.append(f"A {R.COMMITMENTS[w.commitment]['label'].lower()} locks in spend. Confirm the workload is stable first.")
    if {"sovereign", "fedramp"} & set(w.compliance):
        out.append("Sovereign and government regions offer fewer services and different pricing. "
                   "Validate the exact service list.")
    if w.os == "windows" and not w.owns_windows_licences:
        out.append("Windows licences are a large share of cost. Ask whether the customer holds licences "
                   "with Software Assurance.")
    out.append("Estimates exclude support plans, managed databases and inter-zone traffic.")
    return out[:4]
