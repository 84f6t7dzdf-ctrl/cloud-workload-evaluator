import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_prices as F  # noqa: E402
import rates as R  # noqa: E402

# Trimmed examples in the shape the Azure Retail Prices API returns.
VM_ITEMS = [
    {"type": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines Dsv5 Series",
     "skuName": "D2s v5", "retailPrice": 0.096},
    {"type": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines Dsv5 Series Windows",
     "skuName": "D2s v5", "retailPrice": 0.188},
    {"type": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines Dsv5 Series",
     "skuName": "D2s v5 Spot", "retailPrice": 0.0115},
    {"type": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines Dsv5 Series",
     "skuName": "D2s v5 Low Priority", "retailPrice": 0.0192},
]
BLOB_ITEMS = [
    {"type": "Consumption", "productName": "General Block Blob v2", "tierMinimumUnits": 0.0,
     "unitOfMeasure": "1 GB/Month", "retailPrice": 0.0184},
    {"type": "Consumption", "productName": "General Block Blob v2", "tierMinimumUnits": 51200.0,
     "unitOfMeasure": "1 GB/Month", "retailPrice": 0.0177},
    {"type": "Consumption", "productName": "Files v2", "tierMinimumUnits": 0.0,
     "unitOfMeasure": "1 GB/Month", "retailPrice": 0.06},
]


def test_vm_price_ignores_windows_spot_and_low_priority():
    assert F.pick_linux_vm_price(VM_ITEMS) == 0.096


def test_blob_price_uses_first_tier_block_blob():
    assert F.pick_hot_blob_price(BLOB_ITEMS) == 0.0184


def test_split_vm_price_adds_back_up():
    vcpu, ram = F.split_vm_price(0.096, ram_to_vcpu_ratio=0.0042 / 0.032)
    assert 2 * vcpu + 8 * ram == pytest.approx(0.096)


def test_missing_prices_raise():
    with pytest.raises(ValueError):
        F.pick_linux_vm_price([])
    with pytest.raises(ValueError):
        F.pick_hot_blob_price([])


def test_fetch_builds_rates_from_api(monkeypatch):
    def fake_query(odata_filter):
        return VM_ITEMS if "Virtual Machines" in odata_filter else BLOB_ITEMS
    monkeypatch.setattr(F, "query", fake_query)
    result = F.fetch("eastus")
    assert result["reference_vm"]["hourly_usd"] == 0.096
    assert result["rates"]["object_gb_month"] == 0.0184


def test_rates_overlay_from_file(tmp_path):
    path = tmp_path / "azure_prices.json"
    path.write_text(json.dumps({"region": "eastus", "fetched_at": "today",
                                "rates": {"vcpu_hr": 0.03, "object_gb_month": 0.0184}}))
    rates = json.loads(json.dumps(R.BASE_RATES))
    meta = R.apply_azure_prices(rates, path)
    assert meta["region"] == "eastus"
    assert rates["vcpu_hr"]["azure"] == 0.03
    assert rates["vcpu_hr"]["aws"] == R.BASE_RATES["vcpu_hr"]["aws"]


def test_rates_overlay_ignores_missing_or_broken_file(tmp_path):
    rates = json.loads(json.dumps(R.BASE_RATES))
    assert R.apply_azure_prices(rates, tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert R.apply_azure_prices(rates, bad) is None
    assert rates == R.BASE_RATES
