# Cloud Workload Evaluator

A Streamlit app that compares AWS, Azure and Google Cloud for a described workload. It estimates the monthly cost, scores each provider on cost, compliance, ecosystem fit and workload fit, and recommends one.

> **All prices are estimates.** They approximate public list prices (USD, late 2025). Validate them with each provider's pricing calculator before quoting a customer.

## What it does

- **Inputs:** workload type, region, instances, vCPU, RAM, hours, GPUs, OS and Windows licence ownership, pricing model, block storage, object storage, egress, compliance needs, existing estate, budget and currency. Five example workloads are included.
- **Cost model:** compute, GPU, Windows licences, storage and egress. Each is scaled by a regional factor, and compute is also scaled by a commitment discount. Google Cloud's sustained-use discount is approximated.
- **Scoring:** each dimension is scored out of 100, then combined with weights you set using sliders.
- **Output:** a recommendation with reasons, watch-outs and a confidence level, a side-by-side table, a cost breakdown chart, an editable rates table and a copyable summary.

## Project structure

```
app.py               Streamlit user interface
evaluator.py         Pure cost and scoring functions (no Streamlit, unit tested)
rates.py             Rates, factors and judgement tables (estimates, plus optional live Azure prices)
fetch_prices.py      Fetches live Azure prices into azure_prices.json
tests/               pytest tests
requirements.txt     Runtime dependencies (used by Streamlit Cloud)
requirements-dev.txt Test dependencies
```

Inputs, rates and scoring logic are kept separate on purpose. A live pricing feed can replace `rates.py` later without touching the scoring code.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
streamlit run app.py             # opens http://localhost:8501
pytest -q                        # runs the tests
```

## Live Azure prices (optional)

`fetch_prices.py` pulls current Azure list prices from the public Azure Retail Prices API. It needs no account or key.

```bash
python fetch_prices.py            # US East, writes azure_prices.json
python fetch_prices.py --dry-run  # print the prices only
```

When `azure_prices.json` exists, `rates.py` uses it for Azure's vCPU, memory and blob storage rates, and the app shows a banner with the fetch date. Azure prices whole VMs, so the script prices a Standard_D2s_v5 (2 vCPU, 8 GB) and splits it into per-vCPU and per-GB rates. Everything else stays as estimates. Commit `azure_prices.json` to use the live prices on Streamlit Cloud, or delete it to go back to the estimates.

## Deploy to Streamlit Community Cloud (free URL)

1. Create a new **public** repository on GitHub and upload all of these files, keeping the `tests/` folder.
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, then choose **Deploy a public app from GitHub**.
4. Pick your repository and the `main` branch, and set the main file path to `app.py`.
5. Optionally, choose a custom subdomain under **App URL**.
6. Click **Deploy**. The first build takes 1 to 3 minutes, and you then get a URL like `https://your-app.streamlit.app`.

Every push to `main` redeploys the app automatically. Free apps go to sleep after a period without visits, so open the link a few minutes before a demo.

## Method and limitations

- Monthly cost = compute (vCPU and memory rates × hours × instances) + GPUs + Windows licences + block and object storage + internet egress after 100 GB free. Each part is scaled by region, and compute and GPU are also scaled by commitment.
- Cost score = 100 × cheapest cost ÷ this provider's cost. Compliance is the average of 0 to 5 ratings for the selected requirements. Ecosystem and workload fit are analyst judgements stored in `rates.py`.
- The estimates leave out support plans, managed databases, networking appliances, inter-zone traffic, negotiated discounts and taxes.

## Possible next steps

- Pull live prices from the AWS Price List API, Azure Retail Prices API and Google Cloud Billing Catalog API into a nightly cache.
- Save evaluations per customer, and add sign-in.
- Use an LLM to turn a free-text workload description into the structured inputs. Keep all numbers in deterministic code.
