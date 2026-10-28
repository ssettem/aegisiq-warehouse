"""
Run the four business queries in sql/02_business_queries.sql against
aegisiq.db, print each answer, save it to results/<query name>.csv, and
copy the results into dashboard/index.html so the dashboard stays current.

Run after etl/load_warehouse.py.
"""

import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB = ROOT / "aegisiq.db"
QUERIES = ROOT / "sql" / "02_business_queries.sql"
RESULTS = ROOT / "results"
DASHBOARD = ROOT / "dashboard" / "index.html"

# Split the file on its "-- name: xxx" lines -> {name: sql text}
parts = re.split(r"^-- name:\s*(\w+)\s*$", QUERIES.read_text(), flags=re.MULTILINE)
queries = dict(zip(parts[1::2], parts[2::2]))

RESULTS.mkdir(exist_ok=True)
con = sqlite3.connect(DB)
dashboard_data = {}
for name, sql in queries.items():
    df = pd.read_sql_query(sql, con)
    df.to_csv(RESULTS / f"{name}.csv", index=False)
    dashboard_data[name] = df.to_dict(orient="records")
    print(f"\n=== {name} ({len(df)} rows) ===")
    print(df.head(12).to_string(index=False))
con.close()

# Put the results inside the dashboard, between its DATA_START / DATA_END markers.
html = DASHBOARD.read_text()
data_line = "const DATA = " + json.dumps(dashboard_data) + ";"
html = re.sub(r"(// DATA_START\n).*?(\n\s*// DATA_END)",
              lambda m: m.group(1) + data_line + m.group(2), html, flags=re.DOTALL)
DASHBOARD.write_text(html)
print(f"\nSaved {len(queries)} result files to {RESULTS} and updated {DASHBOARD}")
