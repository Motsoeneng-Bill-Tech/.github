#!/usr/bin/env python3
"""
Motsoeneng Bill Tech - Engineering Telemetry Engine

Discovers the organization's real membership and repositories, computes every
metric live from the GitHub API, and writes:
  - docs/data/metrics.json   (canonical dataset — the interactive dashboard reads this)
  - assets/graphs/<login>.svg, assets/leaderboard_card.svg
  - profile/README.md        (regenerated marker sections)

There is no hardcoded roster and no fallback/cached data anywhere in this
pipeline. If any step can't be completed with real data, the script exits
non-zero and writes nothing — the previously published (real) data stays
live rather than being replaced with a guess.
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)  # allow `import gh_api, render` when run as a plain script

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

SCHEMA_VERSION = 1
ROSTER_DETAIL_CAP = 12
REPO_CHUNK_SIZE = 6

# Contribution tiers are activity descriptors, not job titles — thresholds are on
# real, live-computed firm commits. (Previously the site presented these as if they
# were actual org roles, e.g. "Principal Architect" — that was never true data.)
TIERS = [
    (500, "Top Contributor"),
    (200, "Lead Contributor"),
    (100, "Core Contributor"),
    (40, "Regular Contributor"),
    (1, "Contributor"),
    (0, "New Member"),
]


def get_tier_label(firm_commits):
    for threshold, label in TIERS:
        if firm_commits >= threshold:
            return label
    return TIERS[-1][1]


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
    print(f"  found {len(repos_raw)} repositories: {', '.join(r['name'] for r in repos_raw)}")

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    print("Fetching each member's real contribution calendar...")
    member_contribs = {}
    for m in members_raw:
        cc = gh_api.fetch_member_contributions(m["login"], m["created_at"], now_iso, token)
        member_contribs[m["login"]] = cc
        print(f"  {m['login']}: {cc['contributionCalendar']['totalContributions']:,} total contributions since {m['created_at'][:10]}")

    print("Computing real per-repo commit attribution (replaces any cached/fake numbers)...")
    commit_matrix = gh_api.fetch_firm_commit_matrix(ORG_NAME, repos_raw, members_raw, token, chunk_size=REPO_CHUNK_SIZE)

    end_rate = gh_api.get_rate_limit(token)
    cost_used = max(0, (start_rate.get("remaining") or 0) - (end_rate.get("remaining") or 0))
    print(f"Rate limit remaining after run: {end_rate.get('remaining', '?')} (used ~{cost_used} points)")

    data = build_dataset(
        members_raw, repos_raw, member_contribs, commit_matrix, now,
        rate_meta={
            "cost_used_total": cost_used,
            "remaining": end_rate.get("remaining"),
            "reset_at": end_rate.get("resetAt"),
        },
    )
    validate_dataset(data, {m["login"] for m in members_raw}, {r["name"] for r in repos_raw})
    return data


def build_dataset(members_raw, repos_raw, member_contribs, commit_matrix, now, rate_meta):
    warnings = []

    # --- per-repo rollups ---
    repos_out = []
    for r in repos_raw:
        mat = commit_matrix.get(r["name"], {"total_commits": 0, "by_login": {}})
        attributed = sum(mat["by_login"].values())
        if r["is_empty"]:
            warnings.append(f"Repository '{r['name']}' has no commits yet.")
        repos_out.append({
            "name": r["name"],
            "description": r["description"],
            "html_url": r["html_url"],
            "visibility": r["visibility"],
            "primary_language": r["primary_language"],
            "default_branch": r["default_branch"],
            "is_empty": r["is_empty"],
            "is_archived": r["is_archived"],
            "total_commits_default_branch": mat["total_commits"],
            "attributed_member_commits": attributed,
            "unattributed_commits": max(0, mat["total_commits"] - attributed),
        })

    total_firm_commits_org = sum(sum(mat["by_login"].values()) for mat in commit_matrix.values())

    # --- per-member derivation ---
    members_out = []
    day_counts_union = {}
    earliest_created = None

    for m in members_raw:
        login = m["login"]
        cc = member_contribs[login]
        cal = cc["contributionCalendar"]

        firm_by_repo = {}
        for repo_name, mat in commit_matrix.items():
            c = mat["by_login"].get(login, 0)
            if c:
                firm_by_repo[repo_name] = c
        firm_by_repo = dict(sorted(firm_by_repo.items(), key=lambda kv: -kv[1]))
        firm_total = sum(firm_by_repo.values())

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

        members_out.append({
            "login": login,
            "name": (m.get("name") or "").strip() or None,
            "avatar_url": m["avatar_url"],
            "html_url": f"https://github.com/{login}",
            "org_role": m["org_role"],
            "created_at": m["created_at"],
            "profile": {
                "bio": m.get("bio"),
                "company": m.get("company"),
                "location": m.get("location"),
                "website_url": m.get("website_url"),
            },
            "contributions": {
                "total": cal["totalContributions"],
                "commits": cc["totalCommitContributions"],
                "pull_requests": cc["totalPullRequestContributions"],
                "reviews": cc["totalPullRequestReviewContributions"],
                "issues": cc["totalIssueContributions"],
                "restricted": cc["restrictedContributionsCount"],
            },
            "firm_commits": {
                "total": firm_total,
                "by_repo": firm_by_repo,
                "top_repos": list(firm_by_repo.keys()),
            },
            "share_pct": round((firm_total / total_firm_commits_org * 100), 1) if total_firm_commits_org else 0.0,
            "tier": get_tier_label(firm_total),
            "calendar": {
                "from": created_dt.date().isoformat(),
                "to": now.date().isoformat(),
                "total": cal["totalContributions"],
                "active_days": active_days,
                "total_days": total_days,
                "active_pct": round((active_days / total_days * 100), 1) if total_days else 0.0,
                **render.calendar_streaks(day_counts),
                "weeks": render.build_calendar_grid(day_counts, created_dt.date(), now.date()),
            },
        })

    members_out.sort(key=lambda x: -x["firm_commits"]["total"])
    for idx, m in enumerate(members_out, start=1):
        m["rank"] = idx

    org_calendar_start = earliest_created.date() if earliest_created else now.date()
    org_calendar_weeks = render.build_calendar_grid(day_counts_union, org_calendar_start, now.date())

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
            "repo_count": len(repos_out),
            "totals": {
                "total_contributions": sum(m["contributions"]["total"] for m in members_out),
                "total_commit_contributions": sum(m["contributions"]["commits"] for m in members_out),
                "total_pr_contributions": sum(m["contributions"]["pull_requests"] for m in members_out),
                "total_review_contributions": sum(m["contributions"]["reviews"] for m in members_out),
                "total_firm_commits": total_firm_commits_org,
            },
            "calendar": {
                "from": org_calendar_start.isoformat(),
                "to": now.date().isoformat(),
                "weeks": org_calendar_weeks,
            },
        },
        "repos": sorted(repos_out, key=lambda r: -r["total_commits_default_branch"]),
        "members": members_out,
        "meta": {
            "generation_ok": True,
            "rate_limit": rate_meta,
            "warnings": warnings,
        },
    }


def validate_dataset(data, expected_logins, expected_repo_names):
    """Structural completeness check on top of API success — a member or repo that
    legitimately has zero commits is valid data; one that's silently absent is not."""
    got_logins = {m["login"] for m in data["members"]}
    if got_logins != expected_logins:
        raise gh_api.DataIntegrityError(f"Member set mismatch: expected {expected_logins}, got {got_logins}")
    got_repos = {r["name"] for r in data["repos"]}
    if got_repos != expected_repo_names:
        raise gh_api.DataIntegrityError(f"Repo set mismatch: expected {expected_repo_names}, got {got_repos}")
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
    print(f"Wrote {len(data['members'])} member activity graphs to {GRAPHS_DIR}")

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
    print(
        f"Done. {data['org']['member_count']} members, {data['org']['repo_count']} repos, "
        f"{data['org']['totals']['total_firm_commits']:,} real firm commits, "
        f"{data['org']['totals']['total_contributions']:,} total contributions."
    )


if __name__ == "__main__":
    main()
