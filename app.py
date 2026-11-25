"""Cloud Workload Evaluator: Streamlit front end.

Run locally:  streamlit run app.py
All prices are estimates. See rates.py.
"""

import copy

import pandas as pd
import streamlit as st

import rates as R
from evaluator import Workload, confidence, evaluate, from_usd, reasons, risks

st.set_page_config(page_title="Cloud Workload Evaluator", page_icon="☁️", layout="wide")

COMPONENT_LABELS = {"compute": "Compute", "gpu": "GPU", "licence": "Windows licences",
                    "storage": "Storage", "egress": "Egress"}


def money(usd: float, currency: str) -> str:
    symbol = {"USD": "$", "GBP": "£", "EUR": "€"}[currency]
    return f"{symbol}{from_usd(usd, currency):,.0f}"


# ---------- Sidebar: workload inputs ----------
with st.sidebar:
    st.header("Workload")
    preset_name = st.selectbox("Start from an example", list(R.PRESETS))
    p = R.PRESETS[preset_name]
    k = preset_name  # widget keys change with the preset, so values reset cleanly

    wtype = st.selectbox("Type", list(R.WORKLOAD_FIT), index=list(R.WORKLOAD_FIT).index(p["wtype"]),
                         format_func=lambda x: R.WORKLOAD_FIT[x]["label"], key=f"wtype{k}")
    region = st.selectbox("Region", list(R.REGIONS), index=list(R.REGIONS).index(p["region"]),
                          format_func=lambda x: R.REGIONS[x]["label"], key=f"region{k}")

    st.subheader("Compute")
    c1, c2, c3 = st.columns(3)
    instances = c1.number_input("Instances", 0, 1000, p["instances"], key=f"inst{k}")
    vcpu = c2.number_input("vCPU each", 1, 448, p["vcpu"], key=f"vcpu{k}")
    ram_gb = c3.number_input("RAM GB", 1, 12000, p["ram_gb"], key=f"ram{k}")
    c1, c2 = st.columns(2)
    hours = c1.number_input("Hours / month", 0, 744, p["hours"], step=10, key=f"hours{k}")
    gpus = c2.number_input("GPUs each", 0, 16, p["gpus"], key=f"gpu{k}")
    os_choice = st.radio("OS", ["linux", "windows"], index=["linux", "windows"].index(p["os"]),
                         format_func=str.capitalize, horizontal=True, key=f"os{k}")
    owns = st.checkbox("Customer owns Windows Server licences with Software Assurance",
                       value=p["owns_windows_licences"], key=f"ahb{k}")
    commitment = st.selectbox("Pricing model", list(R.COMMITMENTS),
                              index=list(R.COMMITMENTS).index(p["commitment"]),
                              format_func=lambda x: R.COMMITMENTS[x]["label"], key=f"commit{k}")

    st.subheader("Storage and traffic")
    c1, c2, c3 = st.columns(3)
    block_gb = c1.number_input("Block GB", 0, 10_000_000, p["block_gb"], step=50, key=f"block{k}")
    object_gb = c2.number_input("Object GB", 0, 100_000_000, p["object_gb"], step=100, key=f"obj{k}")
    egress_gb = c3.number_input("Egress GB/mo", 0, 100_000_000, p["egress_gb"], step=100, key=f"egress{k}")

    st.subheader("Compliance and context")
    compliance = st.multiselect("Compliance needs", list(R.COMPLIANCE), default=p["compliance"],
                                format_func=lambda x: R.COMPLIANCE[x]["label"], key=f"comp{k}")
    estate = st.selectbox("Existing estate", list(R.ECOSYSTEM_FIT), index=list(R.ECOSYSTEM_FIT).index(p["estate"]),
                          format_func=lambda x: R.ECOSYSTEM_FIT[x]["label"], key=f"estate{k}")
    c1, c2 = st.columns(2)
    currency = c1.selectbox("Currency", list(R.FX), index=list(R.FX).index(p["currency"]), key=f"cur{k}")
    budget = c2.number_input(f"Budget / month ({currency})", 0, 100_000_000, p["budget"], step=100, key=f"budget{k}")

    st.subheader("What matters most")
    weights = {key: st.slider(label, 0, 10, R.DEFAULT_WEIGHTS[key], key=f"w_{key}")
               for key, label in R.WEIGHT_LABELS.items()}

workload = Workload(wtype=wtype, region=region, instances=int(instances), vcpu=int(vcpu), ram_gb=ram_gb,
                    hours=hours, gpus=int(gpus), os=os_choice, owns_windows_licences=owns, commitment=commitment,
                    block_gb=block_gb, object_gb=object_gb, egress_gb=egress_gb, compliance=compliance,
                    estate=estate, budget=budget, currency=currency)

# ---------- Editable rates ----------
if "rates" not in st.session_state:
    st.session_state.rates = copy.deepcopy(R.RATES)

# ---------- Main page ----------
st.title("Cloud Workload Evaluator")
st.caption("Compare AWS, Azure and Google Cloud for a workload on indicative cost and fit.")
st.warning("All prices are estimates (list-price approximations, late 2025). "
           "Validate with each provider's pricing calculator before quoting.", icon="⚠️")

ranked = evaluate(workload, weights, st.session_state.rates)
top = ranked[0]
conf_label, conf_text = confidence(ranked)

with st.container(border=True):
    st.caption("RECOMMENDED OPTION")
    st.subheader(top.name)
    m1, m2, m3 = st.columns(3)
    m1.metric("Score", f"{top.score:.1f} / 100")
    m2.metric("Per month (est.)", money(top.total, currency))
    m3.metric("Per year (est.)", money(top.total * 12, currency))
    if budget:
        (st.error if top.over_budget else st.success)("Over budget" if top.over_budget else "Within budget")
    c1, c2 = st.columns(2)
    c1.markdown("**Why**\n" + "\n".join(f"- {r}" for r in reasons(ranked, workload)))
    c2.markdown("**Watch-outs**\n" + "\n".join(f"- {r}" for r in risks(ranked, workload)))
    st.info(f"**{conf_label}.** {conf_text}")

st.subheader("Side-by-side")
cheapest = min(r.total for r in ranked)
table = pd.DataFrame([{
    "Provider": r.name,
    "Score": round(r.score, 1),
    "Per month (est.)": money(r.total, currency),
    "Per year (est.)": money(r.total * 12, currency),
    "vs cheapest": "cheapest" if r.total == cheapest else f"+{round(100 * (r.total - cheapest) / cheapest)}%",
    "Budget": ("Over" if r.over_budget else "Within") if budget else "–",
} for r in ranked])
st.dataframe(table, hide_index=True, width="stretch")

c1, c2 = st.columns(2)
with c1:
    st.subheader(f"Monthly cost breakdown ({currency})")
    breakdown = pd.DataFrame(
        {COMPONENT_LABELS[c]: [from_usd(r.breakdown[c], currency) for r in ranked] for c in COMPONENT_LABELS},
        index=[r.name for r in ranked],
    )
    breakdown = breakdown.loc[:, (breakdown > 0).any()]
    st.bar_chart(breakdown, horizontal=True, stack=True)
    st.caption("Egress includes the first 100 GB free each month on every provider.")
with c2:
    st.subheader("Score by dimension (0 to 100)")
    dims = pd.DataFrame({R.WEIGHT_LABELS[d]: [round(r.dimensions[d]) for r in ranked] for d in R.WEIGHT_LABELS},
                        index=[r.name for r in ranked])
    st.dataframe(dims, width="stretch")
    st.caption("Cost is relative to the cheapest option (cheapest = 100). The other dimensions "
               "are analyst judgements from rates.py, so they can be challenged.")

with st.expander("Assumptions and rates (editable)"):
    st.caption("USD, US East, Linux, on-demand. Region and commitment factors are applied on top.")
    rate_df = pd.DataFrame({key: {"Rate": v["label"], **{R.PROVIDER_NAMES[p]: v[p] for p in R.PROVIDERS}}
                            for key, v in st.session_state.rates.items()}).T
    edited = st.data_editor(rate_df, disabled=["Rate"], width="stretch", key="rate_editor")
    new_rates = {key: {"label": row["Rate"], **{p: float(row[R.PROVIDER_NAMES[p]]) for p in R.PROVIDERS}}
                 for key, row in edited.iterrows()}
    if new_rates != st.session_state.rates:
        st.session_state.rates = new_rates
        st.rerun()
    if st.button("Reset rates"):
        st.session_state.rates = copy.deepcopy(R.RATES)
        st.session_state.pop("rate_editor", None)
        st.rerun()

with st.expander("Summary for the customer"):
    lines = [
        "Cloud option evaluation (indicative estimates)",
        f"Workload: {R.WORKLOAD_FIT[wtype]['label']}, {R.REGIONS[region]['label']}, {instances} x {vcpu} vCPU / "
        f"{ram_gb} GB, {hours} h/month, {os_choice.capitalize()}, {R.COMMITMENTS[commitment]['label']}",
        f"Storage: {block_gb} GB block, {object_gb} GB object. Egress: {egress_gb} GB/month.",
        "",
        *[f"{i + 1}. {r.name}: score {r.score:.1f}, ~{money(r.total, currency)}/month"
          f"{' (over budget)' if r.over_budget else ''}" for i, r in enumerate(ranked)],
        "",
        f"Recommendation: {top.name}. {conf_label}: {conf_text}",
        "All prices are list-price estimates; validate with provider calculators before quoting.",
    ]
    st.code("\n".join(lines), language=None)
