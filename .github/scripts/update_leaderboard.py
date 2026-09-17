#!/usr/bin/env python3
"""
Motsoeneng Bill Tech - Engineering Telemetry Engine

Builds the executive view of the engineering division from live GitHub data:
  - docs/data/metrics.json   (canonical dataset — the dashboard reads this)
  - assets/graphs/<login>.svg, assets/leaderboard_card.svg
  - profile/README.md        (regenerated marker sections)

Design rule, enforced throughout: NO CONTRIBUTION COUNTS. Not in ranking, not in
display, not as a footnote. Counting commits, pull requests or reviews rewards
volume, and volume is trivially manufactured — this org has a real example of a
single day carrying over a thousand commits. Every metric here is instead built on
the DISTINCT ACTIVE DAY: a day counts once, however much was pushed on it. Showing
up is the only thing that moves a number.

There is no hardcoded roster and no fallback/cached data anywhere in this pipeline.
If any step can't be completed with real data the script exits non-zero and writes
nothing, so the previously published (real) data stays live rather than being
replaced with a guess.
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # allow `import gh_api, render` when run as a plain script

import analytics
import gh_api
import render

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ORG_NAME = "Motsoeneng-Bill-Tech"
ORG_DISPLAY_NAME = "Motsoeneng Bill Tech"
REPO_NAME = ".github"
DASHBOARD_URL = "https://motsoeneng-bill-tech.github.io/.github/"

ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
PROFILE_README = os.path.join(ROOT_DIR, "profile", "README.md")
GRAPHS_DIR = os.path.join(ROOT_DIR, "assets", "graphs")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
DOCS_DATA_PATH = os.path.join(ROOT_DIR, "docs", "data", "metrics.json")

SCHEMA_VERSION = 2
ROSTER_DETAIL_CAP = 12
RELIABILITY_WINDOW_DAYS = 30
DORMANT_AFTER_DAYS = 14
NEW_MEMBER_DAYS = 7
RECENTLY_ACTIVE_DAYS = 7

# Cadence bands describe how regularly someone shows up. They are not job titles and
# not achievements — they're read off the reliability window and nothing else, so no
# amount of activity on any single day can promote anyone.
CADENCE_BANDS = [
    (90, "Daily"),
    (70, "Near-daily"),
    (40, "Regular"),
    (15, "Intermittent"),
    (0, "Occasional"),
]


def cadence_band(reliability_pct, days_since_last, tenure_days):
    if tenure_days < NEW_MEMBER_DAYS:
        return "Newly onboarded"
    if days_since_last is None or days_since_last >= DORMANT_AFTER_DAYS:
        return "Dormant"
    for threshold, label in CADENCE_BANDS:
        if reliability_pct >= threshold:
            return label
    return CADENCE_BANDS[-1][1]


def engagement_status(days_since_last):
    if days_since_last is None:
        return "No recorded activity"
    if days_since_last <= 1:
        return "Active today"
    if days_since_last <= RECENTLY_ACTIVE_DAYS:
        return "Active this week"
    if days_since_last < DORMANT_AFTER_DAYS:
        return "Slowing"
    return "Dormant"


def gather_all_data():
    """Returns a fully-populated, validated data dict, or raises. Never returns partial data."""
    token = gh_api.get_token()
    if not token:
        raise gh_api.GraphQLError(
            "No GitHub token available. Set ORG_LEADERBOARD_TOKEN (needs read:org + repo scopes)."
        )

    start_rate = gh_api.get_rate_limit(token)
    print(f"Rate limit remaining before run: {start_rate.get('remaining', '?')}")

    print(f"Discovering members of {ORG_NAME}...")
    members_raw = gh_api.discover_org_members(ORG_NAME, token)
    print(f"  found {len(members_raw)} members: {', '.join(m['login'] for m in members_raw)}")

    print(f"Discovering repositories of {ORG_NAME}...")
    repos_raw = gh_api.discover_org_repos(ORG_NAME, token)
    print(f"  found {len(repos_raw)} repositories")

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    print("Fetching each engineer's day-level activity calendar...")
    member_contribs = {}
    for m in members_raw:
        cc = gh_api.fetch_member_contributions(m["login"], m["created_at"], now_iso, token)
        member_contribs[m["login"]] = cc
        active = sum(
            1 for w in cc["contributionCalendar"]["weeks"]
            for d in w["contributionDays"] if d["contributionCount"] > 0
        )
        print(f"  {m['login']}: {active} active days since {m['created_at'][:10]}")

    print("Walking each project's commit history for dates (never counts)...")
    repo_histories = {}
    for r in repos_raw:
        hist = gh_api.fetch_repo_commit_history(ORG_NAME, r, token)
        repo_histories[r["name"]] = hist
        note = " (truncated)" if hist["truncated"] else ""
        print(f"  {r['name']}: {len(hist['commits'])} commits scanned{note}")

    end_rate = gh_api.get_rate_limit(token)
    cost_used = max(0, (start_rate.get("remaining") or 0) - (end_rate.get("remaining") or 0))
    print(f"Rate limit remaining after run: {end_rate.get('remaining', '?')} (used ~{cost_used} points)")

    data = build_dataset(
        members_raw, repos_raw, member_contribs, repo_histories, now,
        rate_meta={
            "cost_used_total": cost_used,
            "remaining": end_rate.get("remaining"),
            "reset_at": end_rate.get("resetAt"),
        },
    )
    validate_dataset(data, {m["login"] for m in members_raw}, {r["name"] for r in repos_raw})
    return data


def build_dataset(members_raw, repos_raw, member_contribs, repo_histories, now, rate_meta):
    warnings = []
    today = now.date()
    logins = [m["login"] for m in members_raw]

    by_member_projects, by_project = analytics.build_project_involvement(repo_histories, logins, today)
    by_member_projects, by_project = analytics.attach_logins(by_member_projects, by_project)

    repo_meta = {r["name"]: r for r in repos_raw}

    # --- projects ---
    projects_out = []
    for r in repos_raw:
        p = by_project.get(r["name"], {})
        if r["is_empty"]:
            warnings.append(f"Repository '{r['name']}' has no commits yet.")
        if p.get("history_truncated"):
            warnings.append(f"Repository '{r['name']}' history was truncated — earliest activity may be under-reported.")
        projects_out.append({
            "name": r["name"],
            "display_name": render.REPO_DISPLAY_NAMES.get(r["name"], r["name"]),
            "description": r["description"] or render.REPO_DESCRIPTIONS.get(r["name"]),
            "html_url": r["html_url"],
            "visibility": r["visibility"],
            "primary_language": r["primary_language"],
            "default_branch": r["default_branch"],
            "is_archived": r["is_archived"],
            "status": p.get("status", "No activity"),
            "last_activity": p.get("last_activity"),
            "days_since_activity": p.get("days_since_activity"),
            "active_days_total": p.get("active_days_total", 0),
            "engineer_count": p.get("engineer_count", 0),
            "active_engineer_count": p.get("active_engineer_count", 0),
            "key_person_risk": p.get("key_person_risk", False),
            "sole_engineer": p.get("sole_engineer"),
            "current_engineers": p.get("current_engineers", []),
            "engineers": [
                {
                    "login": e["login"],
                    "active_days": e["active_days"],
                    "first_active": e["first_active"],
                    "last_active": e["last_active"],
                    "days_since_last": e["days_since_last"],
                    "is_current": e["is_current"],
                }
                for e in p.get("engineers", [])
            ],
            "outside_contributors": p.get("outside_contributors", []),
        })

    # --- engineers ---
    members_out = []
    day_counts_union = {}
    earliest_created = None

    for m in members_raw:
        login = m["login"]
        cal = member_contribs[login]["contributionCalendar"]

        created_dt = datetime.fromisoformat(m["created_at"].replace("Z", "+00:00"))
        if earliest_created is None or created_dt < earliest_created:
            earliest_created = created_dt

        day_counts = {}
        for week in cal["weeks"]:
            for day in week["contributionDays"]:
                day_counts[day["date"]] = day["contributionCount"]
                day_counts_union[day["date"]] = day_counts_union.get(day["date"], 0) + day["contributionCount"]

        active_days = sum(1 for c in day_counts.values() if c > 0)
        total_days = len(day_counts)
        streaks = render.calendar_streaks(day_counts)
        reliability = analytics.recent_active_ratio(day_counts, today, RELIABILITY_WINDOW_DAYS)
        trend = analytics.cadence_trend(day_counts, today)
        weekdays = analytics.weekday_pattern(day_counts, today)

        last_active_date = None
        for d in sorted(day_counts.keys(), reverse=True):
            if day_counts[d] > 0:
                last_active_date = d
                break
        days_since_last = (today - datetime.fromisoformat(last_active_date).date()).days if last_active_date else None
        tenure_days = (today - created_dt.date()).days + 1

        # Project portfolio, enriched with each project's own metadata
        projects = []
        for record in by_member_projects.get(login, []):
            meta = repo_meta.get(record["repo"], {})
            project_state = by_project.get(record["repo"], {})
            projects.append({
                "repo": record["repo"],
                "display_name": render.REPO_DISPLAY_NAMES.get(record["repo"], record["repo"]),
                "primary_language": meta.get("primary_language"),
                "visibility": meta.get("visibility"),
                "active_days": record["active_days"],
                "first_active": record["first_active"],
                "last_active": record["last_active"],
                "days_since_last": record["days_since_last"],
                "is_current": record["is_current"],
                "project_status": project_state.get("status"),
                "is_sole_engineer": project_state.get("sole_engineer") == login,
                "is_only_active_engineer": (
                    project_state.get("active_engineer_count") == 1 and record["is_current"]
                ),
            })

        current_projects = [p for p in projects if p["is_current"]]
        languages = sorted({p["primary_language"] for p in projects if p["primary_language"]})
        carries_risk = [p["display_name"] for p in projects if p["is_only_active_engineer"]]

        members_out.append({
            "login": login,
            "name": (m.get("name") or "").strip() or None,
            "avatar_url": m["avatar_url"],
            "html_url": f"https://github.com/{login}",
            "org_role": m["org_role"],
            "created_at": m["created_at"],
            "tenure_days": tenure_days,
            "profile": {
                "bio": m.get("bio"),
                "company": m.get("company"),
                "location": m.get("location"),
                "website_url": m.get("website_url"),
            },
            "reliability": reliability,
            "consistency": {
                "active_days": active_days,
                "total_days": total_days,
                "pct": round((active_days / total_days * 100), 1) if total_days else 0.0,
                "longest_streak": streaks["longest_streak"],
                "current_streak": streaks["current_streak"],
                "last_active_date": last_active_date,
                "days_since_last_active": days_since_last,
            },
            "trend": trend,
            "weekday_pattern": weekdays,
            "projects": projects,
            "project_count": len(projects),
            "current_project_count": len(current_projects),
            "languages": languages,
            "carries_key_person_risk_for": carries_risk,
            "engagement_status": engagement_status(days_since_last),
            "cadence_band": cadence_band(reliability["pct"], days_since_last, tenure_days),
            "calendar": {
                "from": created_dt.date().isoformat(),
                "to": today.isoformat(),
                "active_days": active_days,
                "total_days": total_days,
                "active_pct": round((active_days / total_days * 100), 1) if total_days else 0.0,
                **streaks,
                "weeks": render.build_calendar_grid(day_counts, created_dt.date(), today),
            },
        })

    # Ranked on reliability first, then streak continuity, then tenure. Every key in this
    # chain is day-based, so no single day of activity — however large — can move anyone up.
    members_out.sort(key=lambda x: (
        -x["reliability"]["pct"],
        -x["consistency"]["current_streak"],
        -x["consistency"]["longest_streak"],
        x["created_at"],
    ))
    for idx, m in enumerate(members_out, start=1):
        m["rank"] = idx

    org_calendar_start = earliest_created.date() if earliest_created else today
    org_calendar_weeks = render.build_calendar_grid(day_counts_union, org_calendar_start, today)

    at_risk = [p for p in projects_out if p["key_person_risk"]]
    active_projects = [p for p in projects_out if p["status"] == "Active"]
    dormant_projects = [p for p in projects_out if p["status"] in ("Dormant", "No activity")]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": os.environ.get("GITHUB_SHA", "local"),
        "org": {
            "login": ORG_NAME,
            "name": ORG_DISPLAY_NAME,
            "avatar_url": f"https://github.com/{ORG_NAME}.png",
            "html_url": f"https://github.com/{ORG_NAME}",
            "member_count": len(members_out),
            "repo_count": len(projects_out),
            "summary": {
                "avg_reliability_pct": round(
                    sum(m["reliability"]["pct"] for m in members_out) / len(members_out), 1
                ) if members_out else 0.0,
                "engineers_active_this_week": sum(
                    1 for m in members_out
                    if m["consistency"]["days_since_last_active"] is not None
                    and m["consistency"]["days_since_last_active"] <= RECENTLY_ACTIVE_DAYS
                ),
                "engineers_dormant": sum(1 for m in members_out if m["cadence_band"] == "Dormant"),
                "peak_streak": max((m["consistency"]["longest_streak"] for m in members_out), default=0),
                "projects_active": len(active_projects),
                "projects_dormant": len(dormant_projects),
                "projects_at_key_person_risk": len(at_risk),
                "key_person_risk_projects": [p["display_name"] for p in at_risk],
                "reliability_window_days": RELIABILITY_WINDOW_DAYS,
            },
            "calendar": {
                "from": org_calendar_start.isoformat(),
                "to": today.isoformat(),
                "weeks": org_calendar_weeks,
            },
        },
        "projects": sorted(
            projects_out,
            key=lambda p: (p["days_since_activity"] if p["days_since_activity"] is not None else 9999, p["name"]),
        ),
        "members": members_out,
        "meta": {
            "generation_ok": True,
            "rate_limit": rate_meta,
            "warnings": warnings,
            "disclosures": [
                "Every figure is derived from days on which work was recorded in GitHub — never from how much was pushed on any given day.",
                "Commit attribution follows GitHub's own account linking. Work committed from an unlinked email address is listed separately against the project, never merged into an engineer's record.",
                "Project involvement reflects work merged into each project's default branch. Work still in progress on a side branch is not yet visible here.",
                "This page measures engagement and delivery cadence. It cannot measure the difficulty, quality or business value of the work, and should not be read as a performance rating.",
            ],
        },
    }


def validate_dataset(data, expected_logins, expected_repo_names):
    """Structural completeness check on top of API success — a member or project that
    legitimately has no activity is valid data; one that's silently absent is not."""
    got_logins = {m["login"] for m in data["members"]}
    if got_logins != expected_logins:
        raise gh_api.DataIntegrityError(f"Member set mismatch: expected {expected_logins}, got {got_logins}")
    got_repos = {p["name"] for p in data["projects"]}
    if got_repos != expected_repo_names:
        raise gh_api.DataIntegrityError(f"Project set mismatch: expected {expected_repo_names}, got {got_repos}")
    if data["org"]["member_count"] == 0 or data["org"]["repo_count"] == 0:
        raise gh_api.DataIntegrityError("Org member_count or repo_count is zero.")
    if not data.get("generated_at"):
        raise gh_api.DataIntegrityError("Missing generated_at timestamp.")


def write_outputs(data):
    """Only ever called after gather_all_data() has returned a complete, validated dataset."""
    os.makedirs(GRAPHS_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(DOCS_DATA_PATH), exist_ok=True)

    with open(DOCS_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Wrote {DOCS_DATA_PATH}")

    for member in data["members"]:
        svg = render.render_member_calendar_svg(member)
        with open(os.path.join(GRAPHS_DIR, f"{member['login']}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    print(f"Wrote {len(data['members'])} engineer activity graphs to {GRAPHS_DIR}")

    with open(os.path.join(ASSETS_DIR, "leaderboard_card.svg"), "w", encoding="utf-8") as f:
        f.write(render.render_overview_card_svg(data))
    print("Wrote assets/leaderboard_card.svg")

    if not os.path.exists(PROFILE_README):
        raise FileNotFoundError(f"{PROFILE_README} not found")
    with open(PROFILE_README, "r", encoding="utf-8") as f:
        readme = f.read()
    readme = render.update_readme(
        readme, data,
        org_name=ORG_NAME, repo_name=REPO_NAME,
        dashboard_url=DASHBOARD_URL, roster_cap=ROSTER_DETAIL_CAP,
    )
    with open(PROFILE_README, "w", encoding="utf-8") as f:
        f.write(readme)
    print(f"Updated {PROFILE_README}")


def main():
    print("=== Motsoeneng Bill Tech - Engineering Telemetry Engine ===")
    try:
        data = gather_all_data()
    except (gh_api.GraphQLError, gh_api.DataIntegrityError) as e:
        print(f"FATAL: {e}", file=sys.stderr)
        print("Aborting without writing any output — previously published data stays live.", file=sys.stderr)
        sys.exit(1)

    write_outputs(data)
    for w in data["meta"]["warnings"]:
        print(f"! {w}")
    s = data["org"]["summary"]
    print(
        f"Done. {data['org']['member_count']} engineers, {data['org']['repo_count']} projects, "
        f"team reliability {s['avg_reliability_pct']}%, {s['engineers_active_this_week']} active this week, "
        f"{s['projects_at_key_person_risk']} project(s) at key-person risk."
    )


if __name__ == "__main__":
    main()
