"""
ETL: load the AegisIQ source CSVs into the star-schema warehouse (aegisiq.db).

    Extract   read the shared master lists and every site's exports
    Transform clean them (site names, duplicates, blanks), give every
              dimension row a surrogate key, swap the business IDs in the
              facts for those keys, compute hours booked per coach shift
    Load      rebuild aegisiq.db from sql/01_create_tables.sql and insert
              dimensions first, then facts (so foreign keys always match)

Then it prints row counts and a data-quality check: every pay-per-session
session should have exactly one payment, week by week.

Uses only the Python standard library and pandas.
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "aegisiq.db"
DDL = ROOT / "sql" / "01_create_tables.sql"

# The single, official list of sites. Every spelling found in the source
# files must map to one of these codes, or the ETL stops.
SITES = [
    # code, name, region
    ("AUS", "Austin", "US Central"),
    ("CHI", "Chicago", "US Central"),
    ("SEA", "Seattle", "US West"),
    ("ATL", "Atlanta", "US East"),
]
SITE_ALIASES = {
    "austin": "AUS", "aus": "AUS", "austin tx": "AUS",
    "chicago": "CHI", "chi": "CHI",
    "seattle": "SEA", "sea": "SEA", "seattle wa": "SEA",
    "atlanta": "ATL", "atl": "ATL", "atlanta ga": "ATL",
}

# Reporting period covered by Dim_Date.
PERIOD_START, PERIOD_END = "2025-01-06", "2025-06-29"

# Approximate Dota 2 medal boundaries by MMR.
BRACKETS = [(770, "Herald"), (1540, "Guardian"), (2310, "Crusader"),
            (3080, "Archon"), (3850, "Legend"), (4620, "Ancient"),
            (5420, "Divine"), (99999, "Immortal")]


# --- Extract ----------------------------------------------------------------

def read_site_exports(file_name):
    """Stack one export type (e.g. sessions.csv) from all four site folders."""
    frames = [pd.read_csv(RAW / code / file_name, dtype=str) for code, _, _ in SITES]
    return pd.concat(frames, ignore_index=True)


players = pd.read_csv(RAW / "players.csv", dtype=str)
coaches = pd.read_csv(RAW / "coaches.csv", dtype=str)
heroes = pd.read_csv(RAW / "heroes.csv", dtype=str)
plans = pd.read_csv(RAW / "plans.csv", dtype=str)
sessions = read_site_exports("sessions.csv")
payments = read_site_exports("payments.csv")
shifts = read_site_exports("shifts.csv")
matches = read_site_exports("matches.csv")


# --- Transform: cleaning ------------------------------------------------------

def clean_site(column):
    """Map every spelling of a site name to its official code."""
    codes = column.str.strip().str.lower().map(SITE_ALIASES)
    unknown = column[codes.isna()].unique()
    if len(unknown):
        raise ValueError(f"Unrecognised site names: {list(unknown)}")
    return codes


site_names = {code: name for code, name, _ in SITES}
messy_site_rows = 0
for df, col in [(players, "home_site"), (coaches, "home_site"),
                (sessions, "site"), (shifts, "site")]:
    messy_site_rows += int((~df[col].isin(site_names.values())).sum())
    df[col] = clean_site(df[col])

rows_before = len(sessions)
sessions = sessions.drop_duplicates(subset="session_id", keep="first")
duplicate_sessions = rows_before - len(sessions)

# Blank ratings stay blank (NULL): we do not invent a score the player never gave.
sessions["player_rating"] = pd.to_numeric(sessions["player_rating"], errors="coerce")
missing_ratings = int(sessions["player_rating"].isna().sum())


# --- Transform: dimensions (surrogate keys 1, 2, 3, ...) ---------------------

def add_key(df, key_name):
    df = df.reset_index(drop=True)
    df.insert(0, key_name, df.index + 1)
    return df


dim_site = add_key(pd.DataFrame(SITES, columns=["site_code", "site_name", "region"]), "site_key")

days = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
dim_date = pd.DataFrame({
    "date_key": days.strftime("%Y%m%d").astype(int),
    "full_date": days.strftime("%Y-%m-%d"),
    "day_name": days.day_name(),
    "week_start": (days - pd.to_timedelta(days.weekday, unit="D")).strftime("%Y-%m-%d"),
    "month": days.strftime("%Y-%m"),
    "season": days.year.astype(str) + "-Q" + days.quarter.astype(str),
})

players["starting_mmr"] = players["starting_mmr"].astype(int)
players["skill_bracket"] = players["starting_mmr"].map(
    lambda mmr: next(name for limit, name in BRACKETS if mmr < limit))
dim_player = add_key(players[["player_id", "skill_bracket", "starting_mmr", "region",
                              "signup_date", "cancel_date"]], "player_key")

dim_coach = add_key(coaches[["coach_id", "coach_name", "specialty_role",
                             "experience_level"]], "coach_key")
dim_hero = add_key(heroes, "hero_key")
dim_plan = add_key(plans, "plan_key")
dim_plan["price"] = dim_plan["price"].astype(float)
dim_plan["sessions_included"] = pd.to_numeric(dim_plan["sessions_included"])

# Lookups from business ID -> surrogate key, used to build the facts.
site_key = dict(zip(dim_site.site_code, dim_site.site_key))
player_key = dict(zip(dim_player.player_id, dim_player.player_key))
coach_key = dict(zip(dim_coach.coach_id, dim_coach.coach_key))
hero_key = dict(zip(dim_hero.hero_id, dim_hero.hero_key))
plan_key = dict(zip(dim_plan.plan_code, dim_plan.plan_key))
player_plan = dict(zip(players.player_id, players.plan_code))
player_site = dict(zip(players.player_id, players.home_site))


def to_date_key(column):
    """'2025-01-06' -> 20250106"""
    return column.str.replace("-", "").astype(int)


# --- Transform: facts ---------------------------------------------------------

fact_session = pd.DataFrame({
    "session_id": sessions.session_id,
    "date_key": to_date_key(sessions.session_date),
    "player_key": sessions.player_id.map(player_key),
    "coach_key": sessions.coach_id.map(coach_key),
    "site_key": sessions.site.map(site_key),
    "plan_key": sessions.player_id.map(player_plan).map(plan_key),
    "duration_min": sessions.duration_min.astype(int),
    "session_fee": sessions.session_fee.astype(float),
    "player_rating": sessions.player_rating,
})

fact_match = pd.DataFrame({
    "match_id": matches.match_id,
    "date_key": to_date_key(matches.match_date),
    "player_key": matches.player_id.map(player_key),
    "hero_key": matches.hero_id.map(hero_key),
    "is_win": matches.is_win.astype(int),
    "mmr_change": matches.mmr_change.astype(int),
    "kills": matches.kills.astype(int),
    "deaths": matches.deaths.astype(int),
    "assists": matches.assists.astype(int),
})

gross = payments.gross_amount.astype(float)
discount = payments.discount.astype(float)
fact_revenue = pd.DataFrame({
    "payment_id": payments.payment_id,
    "date_key": to_date_key(payments.payment_date),
    "player_key": payments.player_id.map(player_key),
    "site_key": payments.player_id.map(player_site).map(site_key),
    "plan_key": payments.plan_code.map(plan_key),
    "session_id": payments.session_id,           # blank (NaN -> NULL) for subscriptions
    "gross_amount": gross,
    "discount": discount,
    "net_amount": gross - discount,
})

# Hours booked = total length of the coach's (de-duplicated) sessions that day.
booked = (fact_session.groupby(["coach_key", "date_key"])["duration_min"].sum() / 60
          ).rename("hours_booked").reset_index()
fact_shift = pd.DataFrame({
    "coach_key": shifts.coach_id.map(coach_key),
    "date_key": to_date_key(shifts.shift_date),
    "site_key": shifts.site.map(site_key),
    "hours_scheduled": shifts.hours_scheduled.astype(float),
})
fact_shift = fact_shift.merge(booked, on=["coach_key", "date_key"], how="left")
fact_shift["hours_booked"] = fact_shift["hours_booked"].fillna(0.0)

# Every fact row must find its dimension rows; a missing key means bad source data.
for name, df in [("sessions", fact_session), ("matches", fact_match),
                 ("payments", fact_revenue), ("shifts", fact_shift)]:
    key_cols = [c for c in df.columns if c.endswith("_key")]
    if df[key_cols].isna().any().any():
        raise ValueError(f"{name}: some rows reference an unknown player/coach/site/etc.")


# --- Load ---------------------------------------------------------------------

DB.unlink(missing_ok=True)                      # rebuild from scratch every run
con = sqlite3.connect(DB)
con.executescript(DDL.read_text())              # also turns foreign keys on

tables = [
    ("Dim_Site", dim_site), ("Dim_Date", dim_date), ("Dim_Player", dim_player),
    ("Dim_Coach", dim_coach), ("Dim_Hero", dim_hero), ("Dim_Plan", dim_plan),
    ("Fact_Coaching_Session", fact_session), ("Fact_Match_Performance", fact_match),
    ("Fact_Revenue", fact_revenue), ("Fact_Coach_Shift", fact_shift),
]
for table, df in tables:
    df.to_sql(table, con, if_exists="append", index=False)
con.commit()


# --- Report -------------------------------------------------------------------

print("Cleaning")
print(f"  site names standardised : {messy_site_rows} rows")
print(f"  duplicate sessions removed: {duplicate_sessions} rows")
print(f"  ratings left blank (NULL) : {missing_ratings} sessions")

print("\nRow counts in aegisiq.db")
for table, _ in tables:
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:<24}{count:>8,}")

broken = con.execute("PRAGMA foreign_key_check").fetchall()
print(f"\nForeign key violations: {len(broken)}")

# Data-quality check: each week, pay-per-session sessions vs their payments.
dq = pd.read_sql_query("""
    WITH s AS (
        SELECT d.week_start, COUNT(*) AS pps_sessions
        FROM Fact_Coaching_Session f
        JOIN Dim_Date d ON d.date_key = f.date_key
        JOIN Dim_Plan p ON p.plan_key = f.plan_key
        WHERE p.plan_code = 'PPS'
        GROUP BY d.week_start
    ), r AS (
        SELECT d.week_start, COUNT(*) AS session_payments
        FROM Fact_Revenue f
        JOIN Dim_Date d ON d.date_key = f.date_key
        WHERE f.session_id IS NOT NULL
        GROUP BY d.week_start
    )
    SELECT s.week_start, s.pps_sessions, COALESCE(r.session_payments, 0) AS session_payments,
           s.pps_sessions - COALESCE(r.session_payments, 0) AS unpaid_sessions
    FROM s LEFT JOIN r ON r.week_start = s.week_start
    ORDER BY s.week_start
""", con)
con.close()

flagged = dq[dq.unpaid_sessions != 0]
print("\nData-quality check: weekly pay-per-session sessions vs payments")
print(f"  weeks checked: {len(dq)}, weeks that do not match: {len(flagged)}, "
      f"sessions with no payment: {int(dq.unpaid_sessions.sum())} "
      f"of {int(dq.pps_sessions.sum())}")
if len(flagged):
    print(flagged.to_string(index=False))

(ROOT / "results").mkdir(exist_ok=True)
dq.to_csv(ROOT / "results" / "dq_weekly_sessions_vs_payments.csv", index=False)
print(f"\nWarehouse built: {DB}")
