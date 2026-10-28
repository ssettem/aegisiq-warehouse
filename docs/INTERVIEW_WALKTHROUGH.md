# Interview walkthrough: AegisIQ Reporting Data Warehouse

Plain-English notes for explaining every part of this project. Say it in your own words; the numbers are from the current run (seed 42).

---

## 0. Explaining the game to a non-gamer (say this first if needed)

> "Dota 2 is an online team video game, five against five. The game gives every player a skill score called MMR, matchmaking rating. Win a match and it goes up about 25 points, lose and it goes down. So for a coaching company, MMR is the customer's result: if coaching works, the customer's rating should climb."

Other terms: a **hero** is the character a player picks for a match; **utilization** is hours coaches actually taught ÷ hours they were scheduled.

## 1. The 30-second version

> "AegisIQ was a course case: a Dota 2 coaching company with four sites whose numbers never matched. I started from the questions leaders needed answered, about player performance, coaching sessions, revenue and staffing. I drew an ER diagram of the source data, reshaped it into a star schema with four fact tables and six shared dimensions, and wrote a data mapping. Then I rebuilt it as a working project: Python generates realistic synthetic exports for each site, including messy rows; a Python ETL cleans them and loads a SQLite warehouse; four SQL queries answer the business questions; and a simple dashboard shows the results. The data is synthetic, and I say so in the repo."

**Be upfront:** the original course files are gone. This repo is my rebuild of the same design, with generated data.

---

## 2. The design, step by step

**Requirements first.** Four questions: Does more coaching improve a player's skill rating (MMR)? Which site earns most per coaching hour? Are coaches overbooked or idle? Which plans bring the most revenue and the longest-staying players? Every table exists to answer one of these.

**ER diagram (`docs/er_diagram.png`).** This shows the business as the source systems see it: sites, players, coaches, plans, heroes, sessions, payments, shifts and match results. Each box has a **primary key** (the unique ID of a row, like `session_id`) and **foreign keys** (a column that points to another table, like `coach_id` on a session). The crow's-foot lines show "one to many": one coach runs many sessions.

**Star schema (`docs/star_schema.png`).** The ER diagram is good for recording data, not for reporting. For reporting I reshaped it:
- **Fact tables** in the middle hold events and numbers you add up.
- **Dimension tables** around them hold descriptions you filter and group by (who, what, when, where).

**Data mapping (`docs/data_mapping.md`).** For every warehouse column: which source file and field it comes from, and the rule applied (copied, looked up, calculated, cleaned).

---

## 3. Key terms you will be asked about

**Grain.** What one row of a fact table means. Decide it first, because every number on the row must be true at that level.

| Fact table | Grain | Why that grain |
|---|---|---|
| Fact_Coaching_Session | one session | sessions are what coaches deliver and what pay-per-session players pay for |
| Fact_Match_Performance | one player in one match | MMR change belongs to one player's result in one game |
| Fact_Revenue | one payment | money arrives as payments; a subscription payment covers many sessions, so it can't sit on the session row |
| Fact_Coach_Shift | one coach on one day | staffing is planned per coach per day |

**Primary key / foreign key.** Primary key = the column(s) that uniquely identify a row (`payment_id`; for shifts it is two columns together, `coach_key + date_key`). Foreign key = a column that must match a primary key in another table (`Fact_Revenue.site_key` → `Dim_Site.site_key`). The database rejects a fact row pointing to a site that doesn't exist. The ETL runs a check and found 0 violations.

**Surrogate key vs business key.** Each dimension has a plain number key the warehouse assigns (`player_key` = 1, 2, 3…) and keeps the source ID too (`player_id` = 'P0001'). Facts join on the number key. It is small and fast, and it keeps working if a source system changes its ID format.

**Date key.** `20250106` instead of a date. Easy to read and to join; `Dim_Date` adds week start, month and season (quarter) so queries can group by week without date maths.

**Why a star schema and not one big table?** One big table would repeat the player's and coach's details on every row: bigger, slower, and inconsistent when a detail changes in one place but not another. The star stores each description once. And because all four facts share the same `Dim_Site` and `Dim_Date`, every site reports with the same definitions, which was the business problem.

**Why is site on the facts, not on Dim_Coach?** If a coach moves from Austin to Seattle, old shifts should still count for Austin. Putting `site_key` on each fact row records where the work actually happened.

---

## 4. File by file

**`etl/generate_sample_data.py`**: makes the synthetic data. 4 sites, 38 coaches, 1,140 players, 25 weeks. It writes shared lists (players, coaches, heroes, plans) and one export folder per site (sessions, payments, shifts, matches), like four sites each sending files. Fixed random seed 42, so it gives the same data every run. It plants realistic problems: misspelled site names, duplicate session rows, blank ratings and a few missing payments. It also deliberately makes recent coaching raise a player's win chance slightly. Say this openly: the Q1 pattern was built in, so the project shows the method, not a real discovery.

**`sql/01_create_tables.sql`**: creates the 10 tables with primary keys, foreign keys and one CHECK rule (`is_win` must be 0 or 1). Comments state each fact table's grain.

**`etl/load_warehouse.py`**: the ETL.
- *Extract:* reads the shared files and stacks the four sites' exports.
- *Transform / clean:*
  - site names: 767 rows with variants like `AUS`, `austin`, `Seattle WA` mapped to one code; an unknown spelling stops the load rather than guessing
  - duplicates: 142 repeated sessions removed by `session_id`
  - blanks: 441 missing ratings kept as NULL, not filled in, because inventing a score would distort averages
  - hours booked: calculated per coach per day from the cleaned sessions
  - net amount: gross minus discount
- *Transform / model:* builds the 6 dimensions with surrogate keys, then swaps IDs in the facts for keys.
- *Load:* recreates `aegisiq.db` from the DDL, loads dimensions first then facts (so foreign keys always find their match), prints row counts.
- *Data-quality check:* week by week, pay-per-session sessions vs payments that reference a session. Result: 41 of 2,897 sessions (1.4%) had no payment, in 19 of 25 weeks. This is the improvement I'd make over my original course design, which had no quality check.

**`sql/02_business_queries.sql`** + **`run_queries.py`**: four queries, results saved to `results/` and copied into the dashboard.

**`dashboard/index.html`**: one static page, four Chart.js charts, labelled synthetic. No server or paid tool needed.

---

## 5. What each query does and shows

**Q1: coaching vs skill rating (MMR).** Per player: sessions per active month and MMR change per active month (active month = a month with at least one match). Players grouped into bands. Result: under 2 sessions/month → −8.7 MMR/month; 6+ → +25.6 MMR/month; win rate 48.2% → 54.4%.
*If asked "does coaching cause it?":* "This shows a link, not cause. Players who book more may also play more or be more motivated. To show cause you'd compare similar players, or run a test. And in this data I built the effect into the generator."

**Q2: revenue per coaching hour by site.** Net revenue from Fact_Revenue ÷ hours from Fact_Coach_Shift, two ways. Per *booked* hour Austin is highest ($32.89). Per *scheduled* hour Seattle is highest ($25.59) because its coaches are rarely idle. Atlanta is lowest on both. Why two measures: booked = how well an hour of coaching is priced; scheduled = how well the site uses what it pays for.

**Q3: coach utilization by week.** Hours booked ÷ hours scheduled, per site per week. Seattle above 100% in 13 of 25 weeks (peak 132.9%), meaning coaches worked past their schedule. Atlanta and Chicago were around 60–65% from April. Recommendation: shift hours toward Seattle.

**Q4: revenue and retention by plan.** Revenue per plan from Fact_Revenue; retention = months from sign-up to cancel date (or to the end of the period if still active), from Dim_Player. Monthly Pro: 222 players, $187,770, $846 per player, 3.5 months, 76.6% still active. Pay Per Session: most players (496) but least revenue ($125,920) and only 48.2% still active.
*Caveat to mention:* active players' tenure is cut off at the end of the data, so retention is slightly understated.

---

## 6. Likely follow-up questions

- **"Why SQLite?"** Free, one file, no server. The same SQL runs on SQL Server or PostgreSQL with small changes.
- **"How would this run in production?"** Schedule the ETL nightly, load new rows instead of rebuilding, and send the quality check to finance automatically.
- **"What would you add next?"** A coach-level utilization view (who exactly is overbooked), slowly changing dimensions to track player plan changes over time, and an alert when the weekly unpaid-session count goes above a threshold.
- **"What was hardest?"** Choosing the grain of revenue. Subscription money doesn't belong to one session, so revenue needed its own fact table at payment level.
