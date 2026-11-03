"""Streamlit What-If panel: simulate a supplier delay and see cascading stock-out impact."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # make `src` importable however Streamlit is launched

import pandas as pd
import plotly.express as px
import streamlit as st
from src import whatif
from src.db import read_sql

st.set_page_config(page_title="Control Tower — What-If", layout="wide")
st.title("What-If: supplier delay")


@st.cache_data(ttl=300)
def load():
    inv = read_sql("""SELECT d.product_id, d.warehouse_id, p.category, p.supplier_id, p.unit_cost, d.current_stock AS current_stock_level,
                             d.avg_daily_demand
                      FROM kpi_doi d JOIN dim_products p USING (product_id)
                      WHERE d.ts = (SELECT MAX(ts) FROM kpi_doi)""")
    sup = read_sql("SELECT supplier_id, supplier_name, base_lead_time_days FROM dim_suppliers ORDER BY supplier_id")
    lt = read_sql("""SELECT supplier_id, AVG(EXTRACT(EPOCH FROM (actual_delivery_date-order_date))/86400) AS lead
                     FROM fact_shipments WHERE actual_delivery_date IS NOT NULL GROUP BY 1""")
    return inv, sup.merge(lt, on="supplier_id", how="left")


inv, sup = load()
name = st.sidebar.selectbox("Supplier", sup["supplier_name"])
delay = st.sidebar.slider("Additional delay (days)", 0, 21, 14)
row = sup[sup["supplier_name"] == name].iloc[0]
base = float(row["lead"] if pd.notna(row["lead"]) else row["base_lead_time_days"])
st.sidebar.caption(f"Baseline lead time: {base:.1f} days")

sim = whatif.simulate_supplier_delay(inv, int(row["supplier_id"]), delay, base)
c1, c2, c3 = st.columns(3)
c1.metric("SKUs newly stocked out", int(sim["newly_stocked_out"].sum()))
c2.metric("Units at risk", f"{sim['units_at_risk'].sum():,.0f}")
c3.metric("Value at risk (cost basis)", f"{sim['value_at_risk'].sum():,.0f}")
show_all = st.sidebar.checkbox("Also show SKUs not affected by this delay", value=False)
impacted = sim[sim["units_at_risk"] > 0]
cat = whatif.summarize_by_category(sim)
st.plotly_chart(px.bar(cat, x="category", y="value_at_risk", title="Cascading impact by category"), width="stretch")
table = sim[sim["avg_daily_demand"] > 0] if show_all else impacted
st.caption(f"{len(impacted)} of {len(sim)} SKUs supplied by {name} are affected by a {delay}-day delay.")
if table.empty:
    st.info("No SKUs are affected at this delay. Try a longer delay or another supplier.")
st.dataframe(table[["product_id", "warehouse_id", "category", "days_cover", "incremental_stockout_days", "units_at_risk", "value_at_risk"]].round(2).head(200))
st.caption("Assumes the next replenishment is due at the supplier's baseline lead time and no alternate sourcing.")
