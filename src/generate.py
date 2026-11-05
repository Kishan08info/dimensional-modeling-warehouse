#!/usr/bin/env python3
"""Generate synthetic source data for the dimensional-modeling project.

Outputs (data/):
  customers_cdc.csv - one row per customer attribute version (plan / region /
                      segment) with effective_from; simulates a CDC feed from
                      a CRM where customer attributes change over time.
  products_cdc.csv  - one row per product price version with effective_from;
                      simulates a product-catalog price history.
  orders.csv        - operational orders; amount uses the product price in
                      force on the order date.

All data is SYNTHETIC, seeded (seed=42) so re-runs are byte-identical.
No real customers, products, or revenue.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
OUT = Path(__file__).resolve().parent.parent / "data"
START = date(2025, 1, 1)
END = date(2026, 6, 30)

PLANS = ["starter", "growth", "pro", "enterprise"]
PLAN_W = [0.40, 0.30, 0.20, 0.10]
REGIONS = ["US-West", "US-East", "EU", "APAC"]
REGION_W = [0.35, 0.30, 0.20, 0.15]
SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]
CATEGORIES = ["Analytics", "Collaboration", "Security", "Integrations"]

rng = random.Random(SEED)


def rand_date(d0, d1):
    return d0 + timedelta(days=rng.randrange((d1 - d0).days + 1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- Customers: initial version + optional plan / region changes ----
    customers_cdc = []
    customers = []  # (customer_id, signup_date)
    for i in range(1, 401):
        cid = f"C{i:04d}"
        signup = rand_date(date(2025, 1, 1), date(2025, 12, 31))
        plan = rng.choices(PLANS, weights=PLAN_W)[0]
        region = rng.choices(REGIONS, weights=REGION_W)[0]
        segment = {"starter": "SMB", "growth": "SMB", "pro": "Mid-Market",
                   "enterprise": "Enterprise"}[plan]
        if plan == "pro" and rng.random() < 0.3:
            segment = "SMB"
        customers.append((cid, signup))
        customers_cdc.append({
            "customer_id": cid, "name": f"Customer {i}", "plan": plan,
            "region": region, "segment": segment,
            "effective_from": signup.isoformat(),
        })
        # Plan change for ~40% of customers (mostly upgrades).
        if rng.random() < 0.40:
            change_date = rand_date(signup + timedelta(days=30),
                                    min(END, signup + timedelta(days=400)))
            if change_date > signup:
                idx = PLANS.index(plan)
                if rng.random() < 0.70 and idx < 3:
                    new_plan = PLANS[idx + 1]
                elif idx > 0:
                    new_plan = PLANS[idx - 1]
                else:
                    new_plan = plan
                if new_plan != plan:
                    customers_cdc.append({
                        "customer_id": cid, "name": f"Customer {i}",
                        "plan": new_plan, "region": region,
                        "segment": segment,
                        "effective_from": change_date.isoformat(),
                    })
                    plan = new_plan
        # Region change for ~15% of customers.
        if rng.random() < 0.15:
            change_date = rand_date(signup + timedelta(days=30),
                                    min(END, signup + timedelta(days=400)))
            if change_date > signup:
                new_region = rng.choice([r for r in REGIONS if r != region])
                customers_cdc.append({
                    "customer_id": cid, "name": f"Customer {i}",
                    "plan": plan, "region": new_region,
                    "segment": segment,
                    "effective_from": change_date.isoformat(),
                })
    customers_cdc.sort(key=lambda r: (r["customer_id"], r["effective_from"]))

    # ---- Products: base price + optional price change ----
    products_cdc = []
    products = []  # (product_id, [(effective_from, price), ...])
    for i in range(1, 25):
        pid = f"P{i:02d}"
        price = round(rng.uniform(19, 499), 2)
        eff = date(2025, 1, 1)
        products_cdc.append({
            "product_id": pid, "name": f"Product {i}",
            "category": CATEGORIES[(i - 1) % len(CATEGORIES)],
            "price": f"{price:.2f}", "effective_from": eff.isoformat(),
        })
        timeline = [(eff, price)]
        if rng.random() < 0.50:
            change_date = rand_date(date(2025, 3, 1), date(2026, 3, 31))
            new_price = round(price * rng.uniform(0.70, 1.30), 2)
            products_cdc.append({
                "product_id": pid, "name": f"Product {i}",
                "category": CATEGORIES[(i - 1) % len(CATEGORIES)],
                "price": f"{new_price:.2f}",
                "effective_from": change_date.isoformat(),
            })
            timeline.append((change_date, new_price))
        products.append((pid, timeline))
    products_cdc.sort(key=lambda r: (r["product_id"], r["effective_from"]))

    def price_asof(pid, on_date):
        timeline = dict(products)[pid]
        p = timeline[0][1]
        for eff, pr in timeline:
            if eff <= on_date:
                p = pr
            else:
                break
        return p

    # ---- Orders: 2,400, amount = price in force on the order date ----
    orders = []
    for i in range(1, 2401):
        cid, signup = rng.choice(customers)
        order_date = rand_date(max(signup, START), END)
        pid, _ = rng.choice(products)
        qty = rng.randint(1, 5)
        amount = round(price_asof(pid, order_date) * qty, 2)
        status = rng.choices(["paid", "refunded", "cancelled"],
                             weights=[0.92, 0.05, 0.03])[0]
        orders.append({
            "order_id": f"O{i:05d}", "customer_id": cid, "product_id": pid,
            "order_date": order_date.isoformat(), "quantity": qty,
            "amount": f"{amount:.2f}", "status": status,
        })
    orders.sort(key=lambda r: r["order_date"])

    for name, rows, fields in [
        ("customers_cdc.csv", customers_cdc,
         ["customer_id", "name", "plan", "region", "segment", "effective_from"]),
        ("products_cdc.csv", products_cdc,
         ["product_id", "name", "category", "price", "effective_from"]),
        ("orders.csv", orders,
         ["order_id", "customer_id", "product_id", "order_date",
          "quantity", "amount", "status"]),
    ]:
        with open(OUT / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")

    print(f"customers: {len(customers)}, products: {len(products)}")


if __name__ == "__main__":
    main()
