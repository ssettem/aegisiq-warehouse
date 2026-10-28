# Data mapping: source field → warehouse column

Where every warehouse column comes from, and what the ETL (`etl/load_warehouse.py`) does to it on the way.
Source files are in `data/raw/` (synthetic). "Per site" files exist once for each of AUS, CHI, SEA, ATL and are stacked together.

## Dimensions

| Warehouse column | Source file → field | Rule |
|---|---|---|
| Dim_Site.* | fixed list in the ETL (`SITES`) | The official 4 sites. All messy spellings map to these. |
| Dim_Date.* | generated for 2025-01-06 … 2025-06-29 | `date_key` = date as YYYYMMDD; `week_start` = that week's Monday; `season` = calendar quarter |
| Dim_Player.player_id | players.csv → player_id | copied |
| Dim_Player.skill_bracket | players.csv → starting_mmr | MMR → Dota 2 medal (Herald … Immortal, approximate cut-offs) |
| Dim_Player.starting_mmr, region, signup_date, cancel_date | players.csv → same names | copied; blank cancel_date → NULL (still active) |
| Dim_Coach.coach_id, coach_name, specialty_role, experience_level | coaches.csv → same names | copied |
| Dim_Hero.* | heroes.csv | copied |
| Dim_Plan.* | plans.csv | copied; blank sessions_included → NULL (pay per session) |
| every `*_key` | — | surrogate key 1, 2, 3 … assigned by the ETL |

## Facts

| Warehouse column | Source file → field | Rule |
|---|---|---|
| **Fact_Coaching_Session** | per site: sessions.csv | duplicates on `session_id` removed (keep first) |
| session_id | session_id | copied |
| date_key | session_date | YYYY-MM-DD → YYYYMMDD |
| player_key / coach_key | player_id / coach_id | looked up in Dim_Player / Dim_Coach |
| site_key | site | messy name → official code → Dim_Site |
| plan_key | players.csv → plan_code (via player_id) | the player's plan |
| duration_min, session_fee | same names | copied |
| player_rating | player_rating | blank → NULL (not filled in) |
| **Fact_Match_Performance** | per site: matches.csv | |
| match_id, is_win, mmr_change, kills, deaths, assists | same names | copied |
| date_key | match_date | YYYYMMDD |
| player_key / hero_key | player_id / hero_id | dimension lookup |
| **Fact_Revenue** | per site: payments.csv | |
| payment_id, session_id, gross_amount, discount | same names | copied; blank session_id → NULL (subscription payment) |
| net_amount | gross_amount − discount | calculated |
| date_key | payment_date | YYYYMMDD |
| player_key / plan_key | player_id / plan_code | dimension lookup |
| site_key | players.csv → home_site (via player_id) | revenue is credited to the player's home site |
| **Fact_Coach_Shift** | per site: shifts.csv | |
| coach_key, date_key | coach_id, shift_date | dimension lookup |
| site_key | site | messy name → official code |
| hours_scheduled | hours_scheduled | copied |
| hours_booked | Fact_Coaching_Session | sum of that coach's session minutes that day ÷ 60 (0 if none) |
