#!/usr/bin/env python3
"""Build the star-schema warehouse from the synthetic source CSVs.

Staging -> dim_date, dim_customer (SCD Type 2), dim_product (SCD Type 2),
fact_orders (dimension keys resolved AS OF the order date) -> analysis
queries (sql/analysis.sql) + data tests (sql/checks.sql).

SQLite stands in for a cloud warehouse; the SQL is portable warehouse SQL.
Writes results/summary.json and one CSV per analysis query in results/.
"""
import csv
import json
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
SQL = BASE / "sql"
RESULTS = BASE / "results"
DB = BASE / "warehouse.db"


def load_csv(conn, table, path, columns):
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(
        f"CREATE TABLE {table} ({', '.join(c + ' TEXT' for c in columns)})")
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    conn.executemany(
        f"INSERT INTO {table} VALUES ({','.join('?' * len(columns))})",
        [[r[c] for c in columns] for r in rows])
    return len(rows)


def parse_sql_file(path):
    """Split a .sql file into (name, statement) pairs.

    Each statement is preceded by a `-- <kind>: <name>` comment line.
    """
    text = path.read_text()
    blocks = re.split(r"--\s*(analysis|check):\s*(.+)", text)
    # blocks: ['', kind, name, sql, kind, name, sql, ...]
    out = []
    for i in range(1, len(blocks) - 2, 3):
        name = blocks[i + 1].strip()
        stmt = blocks[i + 2].strip().rstrip(";").strip()
        if stmt:
            out.append((name, stmt))
    return out


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    n_cust = load_csv(conn, "stg_customer_cdc", DATA / "customers_cdc.csv",
                      ["customer_id", "name", "plan", "region", "segment",
                       "effective_from"])
    n_prod = load_csv(conn, "stg_product_cdc", DATA / "products_cdc.csv",
                      ["product_id", "name", "category", "price",
                       "effective_from"])
    n_orders = load_csv(conn, "stg_orders", DATA / "orders.csv",
                        ["order_id", "customer_id", "product_id",
                         "order_date", "quantity", "amount", "status"])

    # ---- dim_date: 2025-01-01 .. 2026-06-30 ----
    conn.executescript("""
        CREATE TABLE dim_date AS
        WITH RECURSIVE d(dt) AS (
          SELECT DATE('2025-01-01')
          UNION ALL SELECT DATE(dt, '+1 day') FROM d WHERE dt < '2026-06-30'
        )
        SELECT CAST(strftime('%Y%m%d', dt) AS INTEGER) AS date_key,
               dt AS date, CAST(strftime('%Y', dt) AS INTEGER) AS year,
               CAST(strftime('%m', dt) AS INTEGER) AS month,
               CAST((CAST(strftime('%m', dt) AS INTEGER) - 1) / 3 + 1 AS INTEGER) AS quarter,
               strftime('%Y-%m', dt) AS year_month
        FROM d;
    """)

    # ---- dim_customer: SCD Type 2 (surrogate key, effective dating) ----
    conn.executescript("""
        CREATE TABLE dim_customer AS
        SELECT ROW_NUMBER() OVER (ORDER BY customer_id, effective_from) AS customer_key,
               customer_id, name, plan, region, segment, effective_from,
               DATE(LEAD(effective_from) OVER (
                   PARTITION BY customer_id ORDER BY effective_from), '-1 day'
               ) AS effective_to,
               CASE WHEN LEAD(effective_from) OVER (
                   PARTITION BY customer_id ORDER BY effective_from) IS NULL
                    THEN 1 ELSE 0 END AS is_current
        FROM stg_customer_cdc;
    """)

    # ---- dim_product: SCD Type 2 over price ----
    conn.executescript("""
        CREATE TABLE dim_product AS
        SELECT ROW_NUMBER() OVER (ORDER BY product_id, effective_from) AS product_key,
               product_id, name, category, CAST(price AS REAL) AS price,
               effective_from,
               DATE(LEAD(effective_from) OVER (
                   PARTITION BY product_id ORDER BY effective_from), '-1 day'
               ) AS effective_to,
               CASE WHEN LEAD(effective_from) OVER (
                   PARTITION BY product_id ORDER BY effective_from) IS NULL
                    THEN 1 ELSE 0 END AS is_current
        FROM stg_product_cdc;
    """)

    # ---- fact_orders: dimension keys resolved AS OF the order date ----
    conn.executescript("""
        CREATE TABLE fact_orders AS
        SELECT o.order_id,
               dc.customer_key, dp.product_key,
               CAST(strftime('%Y%m%d', o.order_date) AS INTEGER) AS date_key,
               CAST(o.quantity AS INTEGER) AS quantity,
               CAST(o.amount AS REAL) AS amount, o.status
        FROM stg_orders o
        JOIN dim_customer dc
          ON dc.customer_id = o.customer_id
         AND dc.effective_from <= o.order_date
         AND (dc.effective_to IS NULL OR dc.effective_to >= o.order_date)
        JOIN dim_product dp
          ON dp.product_id = o.product_id
         AND dp.effective_from <= o.order_date
         AND (dp.effective_to IS NULL OR dp.effective_to >= o.order_date);
    """)
    conn.commit()

    summary = {
        "source_rows": {"customers_cdc": n_cust, "products_cdc": n_prod,
                        "orders": n_orders},
        "warehouse": {
            "dim_customer_rows": conn.execute(
                "SELECT COUNT(*) FROM dim_customer").fetchone()[0],
            "dim_product_rows": conn.execute(
                "SELECT COUNT(*) FROM dim_product").fetchone()[0],
            "dim_date_rows": conn.execute(
                "SELECT COUNT(*) FROM dim_date").fetchone()[0],
            "fact_orders_rows": conn.execute(
                "SELECT COUNT(*) FROM fact_orders").fetchone()[0],
            "current_customers": conn.execute(
                "SELECT COUNT(*) FROM dim_customer WHERE is_current = 1"
                ).fetchone()[0],
            "current_products": conn.execute(
                "SELECT COUNT(*) FROM dim_product WHERE is_current = 1"
                ).fetchone()[0],
        },
    }

    # ---- Analysis queries -> results/*.csv + summary ----
    analysis = {}
    for name, stmt in parse_sql_file(SQL / "analysis.sql"):
        cur = conn.execute(stmt)
        cols = [d[0] for d in cur.description]
        rows = [dict(r) for r in cur.fetchall()]
        with open(RESULTS / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        analysis[name] = rows
        print(f"analysis {name}: {len(rows)} rows")
    summary["analysis"] = analysis

    # ---- Data tests: every check must return 0 violations ----
    checks = []
    failed = False
    for name, stmt in parse_sql_file(SQL / "checks.sql"):
        value = conn.execute(stmt).fetchone()[0]
        ok = (value == 0)
        checks.append({"name": name, "violations": value, "pass": ok})
        print(f"check {name}: {value} violations {'PASS' if ok else 'FAIL'}")
        if not ok:
            failed = True
    summary["checks"] = checks
    summary["all_checks_pass"] = not failed

    with open(RESULTS / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary written to {RESULTS / 'summary.json'}")
    if failed:
        raise SystemExit("DATA TESTS FAILED — see summary.json")
    print("All data tests passed.")


if __name__ == "__main__":
    main()
