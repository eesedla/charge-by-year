#!/usr/bin/env python3
"""
Regenerate the YEAR_DATA constant in this folder's script.js from cpd_data.csv.

Counts disciplinary cases per year, broken down by charge category. The
charge -> category mapping, category order, and colors are read directly from
the MAIN charges tool's script.js (the one containing `const DATA = [...]`),
so this chart always stays in sync with that tool. A case is counted once per
category it touches (deduplicated within the case), so a case whose charges
span two categories is counted in each of those two categories.

Setup:
  - Put cpd_data.csv next to this file (or edit CSV_PATH).
  - Point SOURCE_SCRIPT_JS at the main tool's script.js (the file with
    `const DATA = [...]`). By default it looks for ../script.js, then a
    sibling named source_script.js.

Run:
  python3 build_data.py
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
TARGET_SCRIPT_JS = HERE / "script.js"          # this chart's script.js (gets YEAR_DATA)
CSV_PATH         = HERE / "cpd_data.csv"

# The main tool's script.js, which holds `const DATA = [...]`.
# Edit this if your folder layout differs.
SOURCE_CANDIDATES = [HERE.parent / "script.js", HERE / "source_script.js"]

# ── 1. Locate and read the source mapping ────────────────────────────────────

def find_source():
    for p in SOURCE_CANDIDATES:
        if p.exists():
            txt = p.read_text(encoding="utf-8")
            if re.search(r"const DATA = \[", txt):
                return p, txt
    raise FileNotFoundError(
        "Could not find the main tool's script.js (with `const DATA = [...]`). "
        f"Looked in: {', '.join(str(p) for p in SOURCE_CANDIDATES)}. "
        "Edit SOURCE_CANDIDATES in this script to point at it."
    )

source_path, source_raw = find_source()
DATA = json.loads(re.search(r"const DATA = (\[.*?\]);", source_raw, re.DOTALL).group(1))

charge_to_group = {}
for g in DATA:
    for c in g["charges"]:
        charge_to_group[c["name"].strip().lower()] = g["group"]
group_order  = [g["group"] for g in DATA]
group_colors = {g["group"]: g["color"] for g in DATA}

# Same alias table the main tool uses to reconcile CSV charge spellings.
CSV_CHARGE_ALIASES = {
    "wcs violation":                                    "body camera violation",
    "arrest / criminal charge":                         "arrest or criminal charge",
    "conduct unbecoming / diminished esteem":           "diminished esteem of cpd",
    "preventable motor vehicle accident (mva)":         "preventable motor vehicle accident",
    "failure to report/intervene (uof)":                "failed to report/intervene",
    "database misuse (lerms/leads/ohleg)":              "database misuse",
    "improper handling of firearm":                     "improperly handled a firearm",
    "uniform/grooming violation":                       "uniform violation",
    "ops violation":                                    "ops investigation violation",
    "alcohol or smoking on duty / in uniform":          "consumed prohibited substance while on duty",
}

# ── 2. Parse CSV ─────────────────────────────────────────────────────────────

year_group_cases = defaultdict(lambda: defaultdict(int))  # year -> group -> cases
year_cases       = defaultdict(int)                        # year -> total cases
unmapped         = defaultdict(int)

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        m = re.search(r"(20\d\d)", row["Hearing Date"].strip())
        if not m:
            continue  # no hearing date -> can't place on a year axis
        year = int(m.group(1))
        year_cases[year] += 1

        charges = [c.strip() for c in row["Charges"].split(",") if c.strip()]
        groups_this_case = set()
        for charge in charges:
            ckey = charge.lower().strip()
            ckey = CSV_CHARGE_ALIASES.get(ckey, ckey)
            grp = charge_to_group.get(ckey)
            if grp is None:
                unmapped[charge] += 1
                continue
            groups_this_case.add(grp)
        for grp in groups_this_case:
            year_group_cases[year][grp] += 1

# ── 3. Build payload ─────────────────────────────────────────────────────────

years_out = []
for y in sorted(year_group_cases):
    segs = [
        {"group": g, "count": year_group_cases[y][g], "color": group_colors[g]}
        for g in group_order if year_group_cases[y][g] > 0
    ]
    years_out.append({"year": y, "total": year_cases[y], "segments": segs})

payload = {"groupOrder": group_order, "groupColors": group_colors, "years": years_out}

# ── 4. Write back into this folder's script.js ───────────────────────────────

raw = TARGET_SCRIPT_JS.read_text(encoding="utf-8")
data_json = json.dumps(payload, separators=(",", ":"))
new_raw, n = re.subn(
    r"const YEAR_DATA = .*?;",
    f"const YEAR_DATA = {data_json};",
    raw,
    count=1,
    flags=re.DOTALL,
)
if n == 0:
    raise RuntimeError("Could not find 'const YEAR_DATA = ...;' in script.js")
TARGET_SCRIPT_JS.write_text(new_raw, encoding="utf-8")

total = sum(year_cases.values())
print(f"Source mapping: {source_path}")
print(f"Updated {TARGET_SCRIPT_JS.name} — {total} dated cases across {len(years_out)} years.")
for y in years_out:
    print(f"  {y['year']}: {y['total']} cases")
if unmapped:
    print("\nUNMAPPED CHARGES (excluded — add to the main tool's DATA or to CSV_CHARGE_ALIASES):")
    for ch, cnt in sorted(unmapped.items(), key=lambda x: -x[1]):
        print(f"  [{cnt:4d}x]  {ch}")