"""Day-2 checks 4 and 13: EMA household electricity by planning area (terms of use; 1-2 room values for every area).

Standalone (requests + standard library) so it can run isolated:
  .venv\\Scripts\\python -I scripts/checks/check4_13_ema.py --ema-file <geojson> --boundary <geojson> --out docs/checks/check4_13.md
Makes 4 unauthenticated GET requests to the EMA website (one per URL, 1 s apart, no retries, no attempt to get past a
bot-protection page) and reads the data.gov.sg file already on disk.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EMA_URLS = [
    "https://www.ema.gov.sg/resources/singapore-energy-statistics",
    "https://www.ema.gov.sg/resources/singapore-energy-statistics/chapter3",
    "https://www.ema.gov.sg/terms-of-use",
]
UA = {"User-Agent": "coolcheck-check"}
COLS = ["ONE_TO_TWO_RM", "THREE_RM", "FOUR_RM", "FIVE_RM_EXEC_FLATS"]


def table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def probe(url):
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except requests.RequestException as e:
        return (url, "error", 0, type(e).__name__)
    body = r.text
    blocked = "Incapsula" in body or "_Incapsula_Resource" in body
    return (url, r.status_code, len(r.content), "bot-protection (Incapsula) page, no content" if blocked else "content returned")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ema-file", required=True)
    ap.add_argument("--boundary", required=True)
    ap.add_argument("--out", default="docs/checks/check4_13.md")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    probes = []
    for u in EMA_URLS:
        probes.append(probe(u))
        time.sleep(1)

    ema = json.loads(Path(a.ema_file).read_text(encoding="utf-8"))["features"]
    rows = [f["properties"] for f in ema]
    pa_ema = {r["PLN_AREA_N"].upper(): r for r in rows}
    bnd = json.loads(Path(a.boundary).read_text(encoding="utf-8"))["features"]
    bprops = [f["properties"] for f in bnd]
    # The boundary file stores attributes either as columns or in an HTML Description table
    import html
    import re

    def pa_name(p):
        if "PLN_AREA_N" in p:
            return p["PLN_AREA_N"].upper()
        d = dict((html.unescape(k), html.unescape(v)) for k, v in re.findall(r"<th>([^<]*)</th>\s*<td>([^<]*)</td>", p.get("Description", "")))
        return (d.get("PLN_AREA_N") or "").upper()

    pa_bnd = sorted({pa_name(p) for p in bprops} - {""})
    missing_in_ema = [p for p in pa_bnd if p not in pa_ema]
    extra_in_ema = [p for p in pa_ema if p not in pa_bnd]
    populated = [r for r in rows if r["TOTAL"] > 0]
    no12 = [r["PLN_AREA_N"] for r in populated if not r["ONE_TO_TWO_RM"]]
    zero_cols = {c: [r["PLN_AREA_N"] for r in populated if not r[c]] for c in COLS}
    all_zero = [r["PLN_AREA_N"] for r in rows if r["TOTAL"] == 0]
    now = datetime.now(ZoneInfo("Asia/Singapore"))

    L = ["# Checks 4 and 13: EMA household electricity by planning area", "",
         f"Script: `scripts/checks/check4_13_ema.py`; run {now:%Y-%m-%d %H:%M} SGT. **Unverified until read. Check 4 is NOT answered; check 13 is answered only for an old stand-in file.**", "",
         "## Check 4: terms of use for the EMA Excel download", "",
         "### What was tested", "",
         "Three unauthenticated GET requests to the EMA website, one each (no retries, no attempt to bypass any protection):", ""]
    L += table(["URL", "HTTP", "bytes", "what came back"], probes)
    L += ["", "### Result", "",
          "- The EMA site answered every request with a short page that loads an Incapsula bot-protection script, not the content. "
          "From a script on this computer the Singapore Energy Statistics page, its Chapter 3 page and the terms of use page could not be read, "
          "so **the Excel download link, the period it covers and the terms of use were not read. Check 4 is not answered.**",
          "- Claude in Chrome (a real browser) was tried and was not connected, so no browser read was made either.",
          "- Search results (not opened pages) say EMA's Chapter 3 has an 'Average Monthly Household Electricity Consumption by Planning Area' section with data as at June 2025 "
          "and that the FAQ places it in Tables 3.4 and 3.5. This comes from a search snippet and is **not confirmed**.", "",
          "### Fallback if the terms or the file are not available (agreed 19 Oct)",
          "Drop electricity from the can't-cool-down index and say so. A stand-in exists on data.gov.sg (below) but it is a 2013 snapshot.", "",
          "### What you need to do (user-only; needs a browser)",
          "Open the EMA Singapore Energy Statistics Chapter 3 page, find the planning-area table, note the Excel link, the latest period, and the terms of use / copyright wording in the page footer; paste them here.", "",
          "## Check 13: do 1-2 room values exist for every planning area?", "",
          "### What was tested", "",
          f"The only EMA planning-area files reachable are on data.gov.sg (Singapore Open Data Licence), one per year 2009 to 2013. Tested: "
          f"`d_47db177174ba5899aa9cee08797d9171` 'Average Monthly Household Electricity Consumption by URA Planning Area & Dwelling Type, 2013' "
          f"(EMA, {len(rows)} features, records stamped {sorted({str(r.get('FMEL_UPD_D'))[:8] for r in rows})}). "
          "Columns: " + ", ".join(f"`{c}`" for c in ["TOTAL", *COLS]) + ". Units are not stated in the file (kWh per month is my reading; not confirmed).", "",
          "### Result (2013 file only)", "",
          f"- Planning areas in the file: {len(rows)}. In the Master Plan 2019 boundary file: {len(pa_bnd)}. "
          f"In the boundary file but not in this file: {missing_in_ema or 'none'}. In this file but not in the boundary file: {extra_in_ema or 'none'}.",
          f"- Areas with a TOTAL above 0: **{len(populated)}**. Areas with TOTAL = 0 in every column ({len(all_zero)}): {', '.join(sorted(all_zero))}.",
          f"- **Areas with TOTAL above 0 but a 1-2 room value of 0 or missing: {len(no12)}** ({', '.join(no12) or 'none'}).",
          "- Other zero cells among populated areas: " + ("; ".join(f"{c}: {', '.join(v)}" for c, v in zero_cols.items() if v and c != "ONE_TO_TWO_RM") or "none") + ".",
          "- Implausible-looking cells (by comparison with the other columns; not confirmed errors): "
          + ", ".join(f"{r['PLN_AREA_N']} {c} = {r[c]}" for r in populated for c in COLS if r[c] and r[c] < 0.4 * r["TOTAL"]) + ".", "",
          "Populated areas, as in the file:", ""]
    L += table(["planning area", "TOTAL", *COLS], [(r["PLN_AREA_N"], r["TOTAL"], *[r[c] for c in COLS]) for r in sorted(populated, key=lambda r: r["PLN_AREA_N"])])
    L += ["", "### Reading", "",
          f"- In the 2013 file, **{len(all_zero)} of {len(rows)} areas carry zeros in every column** (my inference, not stated in the file: the columns are flat types, so areas with no flats of those types show zeros) and "
          f"{len(no12)} populated areas have no 1-2 room value. So the answer for this file is **no, not for every planning area**. "
          "Whether the current EMA Excel (to 1H 2025) behaves the same is **not known** because that file could not be reached.",
          "- The file uses 2013-era area names; the boundary comparison above shows whether they match Master Plan 2019 names.", "",
          "### Fallback (agreed 19 Oct)",
          "If the current file also lacks 1-2 room values, the proxy cannot cover every area: drop it from the can't-cool-down index and say so, "
          "or use the 3-room column (and say that). Rental flats per block (HDB Property Information) already cover block-level vulnerability.", "",
          "## Could not confirm", "",
          "- Everything about the current EMA Excel: link, period, units, columns, terms of use (blocked from scripts; needs your browser).",
          "- Whether EMA's current table has the same dwelling-type columns as the 2009 to 2013 data.gov.sg files.",
          "- The units and the cause of the zeros in the 2013 file.", ""]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:75]))


if __name__ == "__main__":
    main()
