"""StorePulse: explain a week-over-week revenue change from a Shopify orders export."""
from __future__ import annotations

import numpy as np
import pandas as pd


def load_orders(path_or_df) -> pd.DataFrame:
    """Shopify export: one row per line item, order fields only on the first row of an order."""
    df = pd.read_csv(path_or_df) if not isinstance(path_or_df, pd.DataFrame) else path_or_df.copy()
    need = ["Name", "Created at", "Lineitem name", "Lineitem quantity", "Lineitem price"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    df["Created at"] = pd.to_datetime(df["Created at"], utc=True).dt.tz_localize(None)
    for c in ["Created at", "Discount Code", "Refunded Amount"]:
        if c in df.columns:
            df[c] = df.groupby("Name")[c].transform("first")
    df["date"] = df["Created at"].dt.normalize()
    df["line_revenue"] = df["Lineitem quantity"] * df["Lineitem price"]
    df["has_discount"] = df.get("Discount Code", pd.Series(index=df.index, dtype=object)).notna()
    df["Refunded Amount"] = df.get("Refunded Amount", 0)
    df["Refunded Amount"] = pd.to_numeric(df["Refunded Amount"], errors="coerce").fillna(0)
    return df


def _window(df, start, end):
    w = df[(df.date >= start) & (df.date <= end)]
    orders = w.drop_duplicates("Name")
    n = orders.Name.nunique()
    rev = w.line_revenue.sum()
    return {
        "revenue": rev, "orders": n, "aov": rev / n if n else 0.0,
        "discount_share": orders.has_discount.mean() if n else 0.0,
        "refunds": orders["Refunded Amount"].sum(),
        "by_product": w.groupby("Lineitem name").agg(rev=("line_revenue", "sum"),
                                                     units=("Lineitem quantity", "sum")),
    }


def explain(df: pd.DataFrame, days: int = 7) -> dict:
    if df.date.nunique() < 2 * days:
        raise ValueError(f"Need at least {2 * days} days of orders; file has {df.date.nunique()}.")
    end = df.date.max()
    cur_start = end - pd.Timedelta(days=days - 1)
    prev_end = cur_start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=days - 1)
    cur, prev = _window(df, cur_start, end), _window(df, prev_start, prev_end)

    delta = cur["revenue"] - prev["revenue"]
    pct = delta / prev["revenue"] if prev["revenue"] else np.nan
    orders_effect = (cur["orders"] - prev["orders"]) * prev["aov"]
    aov_effect = (cur["aov"] - prev["aov"]) * cur["orders"]

    prod = cur["by_product"].join(prev["by_product"], how="outer", lsuffix="_cur", rsuffix="_prev").fillna(0)
    prod["delta"] = prod.rev_cur - prod.rev_prev
    prod = prod.reindex(prod.delta.abs().sort_values(ascending=False).index)

    return {"end": end, "days": days, "cur": cur, "prev": prev, "delta": delta, "pct": pct,
            "orders_effect": orders_effect, "aov_effect": aov_effect, "products": prod}


def _m(x, c="$"):
    return f"{'-' if x < 0 else '+'}{c}{abs(x):,.0f}"


def write_email(e: dict, store: str = "your store", currency: str = "$") -> str:
    d, p = e["delta"], e["pct"]
    if abs(p) < 0.05 if not np.isnan(p) else True:
        head = f"Revenue is steady: {currency}{e['cur']['revenue']:,.0f} over the last {e['days']} days ({p:+.0%} vs the week before)."
    else:
        word = "up" if d > 0 else "down"
        head = (f"Revenue is {word} {abs(p):.0%} over the last {e['days']} days: "
                f"{currency}{e['cur']['revenue']:,.0f} vs {currency}{e['prev']['revenue']:,.0f}.")
    lines = [f"Subject: {store}: revenue {p:+.0%} this week", "", head, ""]

    big = "orders" if abs(e["orders_effect"]) >= abs(e["aov_effect"]) else "order value"
    lines.append(f"- Main driver: {big}. Orders went {e['prev']['orders']} -> {e['cur']['orders']} "
                 f"({_m(e['orders_effect'], currency)}); average order {currency}{e['prev']['aov']:.2f} -> "
                 f"{currency}{e['cur']['aov']:.2f} ({_m(e['aov_effect'], currency)}).")
    top = e["products"].head(2)
    for name, r in top.iterrows():
        if abs(r.delta) > 0:
            lines.append(f"- {name}: {_m(r.delta, currency)} ({r.units_prev:.0f} -> {r.units_cur:.0f} units).")
    ds0, ds1 = e["prev"]["discount_share"], e["cur"]["discount_share"]
    if abs(ds1 - ds0) >= 0.10:
        lines.append(f"- Discounts: {ds0:.0%} -> {ds1:.0%} of orders used a code.")
    rf0, rf1 = e["prev"]["refunds"], e["cur"]["refunds"]
    if abs(rf1 - rf0) >= 0.05 * max(e["prev"]["revenue"], 1):
        lines.append(f"- Refunds: {currency}{rf0:,.0f} -> {currency}{rf1:,.0f}.")
    lines += ["", "Correlation is not proof: check the items above before acting."]
    return "\n".join(lines)


def make_sample(seed: int = 0) -> pd.DataFrame:
    """28 days of fake Shopify rows. Last week: 'Alpha Mug' discount ends, so its sales drop."""
    rng = np.random.default_rng(seed)
    prods = {"Alpha Mug": 18.0, "Beta Tote": 25.0, "Gamma Candle": 12.0}
    rows, n = [], 1000
    for day in range(28):
        date = pd.Timestamp("2026-09-20") + pd.Timedelta(days=day)
        for _ in range(rng.poisson(14)):
            n += 1
            name = rng.choice(list(prods), p=[.5, .3, .2])
            if name == "Alpha Mug" and day >= 21 and rng.random() < 0.55:
                continue  # sales drop after discount ends
            promo = "SEPT20" if (day < 21 and rng.random() < 0.5) else None
            rows.append({"Name": f"#{n}", "Created at": date + pd.Timedelta(hours=int(rng.integers(8, 22))),
                         "Discount Code": promo, "Refunded Amount": 0.0,
                         "Lineitem name": name, "Lineitem quantity": int(rng.integers(1, 3)),
                         "Lineitem price": prods[name]})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    data = load_orders(sys.argv[1]) if len(sys.argv) > 1 else load_orders(make_sample())
    print(write_email(explain(data), store="Demo Store"))
