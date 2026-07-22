#!/usr/bin/env python3
"""
Regenerate data.json from cpd_data.csv.

Counts disciplinary cases per year, broken down by charge category. A case is
counted once per category it touches (deduplicated within the case), so a
case whose charges span two categories is counted in each of those two
categories.

The charge -> category mapping, category order, and colors are defined here
statically (TAXONOMY) rather than read from another repo's script.js — this
tool needs nothing outside its own folder. It's kept in sync by hand with the
CPD-Bubble-Viz tool's TAXONOMY (same categories, same colors, per STYLE.md's
"same concept = same color" rule); if a charge moves categories there, mirror
the change here.

Setup:
  - Put cpd_data.csv next to this file (or edit CSV_PATH).

Run:
  python3 build_data.py
"""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

HERE      = Path(__file__).parent
DATA_JSON = HERE / "data.json"
CSV_PATH  = HERE / "cpd_data.csv"

# ── 1. Static taxonomy ────────────────────────────────────────────────────────
# Same 12 categories, same colors as CPD-Bubble-Viz's TAXONOMY — 12 distinct
# hues, no category sharing a lighter/darker shade of another category's hue.
# (Previously this chart used its own COLOR_OVERRIDES ramp — three hues each
# graduated into 3-4 shades to cover the 12 categories — which reads as a
# gradient implying an order these categories don't have. Fixed per Cid's
# review: reserve gradients for spectrums, not identity.)

GROUP_ORDER = [
    "Neglect of Duty", "Unprofessional Behavior", "Body Camera Violation",
    "Attendance", "Use of Force", "Integrity and Honesty", "Vehicle and Travel",
    "Compliance", "Criminal Conduct", "Improper Conduct", "Evidence and Property",
    "Drugs and Alcohol",
]

GROUP_COLORS = {
    "Neglect of Duty":         "#23685b",
    "Body Camera Violation":   "#7d6b9e",
    "Unprofessional Behavior": "#879599",
    "Attendance":              "#e6a94d",
    "Vehicle and Travel":      "#5fa896",
    "Use of Force":            "#d64d4d",
    "Integrity and Honesty":   "#4d7ea8",
    "Compliance":              "#a9d2cf",
    "Criminal Conduct":        "#ccd8db",
    "Evidence and Property":   "#e56430",
    "Improper Conduct":        "#d0d64c",
    "Drugs and Alcohol":       "#dbe7e3",
}

CHARGE_TO_GROUP = {
    # Neglect of Duty
    "failure to report/notify":              "Neglect of Duty",
    "lack of service":                       "Neglect of Duty",
    "neglect of duty":                       "Neglect of Duty",
    "duty report violation":                 "Neglect of Duty",
    "failure to supervise":                  "Neglect of Duty",
    "asleep on-duty":                        "Neglect of Duty",
    "failed to assist":                      "Neglect of Duty",
    "failed to provide language services":   "Neglect of Duty",
    "failed to take corrective action":      "Neglect of Duty",
    # Unprofessional Behavior
    "unprofessional conduct":                "Unprofessional Behavior",
    "offensive remarks":                     "Unprofessional Behavior",
    "diminished esteem of cpd":              "Unprofessional Behavior",
    "uniform violation":                     "Unprofessional Behavior",
    "appearance of impropriety":             "Unprofessional Behavior",
    "telecommunications violation":          "Unprofessional Behavior",
    "failed to identify":                    "Unprofessional Behavior",
    # Body Camera Violation (CSV only has the generic token below)
    "body camera violation":                 "Body Camera Violation",
    # Attendance
    "sick leave abuse":                      "Attendance",
    "absent without leave (awol)":           "Attendance",
    "refusal of mandatory overtime":         "Attendance",
    "tardiness":                             "Attendance",
    "attendance and overtime violations":    "Attendance",
    # Use of Force
    "use of force violation":                "Use of Force",
    "failed to report/intervene":            "Use of Force",
    "failed to de-escalate":                 "Use of Force",
    "failed to request medical attention":   "Use of Force",
    "improperly handled a firearm":          "Use of Force",
    "unauthorized ammunition/firearms":      "Use of Force",
    # Integrity and Honesty
    "untruthfulness":                        "Integrity and Honesty",
    "database misuse":                       "Integrity and Honesty",
    "cheating and plagiarism":               "Integrity and Honesty",
    "confidential information violation":    "Integrity and Honesty",
    "ethics violation":                      "Integrity and Honesty",
    # Vehicle and Travel
    "vehicle pursuit violation":             "Vehicle and Travel",
    "preventable motor vehicle accident":    "Vehicle and Travel",
    "travel violation":                      "Vehicle and Travel",
    # Compliance
    "insubordination":                       "Compliance",
    "unauthorized secondary employment":     "Compliance",
    "ops investigation violation":           "Compliance",
    # Criminal Conduct
    "arrest or criminal charge":             "Criminal Conduct",
    "violence in the workplace":             "Criminal Conduct",
    # Improper Conduct
    "improper search/frisk":                 "Improper Conduct",
    "improper arrest/detainment":            "Improper Conduct",
    "improper tow":                          "Improper Conduct",
    "improper stop":                         "Improper Conduct",
    "arrestee handling violation":           "Improper Conduct",
    "improper citation":                     "Improper Conduct",
    "mishandled juvenile":                   "Improper Conduct",
    # Evidence and Property
    "failed to safeguard equipment":         "Evidence and Property",
    "evidence collection violation":         "Evidence and Property",
    "failed to safeguard property":          "Evidence and Property",
    # Drugs and Alcohol
    "drug & alcohol testing policy violation":            "Drugs and Alcohol",
    "consumed prohibited substance while on duty":        "Drugs and Alcohol",
}

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

ID_PAT = re.compile(r"^\s*(\d{2})-\d+")

def year_of(row):
    """Year for a case: Hearing Date, else Effective date of termination,
    else the YY- prefix of the report ID (e.g. 17-126 -> 2017)."""
    for col in ("Hearing Date", "Effective date of termination"):
        m = re.search(r"(20\d\d)", (row.get(col) or "").strip())
        if m:
            return int(m.group(1))
    p = ID_PAT.match(row.get("Link to original report") or "")
    return 2000 + int(p.group(1)) if p else None

YEAR_MIN, YEAR_MAX = 2017, 2025  # exclude partial edge years (2016, 2026)

year_group_cases = defaultdict(lambda: defaultdict(int))  # year -> group -> cases
year_cases       = defaultdict(int)                        # year -> total cases
unmapped         = defaultdict(int)

with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        year = year_of(row)
        if year is None or not (YEAR_MIN <= year <= YEAR_MAX):
            continue
        year_cases[year] += 1

        charges = [c.strip() for c in row["Charges"].split(",") if c.strip()]
        groups_this_case = set()
        for charge in charges:
            ckey = charge.lower().strip()
            ckey = CSV_CHARGE_ALIASES.get(ckey, ckey)
            grp = CHARGE_TO_GROUP.get(ckey)
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
        {"group": g, "count": year_group_cases[y][g], "color": GROUP_COLORS[g]}
        for g in GROUP_ORDER if year_group_cases[y][g] > 0
    ]
    years_out.append({"year": y, "total": year_cases[y], "segments": segs})

payload = {"groupOrder": GROUP_ORDER, "groupColors": GROUP_COLORS, "years": years_out}

DATA_JSON.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

total = sum(year_cases.values())
print(f"Wrote {DATA_JSON.name} — {total} dated cases across {len(years_out)} years.")
for y in years_out:
    print(f"  {y['year']}: {y['total']} cases")
if unmapped:
    print("\nUNMAPPED CHARGES (excluded — add to CHARGE_TO_GROUP or CSV_CHARGE_ALIASES):")
    for ch, cnt in sorted(unmapped.items(), key=lambda x: -x[1]):
        print(f"  [{cnt:4d}x]  {ch}")
