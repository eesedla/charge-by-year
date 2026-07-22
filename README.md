# charge-by-year

Types of misconduct disciplined, by year — Signal Cleveland.

## Run it

```
python3 build_data.py   # reads cpd_data.csv, writes data.json
python3 -m http.server   # then open http://localhost:8000
```

`index.html` loads the chart via `fetch('./data.json')`, so it needs to be served
over HTTP (not opened as a `file://` URL — browsers block local `fetch` of JSON
under that scheme). Everything the build needs (`cpd_data.csv`) is committed in
this repo; there are no paths outside this folder.

The charge → category mapping and category colors are defined in `build_data.py`
(`CHARGE_TO_GROUP` / `GROUP_COLORS`) — kept in sync by hand with CPD-Bubble-Viz's
taxonomy (same categories, same colors, per STYLE.md's "same concept = same
color" rule). If a charge moves categories there, mirror the change here.
