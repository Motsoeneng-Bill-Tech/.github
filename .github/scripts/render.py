"""
Rendering layer: turns the already-fetched, already-validated data dict into
SVGs and the profile/README.md markdown. Nothing in this module calls the
GitHub API — it only formats data it's handed.
"""

from datetime import datetime, timedelta

# --- Shared visual language -------------------------------------------------
# These hex values are duplicated (deliberately — standalone SVG files can't
# reference external CSS) in docs/assets/css/tokens.css under the comment
# "keep in sync with .github/scripts/render.py CAL_RAMP". Only the color skin
# is duplicated; the level-bucketing logic (bucket_level, below) is not.
BG = "#0a0e17"
SURFACE = "#10161f"
BORDER = "#232b38"
TEXT_PRIMARY = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_TERTIARY = "#64748b"
ACCENT = "#c9a961"
CAL_RAMP = ["#161a22", "#3a2f1a", "#6b5424", "#a3812f", "#c9a961"]
FONT_STACK = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --- Calendar math (shared by SVG + JSON, so both surfaces always agree) ---

def bucket_level(count):
    """The single place commit counts turn into a 0-4 heat level. Both the static SVGs
    and the live dashboard read the `level` this produces — never recompute it separately."""
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 9:
        return 3
    return 4


def _github_weekday(d):
    """GitHub's own convention: Sunday=0 ... Saturday=6 (Python's date.weekday() is Monday=0)."""
    return (d.weekday() + 1) % 7


def build_calendar_grid(day_counts, start_date, end_date):
    """day_counts: {'YYYY-MM-DD': count}. Returns Sunday-aligned weeks of 7 days spanning
    the Sunday on/before start_date through the Saturday on/after end_date, matching
    GitHub's own contribution calendar layout. Days outside [start_date, end_date] are
    padding (in_range=False) — e.g. before a member's account existed."""
    grid_start = start_date - timedelta(days=_github_weekday(start_date))
    grid_end = end_date + timedelta(days=6 - _github_weekday(end_date))

    weeks = []
    d = grid_start
    while d <= grid_end:
        days = []
        for _ in range(7):
            key = d.isoformat()
            count = day_counts.get(key, 0)
            days.append({
                "date": key,
                "weekday": _github_weekday(d),
                "count": count,
                "level": bucket_level(count),
                "in_range": start_date <= d <= end_date,
            })
            d += timedelta(days=1)
        weeks.append({"days": days})
    return weeks


def calendar_streaks(day_counts):
    """day_counts values are contiguous by construction (the API returns one entry per
    calendar day across the whole range, including zero-count days) — no gap handling needed."""
    if not day_counts:
        return {"longest_streak": 0, "current_streak": 0}
    ordered = [day_counts[k] for k in sorted(day_counts.keys())]
    longest = running = 0
    for count in ordered:
        running = running + 1 if count > 0 else 0
        longest = max(longest, running)
    current = 0
    for count in reversed(ordered):
        if count > 0:
            current += 1
        else:
            break
    return {"longest_streak": longest, "current_streak": current}


# --- SVG rendering -----------------------------------------------------------

def render_member_calendar_svg(member, weeks_shown=14, min_width=300):
    """Compact activity heatmap for one member — used in the README leaderboard row.
    Header shows cadence status, active days, streak, and reviews."""
    weeks = member["calendar"]["weeks"][-weeks_shown:]
    cell, gap = 10, 3
    start_x, start_y = 14, 48
    grid_w = len(weeks) * (cell + gap)
    width = max(min_width, start_x + grid_w + 14)
    height = start_y + 7 * (cell + gap) + 16

    rects = []
    month_labels = {}
    for w_idx, week in enumerate(weeks):
        col_x = start_x + w_idx * (cell + gap)
        for day in week["days"]:
            row_y = start_y + day["weekday"] * (cell + gap)
            color = CAL_RAMP[day["level"]]
            opacity = "1" if day["in_range"] else "0.3"
            if day["weekday"] == 0:
                mon = _MONTH_ABBR[int(day["date"][5:7]) - 1]
                if mon not in month_labels:
                    month_labels[mon] = col_x
            rects.append(
                f'<rect x="{col_x}" y="{row_y}" width="{cell}" height="{cell}" rx="2" '
                f'fill="{color}" fill-opacity="{opacity}" stroke="{BORDER}" stroke-width="0.5" />'
            )

    months_svg = "".join(
        f'<text x="{x}" y="{start_y - 6}" font-family="{FONT_STACK}" font-size="9" '
        f'fill="{TEXT_SECONDARY}">{name}</text>'
        for name, x in month_labels.items()
    )

    c = member.get("consistency", {})
    badge = member.get("tier_badge", "")
    status = member.get("cadence_status", member.get("tier", "Active"))
    active_pct = c.get("pct", member["calendar"]["active_pct"])
    streak = c.get("longest_streak", member["calendar"].get("longest_streak", 0))
    reviews = member["contributions"].get("reviews", 0)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="10" fill="{SURFACE}" stroke="{BORDER}" stroke-width="1" />
  <text x="{start_x}" y="18" font-family="{FONT_STACK}" font-size="12" font-weight="700" fill="{TEXT_PRIMARY}">{badge} @{member['login']} · <tspan fill="{ACCENT}">{status}</tspan></text>
  <text x="{start_x}" y="32" font-family="{FONT_STACK}" font-size="10"><tspan font-weight="700" fill="{TEXT_PRIMARY}">{active_pct:.0f}% active</tspan><tspan fill="{TEXT_TERTIARY}"> ({c.get('active_days', 0)}d) · {streak}d streak · {reviews} reviews</tspan></text>
  {months_svg}
  <g>{''.join(rects)}</g>
</svg>"""


def render_overview_card_svg(data, max_rows=8):
    """Org-wide ranked bar chart — bars represent Active Days Consistency %, NOT commit volume.
    Highlights consistent daily presence and unbroken streaks."""
    width = 860
    org = data["org"]
    members = data["members"][:max_rows]
    row_h = 36
    header_h = 96
    height = header_h + len(members) * row_h + 24

    stats = [
        ("CADENCE MODEL", "Daily Active"),
        ("ENGINEERS", str(org["member_count"])),
        ("AVG CONSISTENCY", f'{org["totals"].get("avg_consistency_pct", 0):.0f}%'),
        ("RECORD STREAK", f'{org["totals"].get("peak_streak", 0)} DAYS'),
    ]
    stat_w = 180
    stats_svg = "".join(
        f'''<g transform="translate({32 + i * (stat_w + 12)}, 56)">
    <text x="0" y="0" font-family="{FONT_STACK}" font-size="10" font-weight="600" letter-spacing="0.6" fill="{TEXT_TERTIARY}">{label}</text>
    <text x="0" y="24" font-family="{FONT_STACK}" font-size="20" font-weight="800" fill="{TEXT_PRIMARY}">{value}</text>
  </g>'''
        for i, (label, value) in enumerate(stats)
    )

    bar_x = 220
    bar_max_w = width - bar_x - 170
    rows_svg = []
    for i, m in enumerate(members):
        y = header_h + i * row_h
        c = m["consistency"]
        pct = c["pct"]
        bar_w = max(3, (pct / 100) * bar_max_w)
        badge = m.get("tier_badge", "")
        status = m.get("cadence_status", "")
        label_meta = f'{pct:.0f}% ({c["active_days"]}d) · {c["longest_streak"]}d streak'
        rows_svg.append(f'''
  <text x="32" y="{y + 22}" font-family="{FONT_STACK}" font-size="12" font-weight="700" fill="{TEXT_TERTIARY}">{badge}</text>
  <text x="56" y="{y + 22}" font-family="{FONT_STACK}" font-size="12" font-weight="700" fill="{TEXT_TERTIARY}">{i + 1:02d}</text>
  <text x="82" y="{y + 22}" font-family="{FONT_STACK}" font-size="12" font-weight="600" fill="{TEXT_PRIMARY}">@{m['login']}</text>
  <rect x="{bar_x}" y="{y + 9}" width="{bar_max_w}" height="8" rx="4" fill="{BORDER}" />
  <rect x="{bar_x}" y="{y + 9}" width="{bar_w:.1f}" height="8" rx="4" fill="{ACCENT}" />
  <text x="{bar_x + bar_max_w + 10}" y="{y + 17}" font-family="{FONT_STACK}" font-size="11" font-weight="700" fill="{ACCENT}">{status}</text>
  <text x="{bar_x + bar_max_w + 10}" y="{y + 29}" font-family="{FONT_STACK}" font-size="9" fill="{TEXT_TERTIARY}">{label_meta}</text>''')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="14" fill="{BG}" stroke="{BORDER}" stroke-width="1" />
  <text x="32" y="32" font-family="{FONT_STACK}" font-size="11" font-weight="700" letter-spacing="1.5" fill="{ACCENT}">{org['name'].upper()} · ENGINEERING DISCIPLINE &amp; CADENCE</text>
  {stats_svg}
  {''.join(rows_svg)}
</svg>"""


# --- README templating -------------------------------------------------------

def _replace_marker(content, marker, new_inner):
    start_tag = f"<!-- {marker}:START -->"
    end_tag = f"<!-- {marker}:END -->"
    if start_tag not in content or end_tag not in content:
        raise ValueError(f"README marker '{marker}' not found in profile/README.md — refusing to guess where to inject content.")
    start_idx = content.find(start_tag) + len(start_tag)
    end_idx = content.find(end_tag)
    return content[:start_idx] + "\n" + new_inner + "\n" + content[end_idx:]


def _fmt_date(iso_str):
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%b %d, %Y")


def render_badges(data, org_name):
    org = data["org"]
    avg_consistency = org["totals"].get("avg_consistency_pct", 0)
    peak_streak = org["totals"].get("peak_streak", 0)
    total_reviews = org["totals"].get("total_reviews", 0)
    return "\n".join([
        f'[![Cadence](https://img.shields.io/badge/Team_Cadence-{avg_consistency}%25_Active-c9a961?style=for-the-badge&logo=clock&logoColor=white)](https://github.com/{org_name})',
        f'[![Record Streak](https://img.shields.io/badge/Record_Streak-{peak_streak}_Days-34d399?style=for-the-badge&logo=streak&logoColor=white)](https://github.com/{org_name})',
        f'[![Code Reviews](https://img.shields.io/badge/Peer_Reviews-{total_reviews}_Completed-8a7130?style=for-the-badge&logo=github&logoColor=white)](https://github.com/{org_name})',
        f'[![Active Engineers](https://img.shields.io/badge/Engineers-{org["member_count"]}-64748b?style=for-the-badge&logo=codeforces&logoColor=white)](https://github.com/orgs/{org_name}/people)',
        '[![Compliance](https://img.shields.io/badge/Security-POPIA_Compliant-1e2430?style=for-the-badge&logo=shield&logoColor=white)](https://mb.co.za/)',
    ])


def render_solutions(data, display_names, descriptions):
    rows = ["| Platform | Visibility | Primary Language | Description |",
            "| :--- | :---: | :---: | :--- |"]
    for r in data["repos"]:
        name = display_names.get(r["name"], r["name"])
        desc = r["description"] or descriptions.get(r["name"]) or "_No description set yet._"
        lang = r["primary_language"] or "—"
        vis = "Public" if r["visibility"] == "PUBLIC" else "Private"
        rows.append(f"| **{name}** | {vis} | {lang} | {desc} |")
    return "\n".join(rows)


def render_leaderboard(data, org_name, repo_name, dashboard_url):
    rows = [
        "| Rank | Engineer | Cadence Status | Active Days & Consistency | Streak Continuity | Code Reviews | Pull Requests | 14-Week Activity Heatmap |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for m in data["members"]:
        avatar = f'<img src="{m["avatar_url"]}" width="30" height="30" style="border-radius:50%; vertical-align:middle;" />'
        activity_img = (
            f'<img src="https://cdn.jsdelivr.net/gh/{org_name}/{repo_name}@main/assets/graphs/{m["login"]}.svg" '
            f'width="220" height="64" alt="{m["login"]} activity graph" />'
        )
        profile_link = f'[↗ profile]({dashboard_url}#/member/{m["login"]})'

        c = m["consistency"]
        status_chip = f'**{m.get("tier_badge", "")} {m.get("cadence_status", "")}**'
        consistency_display = f'**{c["pct"]:.0f}%** <br/>`{c["active_days"]}/{c["total_days"]} days`'
        streak_display = f'**{c["longest_streak"]}d** record <br/>`{c["current_streak"]}d current`'
        reviews_display = f'**{m["contributions"]["reviews"]}** reviews'
        prs_display = f'**{m["contributions"]["pull_requests"]}** PRs'

        rows.append(
            f'| **{m["rank"]:02d}** | [{avatar} **@{m["login"]}**]({m["html_url"]}) <br/>{profile_link} '
            f'| {status_chip} '
            f'| {consistency_display} '
            f'| {streak_display} '
            f'| {reviews_display} '
            f'| {prs_display} '
            f'| {activity_img} |'
        )
    return "\n".join(rows)


def render_roster(data, org_name, repo_name, cap):
    members = data["members"][:cap]
    cards = []
    for m in members:
        top_repos = ", ".join(f"`{r}`" for r in m["firm_commits"]["top_repos"][:3]) or "_No firm repository commits yet._"
        display_name = m["name"] or m["login"]
        c = m["consistency"]
        commits_per_active = m.get("commits_per_active_day", 0.0)

        # Build cadence callout:
        if m.get("cadence_status") == "Sporadic Pusher":
            callout = f"""> ⚠️ **Cadence Alert**: This member shows bursty bulk-push activity averaging **{commits_per_active:.1f} commits per active day**, but was present on only **{c['pct']:.0f}%** of days. The engineering division prioritizes consistent daily presence and code reviews over commit volume.\n"""
        elif m.get("cadence_status") == "Daily Driver":
            callout = f"""> ⚡ **Cadence Benchmark**: Daily engineering driver showing consistent presence (**{c['pct']:.0f}% of tenure days**) with an active **{c['longest_streak']}-day** streak and thorough code reviews.\n"""
        else:
            callout = ""

        cards.append(f"""
### #{m['rank']:02d} · {display_name} ([@{m['login']}]({m['html_url']})) · {m.get('tier_badge', '')} {m.get('cadence_status', '')}

<img src="{m['avatar_url']}" width="40" height="40" style="border-radius:50%; vertical-align:middle;" /> **{display_name}** (`@{m['login']}`) — *{m.get('cadence_desc', '')}*

{callout}
| Engineering Signal | Verified Output |
| :--- | :--- |
| 📅 **Daily Cadence** | **{c['pct']:.0f}%** active ({c['active_days']} of {c['total_days']} days since `{_fmt_date(m["created_at"])}`) |
| 🔥 **Streak Continuity** | **{c['longest_streak']} days** record unbroken streak · **{c['current_streak']} days** current active |
| 🔍 **Peer Code Reviews** | **{m['contributions']['reviews']}** reviews completed (enforcing code guidelines & peer quality) |
| 🚀 **Pull Requests** | **{m['contributions']['pull_requests']}** delivered across **{c['repos_breadth']}** org repositories |
| 📦 **Active Codebases** | {top_repos} |

<div align="center">
  <img src="https://cdn.jsdelivr.net/gh/{org_name}/{repo_name}@main/assets/graphs/{m['login']}.svg" width="100%" alt="{m['login']} activity calendar" />
</div>

---
""")
    roster_md = "\n".join(cards)
    remaining = data["org"]["member_count"] - len(members)
    if remaining > 0:
        roster_md += f"\n\n> View all {data['org']['member_count']} engineers on the [live interactive dashboard]({{dashboard_url}}).\n"
    return roster_md


def update_readme(content, data, *, org_name, repo_name, dashboard_url, roster_cap):
    content = _replace_marker(content, "STATS_BADGES", render_badges(data, org_name))
    content = _replace_marker(content, "SOLUTIONS", render_solutions(data, REPO_DISPLAY_NAMES, REPO_DESCRIPTIONS))

    leaderboard_block = f"""
<div align="center">

<img src="https://cdn.jsdelivr.net/gh/{org_name}/{repo_name}@main/assets/leaderboard_card.svg" alt="Engineering discipline and cadence overview" width="100%" />

</div>

{render_leaderboard(data, org_name, repo_name, dashboard_url)}

> **Discipline & Cadence Policy**: Standings are determined strictly by **daily consistency** (showing up on working days), **streak continuity**, **peer code reviews**, and **structured PR delivery**. Raw commit counts carry **zero ranking weight** to prevent bulk-commit gaming.
"""
    content = _replace_marker(content, "LEADERBOARD", leaderboard_block)

    roster_md = render_roster(data, org_name, repo_name, roster_cap).replace("{dashboard_url}", dashboard_url)
    content = _replace_marker(content, "ROSTER", roster_md)

    synced_str = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    content = _replace_marker(content, "TIMESTAMP", f" *Last synced: {synced_str}* ")

    return content


# --- Editorial copy (NOT telemetry) ------------------------------------------
# Hand-maintained product names/descriptions for repos, used only as a fallback
# when the repo has no `description` set on GitHub itself (GitHub's own field
# always wins when present). A repo missing from both dicts still gets a row
# in the Solutions table — it just gets an honest "no description set" note
# instead of an invented capability blurb. Update this by hand when a repo's
# purpose changes or a new one needs a friendlier public name.

REPO_DISPLAY_NAMES = {
    "forensics-due-diligence-system": "Forensics Due Diligence System",
    "Case-Management": "Enterprise Case Management",
    "mb-knowledge-vault-enterprise": "MB Knowledge Vault Enterprise",
    "tender-intelligence-platform": "Tender Intelligence Platform",
    "job-portal": "Job Portal",
    "mb-67-minutes": "MB 67 Minutes",
    ".github": "Organization Profile & Telemetry",
}

REPO_DESCRIPTIONS = {
    "forensics-due-diligence-system": "Multi-source background screening, corporate directorship graph analysis, sanctions & PEP verification, automated risk scoring.",
    "mb-knowledge-vault-enterprise": "Centralized institutional knowledge repository, precedent search engine, and automated compliance policy cross-referencing.",
    "tender-intelligence-platform": "Automated tender scraping, eligibility scoring, procurement risk detection, and deadline pipeline tracking.",
    "job-portal": "Recruitment platform supporting firm hiring pipelines and public-good community engagements.",
    "mb-67-minutes": "Community outreach and pro-bono engagement initiative supporting the firm's public-good programs.",
    ".github": "This repository — organization profile, health files, and the engineering telemetry pipeline that generates this page.",
}
