"""Plant -> owner mapping, driven by config/plant_owner.csv (edit the CSV, not this code).

Order of resolution:
  1. exact name match (case and whitespace insensitive)
  2. regex match
  3. fallback by sector: state-sector plants are owned by their state's generation company,
     everything else is classed as "Other". Those rows keep confidence "none", which is how the
     refresh report still lists the plants nobody has assigned yet.
"""
import csv
import re
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "config" / "plant_owner.csv"


def _norm(s: str) -> str:
    return " ".join(str(s).upper().split())


class OwnerMap:
    def __init__(self, csv_path=DEFAULT_CSV):
        self.exact, self.regex = {}, []
        with open(csv_path, newline="") as f:
            for r in csv.DictReader(f):
                if r["match"] == "exact":
                    self.exact[_norm(r["pattern"])] = r
                else:
                    self.regex.append((re.compile(r["pattern"], re.I), r))

    def lookup(self, plant: str, sector: str = None, state: str = None):
        """Return (owner, confidence, note)."""
        r = self.exact.get(_norm(plant))
        if r is None:
            r = next((rr for rx, rr in self.regex if rx.search(plant)), None)
        if r:
            return r["owner"], r["confidence"], r["note"]
        if sector == "STATE SECTOR":
            return f"STATE: {state.title()}" if state else "STATE", "medium", "state-sector fallback"
        if sector == "IMPORT":
            return "IMPORT: Bhutan", "high", ""
        return "Other", "none", ""
