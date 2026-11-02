"""Parse DGR sub-report 2: region / state / sector / type / station / unit generation.

Layout (verified on 2019, 2024 and 2026 files):
  - single-cell rows set context: a region (NORTHERN, ...) or a state (DELHI, ...)
  - 'SECTOR:' rows carry the sector name in column 4 (e.g. PVT SECTOR), 'TYPE:' rows the fuel type
  - a station row has a name in column 0 and numbers in the data columns
  - 'Unit' rows that follow belong to that station
  - '* TOTAL' rows are subtotals; they are kept separately for reconciliation
Column positions are found from the header text, not hard-coded, and a ParseError is raised
if the header is not what we expect, so a layout change fails loudly instead of loading junk.
"""
import datetime as dt
import re
from dataclasses import dataclass, field

import xlrd

REGIONS = {"NORTHERN", "WESTERN", "SOUTHERN", "EASTERN", "NORTH EASTERN", "NORTH-EASTERN", "NORTHEASTERN"}


class ParseError(Exception):
    pass


@dataclass
class Dgr2:
    date: dt.date
    stations: list = field(default_factory=list)
    units: list = field(default_factory=list)
    totals: list = field(default_factory=list)


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _find_columns(rows):
    """Locate the data columns from the two header rows."""
    hdr = None
    for i, r in enumerate(rows[:12]):
        if str(r[0]).strip().upper().startswith("POWER STATION"):
            hdr = i
            break
    if hdr is None:
        raise ParseError("header row 'POWER STATION' not found")
    cols = {}
    for j, c in enumerate(rows[hdr]):
        t = " ".join(str(c).upper().split())
        if t.startswith("MONITORED"):
            cols["cap"] = j
        elif t.startswith("GENERATION"):
            cols["prog"] = j
        elif t.startswith("COAL STOCK"):
            cols["coal"] = j
        elif t.startswith("CAP. UNDER") or t.startswith("CAP UNDER"):
            cols["outage_mw"] = j
        elif t.startswith("OUTAGE DATE"):
            cols["outage_date"] = j
        elif t.startswith("EXPECTED"):
            cols["expected"] = j
        elif t.startswith("REMARKS"):
            cols["remarks"] = j
    missing = {"cap", "prog", "coal", "outage_mw"} - cols.keys()
    if missing:
        raise ParseError(f"header columns not found: {sorted(missing)}")
    cols["actual"] = cols["prog"] + 1
    cols["apr_prog"] = cols["prog"] + 2
    cols["apr_actual"] = cols["prog"] + 3
    # sanity: the sub-header must say TODAY'S PROGRAM / ACTUAL right where we think they are
    sub = " ".join(str(c).upper() for c in rows[hdr + 1])
    if "PROGRAM" not in sub or "ACTUAL" not in sub:
        raise ParseError("sub-header (TODAY'S PROGRAM / ACTUAL) not found under header")
    return hdr, cols


def parse_dgr2(path) -> Dgr2:
    book = xlrd.open_workbook(str(path))
    sh = book.sheet_by_index(0)
    rows = [sh.row_values(r) for r in range(sh.nrows)]

    # report date, from the title line: '... GENERATION REPORT FOR     30/10/2026'
    m = None
    for r in rows[:5]:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", " ".join(str(c) for c in r))
        if m:
            break
    if not m:
        raise ParseError("report date not found in title")
    date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    hdr, c = _find_columns(rows)
    out = Dgr2(date=date)
    region = state = sector = fuel = None
    plant = None

    for r in rows[hdr + 2:]:
        name = str(r[0]).strip()
        if not name or name.startswith(("Remarks", "Report Version", "CENTRAL ELECTRICITY")):
            continue
        cap = _num(r[c["cap"]])
        has_nums = any(_num(x) is not None for x in r[c["cap"]:c["apr_actual"] + 1])
        up = " ".join(name.upper().split())

        if up in ("SECTOR:", "TYPE:"):
            # the label sits in column 2, 3 or 4 depending on the report's vintage: take the first text cell before the data columns
            label = next((str(x).strip() for x in r[1:c["cap"]] if isinstance(x, str) and x.strip()), "")
            if up == "SECTOR:":
                sector, fuel = label, None
            else:
                fuel = label
            continue
        if up.endswith("TOTAL"):
            out.totals.append(dict(date=date, label=up, region=region, state=state, mw=cap,
                                   actual_mu=_num(r[c["actual"]]), prog_mu=_num(r[c["prog"]])))
            continue
        if not has_nums:  # heading row
            if up in REGIONS:
                region, state = up, None
            else:
                state = name
            sector = fuel = plant = None
            continue
        if up == "UNIT":
            if plant is None:
                raise ParseError(f"unit row with no station above it: {r[:3]}")
            od = r[c["outage_date"]] if "outage_date" in c else ""
            out.units.append(dict(
                date=date, plant=plant, unit=str(r[2]).strip(), mw=cap,
                prog_mu=_num(r[c["prog"]]), actual_mu=_num(r[c["actual"]]),
                apr_prog_mu=_num(r[c["apr_prog"]]), apr_actual_mu=_num(r[c["apr_actual"]]),
                outage_mw=_num(r[c["outage_mw"]]),
                outage_date=(xlrd.xldate_as_datetime(od, book.datemode).isoformat(timespec="minutes")
                             if isinstance(od, float) else None),
                expected_return=str(r[c["expected"]]).strip() if "expected" in c else "",
                remarks=str(r[c["remarks"]]).strip() if "remarks" in c else "",
            ))
            continue
        # a station
        plant = name
        if state == "BHUTAN" and not sector:  # imports from Bhutan sit under their own heading
            sector, fuel = "IMPORT", "HYDRO"
        out.stations.append(dict(
            date=date, region=region, state=state, sector=sector, fuel=fuel, plant=name,
            mw=cap, prog_mu=_num(r[c["prog"]]), actual_mu=_num(r[c["actual"]]),
            apr_prog_mu=_num(r[c["apr_prog"]]), apr_actual_mu=_num(r[c["apr_actual"]]),
            coal_days=_num(r[c["coal"]]), outage_mw=_num(r[c["outage_mw"]]),
        ))
    if not out.stations:
        raise ParseError("no stations parsed")
    return out


def reconcile(d: Dgr2, tol: float = 0.05):
    """Compare the sum of parsed stations with the file's own REGION TOTAL rows.

    Returns a list of (region, stations_sum, file_total, ok). Several REGION TOTAL rows for
    one region (North Eastern + Bhutan imports) are summed. Use this as a parse-health check.
    """
    got, want = {}, {}
    for s in d.stations:
        got[s["region"]] = got.get(s["region"], 0.0) + (s["actual_mu"] or 0.0)
    for t in d.totals:
        if t["label"] == "REGION TOTAL":
            want[t["region"]] = want.get(t["region"], 0.0) + (t["actual_mu"] or 0.0)
    return [(r, round(got.get(r, 0.0), 2), round(want[r], 2), abs(got.get(r, 0.0) - want[r]) <= tol)
            for r in sorted(want)]
