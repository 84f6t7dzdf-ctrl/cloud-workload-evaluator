"""Fetch live Azure list prices into azure_prices.json.

Uses the public Azure Retail Prices API, which needs no account or key:
https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices

Run:  python fetch_prices.py            (US East, the base region the app uses)
      python fetch_prices.py --dry-run  (print what it found, write nothing)

rates.py loads azure_prices.json automatically when it exists, so the app then
shows real Azure compute and blob storage prices in place of the estimates.
Other Azure rates (GPU, disks, egress) and the AWS and Google Cloud rates stay
as estimates.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://prices.azure.com/api/retail/prices"
OUTPUT = Path(__file__).with_name("azure_prices.json")

# Reference VM used to price compute: 2 vCPU, 8 GB RAM, general purpose.
REFERENCE_SKU = "Standard_D2s_v5"
REFERENCE_VCPU = 2
REFERENCE_RAM_GB = 8


def query(odata_filter: str) -> list[dict]:
    """Return every item matching an OData filter, following NextPageLink."""
    url = f"{API_URL}?{urllib.parse.urlencode({'$filter': odata_filter})}"
    items: list[dict] = []
    while url:
        with urllib.request.urlopen(url, timeout=30) as resp:
            page = json.load(resp)
        items.extend(page.get("Items", []))
        url = page.get("NextPageLink")
    return items


def pick_linux_vm_price(items: list[dict]) -> float:
    """Hourly pay-as-you-go Linux price from the VM items for one SKU."""
    candidates = [
        i for i in items
        if i.get("type") == "Consumption"
        and i.get("unitOfMeasure") == "1 Hour"
        and "Windows" not in i.get("productName", "")
        and "Spot" not in i.get("skuName", "")
        and "Low Priority" not in i.get("skuName", "")
    ]
    if not candidates:
        raise ValueError("No Linux pay-as-you-go price found for the reference VM")
    return min(i["retailPrice"] for i in candidates)


def pick_hot_blob_price(items: list[dict]) -> float:
    """First-tier price per GB-month for Hot LRS block blob storage."""
    candidates = [
        i for i in items
        if i.get("type") == "Consumption"
        and "Block Blob" in i.get("productName", "")
        and float(i.get("tierMinimumUnits", 0)) == 0
        and "GB/Month" in i.get("unitOfMeasure", "")
    ]
    if not candidates:
        raise ValueError("No Hot LRS block blob price found")
    return min(i["retailPrice"] for i in candidates)


def split_vm_price(hourly: float, ram_to_vcpu_ratio: float) -> tuple[float, float]:
    """Split a whole-VM hourly price into per-vCPU and per-GB-RAM rates.

    Azure prices whole VMs, so we keep the same RAM-to-vCPU price ratio as the
    estimates in rates.py and solve: hourly = vcpu * v + ram * (ratio * v).
    """
    vcpu_rate = hourly / (REFERENCE_VCPU + REFERENCE_RAM_GB * ram_to_vcpu_ratio)
    return vcpu_rate, vcpu_rate * ram_to_vcpu_ratio


def fetch(region: str = "eastus") -> dict:
    # Imported here so this script still runs if rates.py is mid-edit.
    from rates import BASE_RATES

    est = BASE_RATES
    ratio = est["ram_gb_hr"]["azure"] / est["vcpu_hr"]["azure"]

    vm_items = query(
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
        f"and armSkuName eq '{REFERENCE_SKU}' and priceType eq 'Consumption'"
    )
    vm_hourly = pick_linux_vm_price(vm_items)
    vcpu_hr, ram_gb_hr = split_vm_price(vm_hourly, ratio)

    blob_items = query(
        f"serviceName eq 'Storage' and armRegionName eq '{region}' "
        f"and meterName eq 'Hot LRS Data Stored' and priceType eq 'Consumption'"
    )
    object_gb_month = pick_hot_blob_price(blob_items)

    return {
        "source": API_URL,
        "region": region,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "reference_vm": {"sku": REFERENCE_SKU, "hourly_usd": vm_hourly},
        "rates": {
            "vcpu_hr": round(vcpu_hr, 6),
            "ram_gb_hr": round(ram_gb_hr, 6),
            "object_gb_month": round(object_gb_month, 6),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", default="eastus",
                        help="Azure region name (default eastus, the app's base region)")
    parser.add_argument("--dry-run", action="store_true", help="print results without writing the file")
    args = parser.parse_args()

    try:
        result = fetch(args.region)
    except Exception as exc:  # network errors, API changes
        print(f"Could not fetch Azure prices: {exc}", file=sys.stderr)
        print("The app keeps using the estimates in rates.py.", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if not args.dry_run:
        OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
        print(f"Wrote {OUTPUT.name}. Restart the app to use these prices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
