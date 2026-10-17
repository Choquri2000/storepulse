import pandas as pd
import streamlit as st

import storepulse as sp

st.set_page_config(page_title="StorePulse", layout="centered")
st.title("StorePulse")
st.caption("Why did your revenue change? Upload your Shopify orders export and get a plain-English answer. "
           "Processed in memory, never stored.")

up = st.file_uploader("Shopify orders export (CSV)", type="csv")
use_demo = st.checkbox("Use demo data")
days = st.select_slider("Compare last N days with the N days before", [7, 14, 28], value=7)
currency = st.text_input("Currency symbol", "$", max_chars=3)

src = sp.make_sample() if use_demo else (up if up else None)
if src is None:
    st.info("Upload a file or tick 'Use demo data'. In Shopify: Orders > Export > All orders > CSV.")
    st.stop()

try:
    df = sp.load_orders(src)
    e = sp.explain(df, days)
except Exception as err:
    st.error(f"Could not analyse this file: {err}")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Revenue", f"{currency}{e['cur']['revenue']:,.0f}", f"{e['pct']:+.0%}")
c2.metric("Orders", e["cur"]["orders"], int(e["cur"]["orders"] - e["prev"]["orders"]))
c3.metric("Avg order", f"{currency}{e['cur']['aov']:.2f}", f"{e['cur']['aov'] - e['prev']['aov']:+.2f}")

email = sp.write_email(e, "Your store", currency)
st.subheader("Your explanation")
st.code(email, language=None)
st.download_button("Download as text", email, "storepulse.txt")

st.subheader("Daily revenue")
daily = df.groupby("date").line_revenue.sum()
st.line_chart(daily)
st.subheader("Biggest product changes")
st.bar_chart(e["products"].head(8)["delta"])
