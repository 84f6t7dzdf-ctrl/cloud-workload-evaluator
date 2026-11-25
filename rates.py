"""Rates, factors and judgement tables for the Cloud Workload Evaluator.

ALL PRICES ARE ESTIMATES. They approximate public list prices (USD, US East,
Linux, on-demand, late 2025) and will drift. Validate with each provider's own
pricing calculator before quoting a customer.

Keeping these tables apart from the calculation means a live pricing feed
(AWS Price List API, Azure Retail Prices API, Google Cloud Billing Catalog API)
can replace them later without touching the scoring code.
"""

import copy
import json
from pathlib import Path

PROVIDERS = ["aws", "azure", "gcp"]
PROVIDER_NAMES = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud"}

# Unit rates in USD (estimates).
RATES = {
    "vcpu_hr": {"label": "vCPU per hour", "aws": 0.0336, "azure": 0.0320, "gcp": 0.0316},
    "ram_gb_hr": {"label": "Memory GB per hour", "aws": 0.0045, "azure": 0.0042, "gcp": 0.00424},
    "gpu_hr": {"label": "Datacentre GPU per hour", "aws": 4.10, "azure": 3.40, "gcp": 3.67},
    "win_vcpu_hr": {"label": "Windows licence per vCPU-hour", "aws": 0.046, "azure": 0.046, "gcp": 0.046},
    "block_gb_month": {"label": "Block SSD per GB-month", "aws": 0.080, "azure": 0.085, "gcp": 0.100},
    "object_gb_month": {"label": "Object storage per GB-month", "aws": 0.023, "azure": 0.018, "gcp": 0.020},
    "egress_gb": {"label": "Internet egress per GB", "aws": 0.090, "azure": 0.087, "gcp": 0.120},
}
FREE_EGRESS_GB = 100

# Keep the hand-written estimates, then overlay live Azure prices if
# fetch_prices.py has written azure_prices.json next to this file.
BASE_RATES = copy.deepcopy(RATES)
AZURE_LIVE = None  # metadata about the live prices, when loaded


def apply_azure_prices(rates: dict, path: Path) -> dict | None:
    """Overlay live Azure prices from a JSON file onto `rates`. Returns the file's metadata."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        for key, value in data["rates"].items():
            if key in rates:
                rates[key]["azure"] = float(value)
        return data
    except (ValueError, KeyError, TypeError):
        return None  # a broken file falls back to the estimates


AZURE_LIVE = apply_azure_prices(RATES, Path(__file__).with_name("azure_prices.json"))

REGIONS = {
    "us": {"label": "US East", "aws": 1.00, "azure": 1.00, "gcp": 1.00},
    "uk": {"label": "UK (London)", "aws": 1.16, "azure": 1.10, "gcp": 1.17},
    "eu": {"label": "EU West", "aws": 1.10, "azure": 1.07, "gcp": 1.10},
    "apac": {"label": "Asia Pacific (Singapore)", "aws": 1.24, "azure": 1.20, "gcp": 1.23},
}

# Multiplier applied to compute and GPU cost.
COMMITMENTS = {
    "od": {"label": "On-demand", "aws": 1.00, "azure": 1.00, "gcp": 1.00},
    "y1": {"label": "1-year commitment", "aws": 0.70, "azure": 0.67, "gcp": 0.63},
    "y3": {"label": "3-year commitment", "aws": 0.50, "azure": 0.47, "gcp": 0.45},
}
GCP_MAX_SUSTAINED_USE_DISCOUNT = 0.20  # approximate, on-demand only

# Indicative currency conversion from USD (estimates).
FX = {"USD": 1.0, "GBP": 0.79, "EUR": 0.92}

# --- Judgement tables (analyst opinion, deliberately visible and editable) ---

# 0 to 5 capability rating per requirement.
COMPLIANCE = {
    "gdpr": {"label": "GDPR / UK data residency", "aws": 5, "azure": 5, "gcp": 5},
    "iso": {"label": "ISO 27001 / SOC 2", "aws": 5, "azure": 5, "gcp": 5},
    "hipaa": {"label": "HIPAA", "aws": 5, "azure": 5, "gcp": 5},
    "pci": {"label": "PCI DSS", "aws": 5, "azure": 5, "gcp": 5},
    "fedramp": {"label": "FedRAMP High / government", "aws": 5, "azure": 5, "gcp": 4},
    "sovereign": {"label": "Sovereign cloud", "aws": 4, "azure": 5, "gcp": 4},
}

# 0 to 100, by the customer's existing estate.
ECOSYSTEM_FIT = {
    "none": {"label": "No strong preference", "aws": 80, "azure": 75, "gcp": 75},
    "microsoft": {"label": "Microsoft-centric (M365, Entra ID)", "aws": 62, "azure": 95, "gcp": 60},
    "google": {"label": "Google-centric (Workspace, BigQuery)", "aws": 62, "azure": 62, "gcp": 95},
    "aws": {"label": "Already running on AWS", "aws": 95, "azure": 62, "gcp": 62},
}

# 0 to 100, by workload type.
WORKLOAD_FIT = {
    "web": {"label": "Web / API application", "aws": 90, "azure": 85, "gcp": 86},
    "analytics": {"label": "Data & analytics", "aws": 84, "azure": 86, "gcp": 95},
    "ml": {"label": "AI / ML (GPU)", "aws": 88, "azure": 90, "gcp": 92},
    "windows": {"label": "Windows / .NET line-of-business", "aws": 78, "azure": 96, "gcp": 70},
    "regulated": {"label": "Regulated data platform", "aws": 90, "azure": 90, "gcp": 85},
    "batch": {"label": "Batch / HPC", "aws": 86, "azure": 84, "gcp": 90},
}

WORKLOAD_NOTES = {
    "web": {
        "aws": "Widest service catalogue and mature managed options for web tiers (ECS, EKS, RDS, CloudFront).",
        "azure": "App Service and AKS integrate closely with Entra ID and Microsoft developer tooling.",
        "gcp": "Cloud Run and GKE are strong for containerised, autoscaling services.",
    },
    "analytics": {
        "aws": "Redshift, Athena and EMR cover most analytics patterns.",
        "azure": "Fabric and Synapse suit organisations already reporting in Power BI.",
        "gcp": "BigQuery is serverless and usually the simplest warehouse to operate.",
    },
    "ml": {
        "aws": "SageMaker, Bedrock and Trainium give broad ML and generative AI options.",
        "azure": "Azure OpenAI and Azure ML suit enterprises standardising on OpenAI models.",
        "gcp": "Vertex AI and TPUs are strong for training and serving at scale.",
    },
    "windows": {
        "aws": "Runs Windows well, but licence costs are higher without Microsoft discounts.",
        "azure": "Azure Hybrid Benefit and extended Windows and SQL Server support make it the natural home.",
        "gcp": "Supports Windows and SQL Server, with a smaller Microsoft-focused partner ecosystem.",
    },
    "regulated": {
        "aws": "Large compliance programme and a long HIPAA-eligible services list.",
        "azure": "Broad compliance offerings with strong sovereign and government options.",
        "gcp": "Assured Workloads helps enforce data residency and compliance controls.",
    },
    "batch": {
        "aws": "Spot instances and AWS Batch suit interruptible work.",
        "azure": "Azure Batch and Spot VMs cover HPC-style jobs.",
        "gcp": "Spot VMs and per-second billing suit short-lived batch jobs.",
    },
}

ESTATE_NOTES = {
    "microsoft": {"azure": "Reuses existing Microsoft agreements, Entra ID identity and in-house skills."},
    "google": {"gcp": "Builds on the existing Google Workspace and data estate."},
    "aws": {"aws": "No migration needed: extends an existing AWS landing zone, skills and commitments."},
}

DEFAULT_WEIGHTS = {"cost": 5, "compliance": 3, "ecosystem": 3, "fit": 3}
WEIGHT_LABELS = {"cost": "Cost", "compliance": "Compliance", "ecosystem": "Ecosystem fit", "fit": "Workload fit"}

PRESETS = {
    "Customer web app": dict(wtype="web", region="uk", instances=6, vcpu=4, ram_gb=16, hours=730, gpus=0,
                             os="linux", owns_windows_licences=False, commitment="y1", block_gb=1200,
                             object_gb=5000, egress_gb=3000, compliance=["gdpr", "iso"], estate="microsoft",
                             budget=1500, currency="USD"),
    "Analytics platform": dict(wtype="analytics", region="eu", instances=8, vcpu=8, ram_gb=64, hours=730, gpus=0,
                               os="linux", owns_windows_licences=False, commitment="y1", block_gb=4000,
                               object_gb=80000, egress_gb=1500, compliance=["gdpr", "iso"], estate="google",
                               budget=6000, currency="USD"),
    "GPU model training": dict(wtype="ml", region="us", instances=2, vcpu=12, ram_gb=96, hours=300, gpus=1,
                               os="linux", owns_windows_licences=False, commitment="od", block_gb=2000,
                               object_gb=20000, egress_gb=500, compliance=["iso"], estate="none",
                               budget=4000, currency="USD"),
    "Windows .NET estate": dict(wtype="windows", region="uk", instances=10, vcpu=4, ram_gb=16, hours=730, gpus=0,
                                os="windows", owns_windows_licences=True, commitment="y3", block_gb=3000,
                                object_gb=2000, egress_gb=800, compliance=["gdpr", "iso"], estate="microsoft",
                                budget=2500, currency="GBP"),
    "Healthcare data API": dict(wtype="regulated", region="us", instances=4, vcpu=8, ram_gb=32, hours=730, gpus=0,
                                os="linux", owns_windows_licences=False, commitment="y1", block_gb=2000,
                                object_gb=10000, egress_gb=2000, compliance=["hipaa", "iso", "pci"], estate="aws",
                                budget=2500, currency="USD"),
}
