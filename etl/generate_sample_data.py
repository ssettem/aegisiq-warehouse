"""
Generate SYNTHETIC source data for the AegisIQ case study.

Nothing here is real. AegisIQ is a fictional Dota 2 coaching company from a
graduate course case. This script invents the CSV exports its systems would
produce, so the ETL and queries have something realistic to work on.

What it writes (into data/raw/):
    players.csv, coaches.csv, heroes.csv, plans.csv   <- shared master lists
    <SITE>/sessions.csv, payments.csv, shifts.csv, matches.csv
                                                      <- one export per site

Built-in mess, so the ETL has real cleaning to do:
    1. Site names typed inconsistently ("austin", "AUS", "Seattle WA", ...)
    2. About 1% of session rows exported twice (duplicate sessions)
    3. About 3% of session ratings left blank (player skipped the survey)
    4. About 1.5% of pay-per-session payments missing (for the quality check)

Built-in business assumption (so the analysis has a pattern to find):
    a player's chance of winning a match rises a little with the number of
    coaching sessions they had in the previous 14 days. Because this effect
    is coded below, the analysis "finding" demonstrates the query, not a
    real-world fact about coaching.

The random seed is fixed, so every run produces exactly the same files.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# Reporting period: 25 full weeks, Monday 6 Jan 2025 to Sunday 29 Jun 2025.
START = date(2025, 1, 6)
END = date(2025, 6, 29)
ALL_DAYS = [START + timedelta(days=i) for i in range((END - START).days + 1)]

# site code: (proper name, number of coaches, number of players, messy spellings)
SITES = {
    "AUS": ("Austin",  10, 300, ["austin", "AUS", "Austin TX"]),
    "CHI": ("Chicago", 10, 270, ["Chicago ", "CHI", "chicago"]),
    "SEA": ("Seattle",  8, 360, ["Seattle WA", "SEA", "seattle"]),
    "ATL": ("Atlanta", 10, 210, ["atlanta", "ATL", "Atlanta GA"]),
}
MESSY_SITE_RATE = 0.04

# plan code: (name, type, price, sessions included per month,
#             share of players, monthly churn chance, avg sessions per week)
PLANS = {
    "PPS":   ("Pay Per Session", "Pay per session", 40.0, None, 0.45, 0.22, 0.45),
    "BASIC": ("Monthly Basic",   "Subscription",   120.0, 4,    0.35, 0.12, 0.95),
    "PRO":   ("Monthly Pro",     "Subscription",   220.0, 8,    0.20, 0.07, 1.80),
}

HEROES = [
    ("Anti-Mage", "Carry"), ("Phantom Assassin", "Carry"), ("Juggernaut", "Carry"),
    ("Faceless Void", "Carry"), ("Shadow Fiend", "Mid"), ("Invoker", "Mid"),
    ("Storm Spirit", "Mid"), ("Queen of Pain", "Mid"), ("Puck", "Mid"),
    ("Axe", "Offlane"), ("Mars", "Offlane"), ("Tidehunter", "Offlane"),
    ("Centaur Warrunner", "Offlane"), ("Earthshaker", "Soft Support"),
    ("Rubick", "Soft Support"), ("Tusk", "Soft Support"),
    ("Crystal Maiden", "Hard Support"), ("Lion", "Hard Support"),
    ("Witch Doctor", "Hard Support"), ("Dazzle", "Hard Support"),
]
ROLES = ["Carry", "Mid", "Offlane", "Soft Support", "Hard Support"]
FIRST_NAMES = ["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley",
               "Jamie", "Avery", "Quinn", "Drew", "Reese", "Skyler", "Parker"]
LAST_NAMES = ["Nguyen", "Patel", "Garcia", "Kim", "Smith", "Lopez", "Chen",
              "Johnson", "Brown", "Singh", "Martinez", "Lee", "Davis", "Wilson"]


def site_label(code):
    """Return the site name, occasionally typed the 'wrong' way."""
    name, _, _, messy = SITES[code]
    return random.choice(messy) if random.random() < MESSY_SITE_RATE else name


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


# --- Master lists ---------------------------------------------------------

heroes = [(f"H{i:02d}", name, role) for i, (name, role) in enumerate(HEROES, 1)]
write_csv(RAW / "heroes.csv", ["hero_id", "hero_name", "hero_role"], heroes)

write_csv(RAW / "plans.csv",
          ["plan_code", "plan_name", "plan_type", "price", "sessions_included"],
          [(code, p[0], p[1], p[2], p[3] or "") for code, p in PLANS.items()])

# Coaches: each works either Mon-Fri or Wed-Sun, 6 hours a day.
coaches = []          # (coach_id, site_code, name, role, level, workdays)
for code, (_, n_coaches, _, _) in SITES.items():
    for _ in range(n_coaches):
        coach_id = f"C{len(coaches) + 1:03d}"
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        workdays = {0, 1, 2, 3, 4} if len(coaches) % 2 == 0 else {2, 3, 4, 5, 6}
        level = random.choices(["Junior", "Mid", "Senior"], [0.4, 0.4, 0.2])[0]
        coaches.append((coach_id, code, name, random.choice(ROLES), level, workdays))
write_csv(RAW / "coaches.csv",
          ["coach_id", "home_site", "coach_name", "specialty_role", "experience_level"],
          [(c[0], site_label(c[1]), c[2], c[3], c[4]) for c in coaches])

# Players: sign up between January and April; some cancel later.
players = []          # dicts, kept for the session/match/payment steps
signup_window = (date(2025, 4, 30) - START).days
for code, (_, _, n_players, _) in SITES.items():
    for _ in range(n_players):
        plan = random.choices(list(PLANS), [p[4] for p in PLANS.values()])[0]
        signup = START + timedelta(days=random.randint(0, signup_window))
        # Each 30 days the player may cancel (subscriptions cancel at renewal).
        cancel, months = None, 1
        while signup + timedelta(days=30 * months) <= END:
            if random.random() < PLANS[plan][5]:
                cancel = signup + timedelta(days=30 * months)
                break
            months += 1
        players.append({
            "id": f"P{len(players) + 1:04d}",
            "site": code,
            "plan": plan,
            "signup": signup,
            "cancel": cancel,
            "last_day": (cancel - timedelta(days=1)) if cancel else END,
            "mmr": max(300, min(7500, int(random.gauss(3200, 1100)))),
            "region": "US West" if code == "SEA" else random.choice(["US East", "US Central"]),
            # Some players book far more than others on the same plan.
            "rate": PLANS[plan][6] * random.uniform(0.3, 1.7),
            "heroes": random.sample(heroes, 3),
        })
write_csv(RAW / "players.csv",
          ["player_id", "home_site", "plan_code", "starting_mmr", "region",
           "signup_date", "cancel_date"],
          [(p["id"], site_label(p["site"]), p["plan"], p["mmr"], p["region"],
            p["signup"], p["cancel"] or "") for p in players])

# --- Shifts (one coach, one day) ------------------------------------------

shifts = {code: [] for code in SITES}
working = {}          # (site_code, day) -> list of coach_ids on shift
for coach_id, code, *_, workdays in coaches:
    for day in ALL_DAYS:
        if day.weekday() in workdays and random.random() > 0.04:   # ~4% days off
            shifts[code].append((coach_id, day, 6.0, site_label(code)))
            working.setdefault((code, day), []).append(coach_id)

# --- Sessions, matches, payments ------------------------------------------

sessions = {code: [] for code in SITES}
matches = {code: [] for code in SITES}
payments = {code: [] for code in SITES}
n_sessions = n_matches = n_payments = 0     # running counters for the IDs


for p in players:
    code, plan = p["site"], p["plan"]
    active_days = [d for d in ALL_DAYS if p["signup"] <= d <= p["last_day"]]

    # Coaching sessions
    session_days = []
    for day in active_days:
        coaches_on_shift = working.get((code, day))
        if coaches_on_shift and random.random() < p["rate"] / 7:
            n_sessions += 1
            session_id = f"S{n_sessions:06d}"
            duration = random.choices([60, 90], [0.8, 0.2])[0]
            fee = PLANS["PPS"][2] * duration / 60 if plan == "PPS" else 0.0
            rating = "" if random.random() < 0.03 else random.choices(
                [2, 3, 4, 5], [0.05, 0.2, 0.45, 0.3])[0]
            sessions[code].append((session_id, p["id"], random.choice(coaches_on_shift),
                                   site_label(code), day, duration, fee, rating))
            session_days.append(day)
            # Pay-per-session players pay on the day; ~1.5% of payments go missing.
            if plan == "PPS" and random.random() > 0.015:
                n_payments += 1
                payments[code].append((f"PAY{n_payments:06d}", p["id"], plan, day,
                                       fee, 0.0, session_id))

    # Subscription payments: one every 30 days from sign-up until cancel.
    if plan != "PPS":
        k = 0
        while p["signup"] + timedelta(days=30 * k) <= p["last_day"]:
            price = PLANS[plan][2]
            discount = price * 0.10 if k == 0 and random.random() < 0.2 else 0.0
            n_payments += 1
            payments[code].append((f"PAY{n_payments:06d}", p["id"], plan,
                                   p["signup"] + timedelta(days=30 * k),
                                   price, round(discount, 2), ""))
            k += 1

    # Matches: about 3 a week. Win chance = 47% + 2% per recent session (max 4).
    for day in active_days:
        if random.random() < 0.43:
            recent = sum(1 for s in session_days if 0 < (day - s).days <= 14)
            win = random.random() < 0.47 + 0.02 * min(recent, 4)
            hero = random.choice(p["heroes"]) if random.random() < 0.8 else random.choice(heroes)
            mmr_change = random.randint(22, 28) * (1 if win else -1)
            kills = random.randint(2, 12) + (2 if win else 0)
            deaths = random.randint(1, 10) - (2 if win else 0)
            assists = random.randint(3, 20)
            n_matches += 1
            match_id = f"M{n_matches:07d}"
            matches[code].append((match_id, p["id"], day, hero[0], int(win),
                                  mmr_change, kills, max(deaths, 0), assists))

# --- Write the per-site exports ------------------------------------------

for code in SITES:
    rows = sessions[code]
    # Export glitch: about 1% of session rows appear twice.
    rows = rows + random.sample(rows, k=max(1, len(rows) // 100))
    rows.sort(key=lambda r: r[0])
    write_csv(RAW / code / "sessions.csv",
              ["session_id", "player_id", "coach_id", "site", "session_date",
               "duration_min", "session_fee", "player_rating"], rows)
    write_csv(RAW / code / "payments.csv",
              ["payment_id", "player_id", "plan_code", "payment_date",
               "gross_amount", "discount", "session_id"], payments[code])
    write_csv(RAW / code / "shifts.csv",
              ["coach_id", "shift_date", "hours_scheduled", "site"], shifts[code])
    write_csv(RAW / code / "matches.csv",
              ["match_id", "player_id", "match_date", "hero_id", "is_win",
               "mmr_change", "kills", "deaths", "assists"], matches[code])

print(f"SYNTHETIC data written to {RAW}")
print(f"  players {len(players)}, coaches {len(coaches)}, "
      f"sessions {n_sessions} (before duplicates), matches {n_matches}, "
      f"payments {n_payments}")
