"""SQLite storage. Upserts, so re-running a day (late or revised file) overwrites it cleanly."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
  date TEXT NOT NULL, plant TEXT NOT NULL,
  region TEXT, state TEXT, sector TEXT, fuel TEXT,
  owner TEXT, owner_confidence TEXT,
  mw REAL, prog_mu REAL, actual_mu REAL, apr_prog_mu REAL, apr_actual_mu REAL,
  plf_pct REAL, coal_days REAL, outage_mw REAL,
  PRIMARY KEY (date, plant)
);
CREATE TABLE IF NOT EXISTS units (
  date TEXT NOT NULL, plant TEXT NOT NULL, unit TEXT NOT NULL,
  mw REAL, prog_mu REAL, actual_mu REAL, apr_prog_mu REAL, apr_actual_mu REAL,
  outage_mw REAL, outage_date TEXT, expected_return TEXT, remarks TEXT,
  PRIMARY KEY (date, plant, unit)
);
CREATE INDEX IF NOT EXISTS ix_stations_owner ON stations(owner, date);
"""


def connect(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def plf(actual_mu, mw):
    """Plant load factor for one day: MU*1000 / (MW * 24h). None when capacity is zero."""
    if actual_mu is None or not mw:
        return None
    return round(actual_mu * 1000 / (mw * 24) * 100, 2)


def save_day(db, parsed, owners):
    """Replace everything stored for parsed.date. Returns number of stations written."""
    day = parsed.date.isoformat()
    with db:
        db.execute("DELETE FROM stations WHERE date=?", (day,))
        db.execute("DELETE FROM units WHERE date=?", (day,))
        for s in parsed.stations:
            owner, conf, _ = owners.lookup(s["plant"], s["sector"], s["state"])
            db.execute(
                "INSERT INTO stations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (day, s["plant"], s["region"], s["state"], s["sector"], s["fuel"], owner, conf,
                 s["mw"], s["prog_mu"], s["actual_mu"], s["apr_prog_mu"], s["apr_actual_mu"],
                 plf(s["actual_mu"], s["mw"]), s["coal_days"], s["outage_mw"]))
        for u in parsed.units:
            db.execute(
                "INSERT OR REPLACE INTO units VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (day, u["plant"], u["unit"], u["mw"], u["prog_mu"], u["actual_mu"], u["apr_prog_mu"],
                 u["apr_actual_mu"], u["outage_mw"], u["outage_date"], u["expected_return"], u["remarks"]))
    return len(parsed.stations)
