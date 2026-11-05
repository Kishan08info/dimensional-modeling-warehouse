# Dimensional Data Modeling — Star Schema Warehouse with SCD Type 2

**SYNTHETIC DATA. Portfolio skill demo, NOT work experience.** No real
customers, products, or revenue. SQLite stands in for a cloud warehouse; the
SQL is portable warehouse SQL, not a claim of Snowflake/BigQuery production
experience.

## Business question

Customer attributes change — plans upgrade, regions move, product prices
change. If you overwrite them, history rewrites itself: last year's revenue
suddenly looks like it came from this year's plan. How do you model a
warehouse so every order is attributed to the customer and product **as they
were on the order date**, while still being able to report by today's
attributes?

This is the exact shape of work in current Data Engineer postings: data
modeling and governed serving (Shield AI, Data Engineer, Finance), data
modeling + ETL + data warehousing (NielsenIQ, Data Engineer), and pipelines
landing CRM data in a cloud warehouse (PointClickCare, Salesforce/Marketo →
BigQuery; Northbeam, REST APIs + batch processing).

## Approach

1. **Source data** (`src/generate.py`, seeded — re-runs are identical):
   `customers_cdc.csv` (588 rows — a CDC feed of customer attribute
   versions), `products_cdc.csv` (35 rows — product price history),
   `orders.csv` (2,400 orders, Jan 2025–Jun 2026; each amount uses the
   product price in force on the order date).
2. **Dimensions** (`src/build.py`): `dim_customer` and `dim_product` are
   **SCD Type 2** — surrogate keys, `effective_from` / `effective_to`,
   `is_current` flag, one row per attribute version. `dim_date` covers
   2025-01-01–2026-06-30 (546 days).
3. **Fact** (`fact_orders`): 2,400 rows; customer and product keys resolved
   **as of the order date** via effective-range joins — never by current
   attribute.
4. **Analysis** (`sql/analysis.sql`, 9 queries): monthly revenue, revenue by
   plan and region **at order time vs current** (the comparison that shows
   why SCD2 matters), revenue by category, plan upgrades/downgrades, top
   customers by lifetime value. One CSV per query in `results/`.
5. **Data tests** (`sql/checks.sql`, 12 checks): surrogate-key uniqueness,
   no overlapping SCD2 ranges, no invalid effective ranges, every order
   resolves to a dimension version, fact row count and paid revenue
   reconcile exactly to raw, plan attribution and amount match the source
   CDC as of each order date.

## Results (real numbers from actual runs, 2026-11-05)

Verified byte-identical on a from-scratch re-run
(`rm -rf data results warehouse.db && bash run_demo.sh`).

### Warehouse

- 400 customers → **588 dim_customer rows** (164 customers changed plan
  or region); 24 products → **35 dim_product rows** (11 changed price).
- **2,400 fact rows** — every order resolved to an as-of dimension version.

### Plan changes

- 188 attribute-version transitions: **93 upgrades, 33 downgrades**,
  62 same-plan versions (region changes).

### Revenue

- 2,191 paid orders, **$1,733,395.50** paid revenue; 133 refunded and
  76 cancelled orders ($163,641.20 excluded from paid revenue).
- Monthly paid revenue: **$4,914.62** (Jan 2025, 6 orders) → peak
  **$177,378.20** (Jan 2026, 231 orders) → $154,585.89 (Jun 2026).
- Security is the top category ($504,808.72), then Analytics ($490,790.98).

### Why SCD Type 2 matters — the same revenue, two attributions

| Plan | Revenue at order time | Revenue by current plan |
|---|---|---|
| starter | $628,046.70 | $575,032.30 |
| growth | $502,115.41 | $460,602.66 |
| pro | $388,488.47 | $476,913.43 |
| enterprise | $214,744.92 | $220,847.11 |

Total is identical ($1,733,395.50) either way — but $53,014.40 of starter
revenue and $41,512.75 of growth revenue actually belongs to customers who
have since upgraded, and pro's current-plan revenue is **$88,424.96 higher**
than its at-order-time revenue. Overwriting attributes (SCD Type 1) would
misstate every one of those numbers. The region picture is the same story
at smaller scale (US-West $591,856.93 at order time vs $582,068.00 current).

### Top customer

- C0217 (starter, current): 12 paid orders, **$13,717.87** lifetime value.

### Data tests

- **12/12 checks pass, 0 violations** — including the two as-of
  correctness checks: every fact row's plan matches the CDC plan in force
  on its order date, and every amount equals price-as-of × quantity.

## Run it

```bash
bash run_demo.sh   # generate -> build warehouse -> analysis -> tests
```

Python 3, standard library only (`sqlite3`, `csv`, `json`). Outputs:
`results/summary.json` plus one CSV per analysis query. The warehouse
itself (`warehouse.db`) is gitignored; rebuild it any time with
`bash run_demo.sh`.

## Files

- `src/generate.py` — seeded synthetic source data (CDC feeds + orders)
- `src/build.py` — staging → SCD2 dimensions → fact → analysis + tests
- `sql/analysis.sql` — 9 analysis queries
- `sql/checks.sql` — 12 data tests
- `data/` — generated source CSVs
- `results/` — `summary.json` + analysis CSVs
