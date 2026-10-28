-- =====================================================================
-- AegisIQ Reporting Data Warehouse: table definitions (SQLite)
--
-- Star schema: 6 dimension tables (descriptions) and 4 fact tables
-- (events and numbers). Every fact row points to its dimensions with
-- foreign keys, so all four sites share one definition of "site",
-- "date", "player", "coach", "hero" and "plan".
--
-- Naming: *_key = surrogate key (a plain integer the warehouse assigns)
--         *_id  = business/natural ID copied from the source system
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- DIMENSIONS
-- ---------------------------------------------------------------------

-- The four coaching sites. One row per site.
CREATE TABLE Dim_Site (
    site_key    INTEGER PRIMARY KEY,
    site_code   TEXT NOT NULL UNIQUE,   -- e.g. 'AUS'
    site_name   TEXT NOT NULL,          -- e.g. 'Austin'
    region      TEXT NOT NULL           -- e.g. 'US Central'
);

-- One row per calendar day in the reporting period.
-- date_key is the date written as a number, e.g. 20250106.
CREATE TABLE Dim_Date (
    date_key    INTEGER PRIMARY KEY,
    full_date   TEXT NOT NULL UNIQUE,   -- 'YYYY-MM-DD'
    day_name    TEXT NOT NULL,          -- 'Monday'
    week_start  TEXT NOT NULL,          -- Monday of that week
    month       TEXT NOT NULL,          -- 'YYYY-MM'
    season      TEXT NOT NULL           -- calendar quarter, e.g. '2025-Q1'
);

-- One row per player (customer).
CREATE TABLE Dim_Player (
    player_key      INTEGER PRIMARY KEY,
    player_id       TEXT NOT NULL UNIQUE,   -- e.g. 'P0001'
    skill_bracket   TEXT NOT NULL,          -- Dota 2 medal from starting MMR
    starting_mmr    INTEGER NOT NULL,
    region          TEXT NOT NULL,
    signup_date     TEXT NOT NULL,
    cancel_date     TEXT                    -- NULL = still active
);

-- One row per coach.
CREATE TABLE Dim_Coach (
    coach_key           INTEGER PRIMARY KEY,
    coach_id            TEXT NOT NULL UNIQUE,   -- e.g. 'C001'
    coach_name          TEXT NOT NULL,
    specialty_role      TEXT NOT NULL,          -- Carry, Mid, Offlane, ...
    experience_level    TEXT NOT NULL           -- Junior, Mid, Senior
);

-- One row per Dota 2 hero tracked.
CREATE TABLE Dim_Hero (
    hero_key    INTEGER PRIMARY KEY,
    hero_id     TEXT NOT NULL UNIQUE,
    hero_name   TEXT NOT NULL,
    hero_role   TEXT NOT NULL
);

-- One row per product the company sells.
CREATE TABLE Dim_Plan (
    plan_key            INTEGER PRIMARY KEY,
    plan_code           TEXT NOT NULL UNIQUE,   -- 'PPS', 'BASIC', 'PRO'
    plan_name           TEXT NOT NULL,
    plan_type           TEXT NOT NULL,          -- 'Pay per session' or 'Subscription'
    price               REAL NOT NULL,          -- per session or per month
    sessions_included   INTEGER                 -- per month; NULL for pay per session
);

-- ---------------------------------------------------------------------
-- FACTS
-- ---------------------------------------------------------------------

-- Grain: ONE coaching session.
CREATE TABLE Fact_Coaching_Session (
    session_id      TEXT PRIMARY KEY,       -- from the booking system
    date_key        INTEGER NOT NULL REFERENCES Dim_Date(date_key),
    player_key      INTEGER NOT NULL REFERENCES Dim_Player(player_key),
    coach_key       INTEGER NOT NULL REFERENCES Dim_Coach(coach_key),
    site_key        INTEGER NOT NULL REFERENCES Dim_Site(site_key),
    plan_key        INTEGER NOT NULL REFERENCES Dim_Plan(plan_key),
    duration_min    INTEGER NOT NULL,
    session_fee     REAL NOT NULL,          -- 0 when covered by a subscription
    player_rating   INTEGER                 -- 1-5, NULL when the player skipped the survey
);

-- Grain: ONE player in ONE match.
CREATE TABLE Fact_Match_Performance (
    match_id        TEXT PRIMARY KEY,
    date_key        INTEGER NOT NULL REFERENCES Dim_Date(date_key),
    player_key      INTEGER NOT NULL REFERENCES Dim_Player(player_key),
    hero_key        INTEGER NOT NULL REFERENCES Dim_Hero(hero_key),
    is_win          INTEGER NOT NULL CHECK (is_win IN (0, 1)),
    mmr_change      INTEGER NOT NULL,
    kills           INTEGER NOT NULL,
    deaths          INTEGER NOT NULL,
    assists         INTEGER NOT NULL
);

-- Grain: ONE payment.
CREATE TABLE Fact_Revenue (
    payment_id      TEXT PRIMARY KEY,
    date_key        INTEGER NOT NULL REFERENCES Dim_Date(date_key),
    player_key      INTEGER NOT NULL REFERENCES Dim_Player(player_key),
    site_key        INTEGER NOT NULL REFERENCES Dim_Site(site_key),
    plan_key        INTEGER NOT NULL REFERENCES Dim_Plan(plan_key),
    session_id      TEXT,                   -- set only for pay-per-session payments
    gross_amount    REAL NOT NULL,
    discount        REAL NOT NULL,
    net_amount      REAL NOT NULL           -- gross_amount - discount
);

-- Grain: ONE coach on ONE day.
CREATE TABLE Fact_Coach_Shift (
    coach_key       INTEGER NOT NULL REFERENCES Dim_Coach(coach_key),
    date_key        INTEGER NOT NULL REFERENCES Dim_Date(date_key),
    site_key        INTEGER NOT NULL REFERENCES Dim_Site(site_key),
    hours_scheduled REAL NOT NULL,
    hours_booked    REAL NOT NULL,          -- sum of that coach's sessions that day
    PRIMARY KEY (coach_key, date_key)
);
