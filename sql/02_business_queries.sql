-- =====================================================================
-- AegisIQ: the four business questions
-- Each query starts with a "-- name:" line; run_queries.py uses it to
-- name the output file in results/.
-- =====================================================================


-- name: q1_coaching_vs_mmr
-- Q1. Do players who get more coaching improve their MMR faster?
-- Per player: sessions per active month and MMR gained per active month
-- ("active month" = a month in which the player played at least one match).
-- Then group players into bands by how much coaching they get.
-- Note: this shows a link (correlation), not proof that coaching causes it.
WITH player_months AS (
    SELECT m.player_key,
           COUNT(DISTINCT d.month) AS active_months,
           SUM(m.mmr_change)       AS mmr_change,
           AVG(m.is_win)           AS win_rate
    FROM Fact_Match_Performance m
    JOIN Dim_Date d ON d.date_key = m.date_key
    GROUP BY m.player_key
),
player_sessions AS (
    SELECT player_key, COUNT(*) AS sessions
    FROM Fact_Coaching_Session
    GROUP BY player_key
),
per_player AS (
    SELECT pm.player_key,
           1.0 * COALESCE(ps.sessions, 0) / pm.active_months AS sessions_per_month,
           1.0 * pm.mmr_change / pm.active_months            AS mmr_per_month,
           pm.win_rate
    FROM player_months pm
    LEFT JOIN player_sessions ps ON ps.player_key = pm.player_key
)
SELECT CASE WHEN sessions_per_month < 2 THEN '1: under 2 sessions/month'
            WHEN sessions_per_month < 4 THEN '2: 2-4 sessions/month'
            WHEN sessions_per_month < 6 THEN '3: 4-6 sessions/month'
            ELSE                             '4: 6+ sessions/month' END AS coaching_band,
       COUNT(*)                                  AS players,
       ROUND(AVG(sessions_per_month), 1)         AS avg_sessions_per_month,
       ROUND(AVG(mmr_per_month), 1)              AS avg_mmr_gain_per_month,
       ROUND(100 * AVG(win_rate), 1)             AS win_rate_pct
FROM per_player
GROUP BY coaching_band
ORDER BY coaching_band;


-- name: q2_revenue_per_coaching_hour
-- Q2. Which site earns the most per coaching hour?
-- Revenue (net of discounts) from Fact_Revenue, divided by the coaching
-- hours from Fact_Coach_Shift. Booked hours = hours actually coached;
-- scheduled hours = hours the site paid coaches to be available.
WITH revenue AS (
    SELECT site_key, SUM(net_amount) AS net_revenue
    FROM Fact_Revenue
    GROUP BY site_key
),
hours AS (
    SELECT site_key,
           SUM(hours_booked)    AS booked_hours,
           SUM(hours_scheduled) AS scheduled_hours
    FROM Fact_Coach_Shift
    GROUP BY site_key
)
SELECT s.site_name,
       ROUND(r.net_revenue, 0)                       AS net_revenue,
       ROUND(h.booked_hours, 0)                      AS booked_hours,
       ROUND(h.scheduled_hours, 0)                   AS scheduled_hours,
       ROUND(r.net_revenue / h.booked_hours, 2)      AS revenue_per_booked_hour,
       ROUND(r.net_revenue / h.scheduled_hours, 2)   AS revenue_per_scheduled_hour
FROM Dim_Site s
JOIN revenue r ON r.site_key = s.site_key
JOIN hours   h ON h.site_key = s.site_key
ORDER BY revenue_per_booked_hour DESC;


-- name: q3_coach_utilization_by_week
-- Q3. Are coaches overbooked or idle?
-- Utilization = hours booked / hours scheduled, by site and week.
-- Over 100% means coaches ran sessions beyond their scheduled hours.
SELECT d.week_start,
       s.site_name,
       COUNT(DISTINCT f.coach_key)                              AS coaches_on_shift,
       SUM(f.hours_scheduled)                                   AS scheduled_hours,
       SUM(f.hours_booked)                                      AS booked_hours,
       ROUND(100.0 * SUM(f.hours_booked) / SUM(f.hours_scheduled), 1) AS utilization_pct
FROM Fact_Coach_Shift f
JOIN Dim_Date d ON d.date_key = f.date_key
JOIN Dim_Site s ON s.site_key = f.site_key
GROUP BY d.week_start, s.site_name
ORDER BY d.week_start, s.site_name;


-- name: q4_revenue_and_retention_by_plan
-- Q4. Which plans bring the most revenue and the longest-staying players?
-- Retention: months from sign-up to cancel date (or to the end of the
-- period, 2025-06-29, for players still active). Players who are still
-- active could stay longer, so this undercounts the best plans slightly.
WITH player_plan AS (
    SELECT DISTINCT player_key, plan_key FROM Fact_Revenue
),
tenure AS (
    SELECT pp.plan_key,
           p.player_key,
           (julianday(COALESCE(p.cancel_date, '2025-06-29')) - julianday(p.signup_date)) / 30.0
               AS months_retained,
           CASE WHEN p.cancel_date IS NULL THEN 1 ELSE 0 END AS still_active
    FROM player_plan pp
    JOIN Dim_Player p ON p.player_key = pp.player_key
),
revenue AS (
    SELECT plan_key, SUM(net_amount) AS net_revenue
    FROM Fact_Revenue
    GROUP BY plan_key
)
SELECT pl.plan_name,
       COUNT(t.player_key)                                  AS paying_players,
       ROUND(r.net_revenue, 0)                              AS net_revenue,
       ROUND(r.net_revenue / COUNT(t.player_key), 0)        AS revenue_per_player,
       ROUND(AVG(t.months_retained), 1)                     AS avg_months_retained,
       ROUND(100.0 * AVG(t.still_active), 1)                AS pct_still_active
FROM Dim_Plan pl
JOIN tenure  t ON t.plan_key = pl.plan_key
JOIN revenue r ON r.plan_key = pl.plan_key
GROUP BY pl.plan_name, r.net_revenue
ORDER BY net_revenue DESC;
