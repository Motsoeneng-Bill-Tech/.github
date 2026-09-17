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

    c = member["consistency"]
    rel = member["reliability"]
    band = member["cadence_band"]
    projects = member["current_project_count"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="10" fill="{SURFACE}" stroke="{BORDER}" stroke-width="1" />
  <text x="{start_x}" y="18" font-family="{FONT_STACK}" font-size="12" font-weight="700" fill="{TEXT_PRIMARY}">@{member['login']} · <tspan fill="{ACCENT}">{band}</tspan></text>
  <text x="{start_x}" y="32" font-family="{FONT_STACK}" font-size="10"><tspan font-weight="700" fill="{TEXT_PRIMARY}">{rel['pct']:.0f}% of last {rel['window_days']} days</tspan><tspan fill="{TEXT_TERTIARY}"> · {c['current_streak']}d streak · {projects} active project{'' if projects == 1 else 's'}</tspan></text>
  {months_svg}
  <g>{''.join(rects)}</g>
</svg>"""


def render_overview_card_svg(data, max_rows=8):
    """Org-wide ranked bar chart. Bars are reliability — the share of recent days each
    engineer was present — never volume, so no single day can lengthen anyone's bar."""
    width = 860
    org = data["org"]
    summary = org["summary"]
    members = data["members"][:max_rows]
    row_h = 36
    header_h = 96
    height = header_h + len(members) * row_h + 24

    stats = [
        ("ENGINEERS", str(org["member_count"])),
        ("ACTIVE THIS WEEK", str(summary["engineers_active_this_week"])),
        ("TEAM RELIABILITY", f'{summary["avg_reliability_pct"]:.0f}%'),
        ("PROJECTS AT RISK", str(summary["projects_at_key_person_risk"])),
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
    bar_max_w = width - bar_x - 180
    rows_svg = []
    for i, m in enumerate(members):
        y = header_h + i * row_h
        rel = m["reliability"]
        bar_w = max(3, (rel["pct"] / 100) * bar_max_w)
        label_meta = f'{m["current_project_count"]} active project{"" if m["current_project_count"] == 1 else "s"} · {m["consistency"]["current_streak"]}d streak'
        rows_svg.append(f'''
  <text x="32" y="{y + 22}" font-family="{FONT_STACK}" font-size="12" font-weight="700" fill="{TEXT_TERTIARY}">{i + 1:02d}</text>
  <text x="60" y="{y + 22}" font-family="{FONT_STACK}" font-size="12" font-weight="600" fill="{TEXT_PRIMARY}">@{m['login']}</text>
  <rect x="{bar_x}" y="{y + 9}" width="{bar_max_w}" height="8" rx="4" fill="{BORDER}" />
  <rect x="{bar_x}" y="{y + 9}" width="{bar_w:.1f}" height="8" rx="4" fill="{ACCENT}" />
  <text x="{bar_x + bar_max_w + 10}" y="{y + 17}" font-family="{FONT_STACK}" font-size="11" font-weight="700" fill="{ACCENT}">{rel['pct']:.0f}% · {m['cadence_band']}</text>
  <text x="{bar_x + bar_max_w + 10}" y="{y + 29}" font-family="{FONT_STACK}" font-size="9" fill="{TEXT_TERTIARY}">{label_meta}</text>''')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="14" fill="{BG}" stroke="{BORDER}" stroke-width="1" />
  <text x="32" y="32" font-family="{FONT_STACK}" font-size="11" font-weight="700" letter-spacing="1.5" fill="{ACCENT}">{org['name'].upper()} · ENGINEERING DIVISION OVERVIEW</text>
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
    s = org["summary"]
    return "\n".join([
        f'[![Team Reliability](https://img.shields.io/badge/Team_Reliability-{s["avg_reliability_pct"]:.0f}%25-c9a961?style=for-the-badge&logo=clockify&logoColor=white)](https://github.com/{org_name})',
        f'[![Active This Week](https://img.shields.io/badge/Active_This_Week-{s["engineers_active_this_week"]}_of_{org["member_count"]}-34d399?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/orgs/{org_name}/people)',
        f'[![Projects](https://img.shields.io/badge/Live_Projects-{s["projects_active"]}_of_{org["repo_count"]}-8a7130?style=for-the-badge&logo=git&logoColor=white)](https://github.com/{org_name})',
        f'[![Key Person Risk](https://img.shields.io/badge/Key_Person_Risk-{s["projects_at_key_person_risk"]}_projects-64748b?style=for-the-badge&logo=shield&logoColor=white)](https://github.com/{org_name})',
        '[![Compliance](https://img.shields.io/badge/Security-POPIA_Compliant-1e2430?style=for-the-badge&logo=shield&logoColor=white)](https://mb.co.za/)',
    ])


def render_solutions(data, display_names, descriptions):
    """Every real project, with its live staffing and health — the portfolio view an
    executive reads first. Driven by live discovery, so a new project cannot be forgotten."""
    rows = ["| Platform | Status | Engineers | Last Activity | Description |",
            "| :--- | :---: | :---: | :---: | :--- |"]
    for p in data["projects"]:
        desc = p["description"] or "_No description set yet._"
        staffing = f'{p["active_engineer_count"]} active / {p["engineer_count"]} total'
        if p["key_person_risk"]:
            staffing += " ⚠️"
        last = f'{p["days_since_activity"]}d ago' if p["days_since_activity"] is not None else "—"
        lang = f' · `{p["primary_language"]}`' if p["primary_language"] else ""
        rows.append(f'| **{p["display_name"]}**{lang} | {p["status"]} | {staffing} | {last} | {desc} |')
    rows.append("")
    rows.append("> ⚠️ marks a project currently carried by a single engineer — a continuity risk worth staffing against.")
    return "\n".join(rows)


def render_leaderboard(data, org_name, repo_name, dashboard_url):
    """No column here is a count of anything. Reliability, streaks and project counts are
    all day-based, so the table cannot be climbed by pushing harder on a single day."""
    window = data["org"]["summary"]["reliability_window_days"]
    rows = [
        f"| # | Engineer | Cadence | Reliability (last {window}d) | Current Streak | Projects | Status | Activity |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for m in data["members"]:
        avatar = f'<img src="{m["avatar_url"]}" width="30" height="30" style="border-radius:50%; vertical-align:middle;" />'
        activity_img = (
            f'<img src="https://cdn.jsdelivr.net/gh/{org_name}/{repo_name}@main/assets/graphs/{m["login"]}.svg?v=3" '
            f'width="220" height="64" alt="{m["login"]} activity calendar" />'
        )
        profile_link = f'[↗ profile]({dashboard_url}#/member/{m["login"]})'
        c = m["consistency"]
        rel = m["reliability"]
        projects = f'**{m["current_project_count"]}** active <br/>`{m["project_count"]} total`'
        rows.append(
            f'| **{m["rank"]:02d}** | [{avatar} **@{m["login"]}**]({m["html_url"]}) <br/>{profile_link} '
            f'| **{m["cadence_band"]}** '
            f'| **{rel["pct"]:.0f}%** <br/>`{rel["active_days"]}/{rel["window_days"]} days` '
            f'| **{c["current_streak"]}d** <br/>`{c["longest_streak"]}d record` '
            f'| {projects} '
            f'| {m["engagement_status"]} '
            f'| {activity_img} |'
        )
    return "\n".join(rows)


def render_roster(data, org_name, repo_name, cap):
    members = data["members"][:cap]
    cards = []
    for m in members:
        display_name = m["name"] or m["login"]
        c = m["consistency"]
        rel = m["reliability"]
        trend = m["trend"]

        if m["projects"]:
            project_lines = []
            for p in m["projects"]:
                marker = "▸" if p["is_current"] else "·"
                position = "Active now" if p["is_current"] else f'Last active {p["days_since_last"]}d ago'
                if p["is_only_active_engineer"]:
                    position += " · **sole active engineer**"
                span = f'{_fmt_date(p["first_active"])} → {_fmt_date(p["last_active"])}'
                project_lines.append(
                    f'| {marker} | **{p["display_name"]}** | {p["active_days"]} | `{span}` | {position} |'
                )
            projects_block = "\n".join([
                "| | Project | Days engaged | Span | Position |",
                "| :---: | :--- | :---: | :---: | :--- |",
                *project_lines,
            ])
        else:
            projects_block = "_No merged work on firm projects yet._"

        languages = ", ".join(f"`{lang}`" for lang in m["languages"]) or "—"
        risk_note = ""
        if m["carries_key_person_risk_for"]:
            carried = ", ".join(f"**{name}**" for name in m["carries_key_person_risk_for"])
            risk_note = f"\n> **Continuity risk:** currently the only active engineer on {carried}. Worth a second pair of hands.\n"

        cards.append(f"""
### #{m['rank']:02d} · {display_name} — {m['cadence_band']}

<img src="{m['avatar_url']}" width="40" height="40" style="border-radius:50%; vertical-align:middle;" /> [`@{m['login']}`]({m['html_url']}) · joined {_fmt_date(m["created_at"])} · {m['engagement_status']}
{risk_note}
| | |
| :--- | :--- |
| **Reliability** | **{rel['pct']:.0f}%** of the last {rel['window_days']} days ({rel['active_days']} of {rel['window_days']}) |
| **Streak** | **{c['current_streak']} days** current · {c['longest_streak']} days best |
| **Trend** | {trend['direction']} — {trend['recent_avg_active_days']} active days/week recently vs {trend['earlier_avg_active_days']} before |
| **Projects** | **{m['current_project_count']}** active of {m['project_count']} worked on |
| **Technologies** | {languages} |

{projects_block}

<div align="center">
  <img src="https://cdn.jsdelivr.net/gh/{org_name}/{repo_name}@main/assets/graphs/{m['login']}.svg?v=3" width="100%" alt="{m['login']} activity calendar" />
</div>

[View full profile →]({{dashboard_url}}#/member/{m['login']})

---
""")
    roster_md = "\n".join(cards)
    remaining = data["org"]["member_count"] - len(members)
    if remaining > 0:
        roster_md += f"\n\n> View all {data['org']['member_count']} engineers on the [live executive dashboard]({{dashboard_url}}).\n"
    return roster_md


def update_readme(content, data, *, org_name, repo_name, dashboard_url, roster_cap):
    content = _replace_marker(content, "STATS_BADGES", render_badges(data, org_name))
    content = _replace_marker(content, "SOLUTIONS", render_solutions(data, REPO_DISPLAY_NAMES, REPO_DESCRIPTIONS))

    leaderboard_block = f"""
<div align="center">

<img src="https://cdn.jsdelivr.net/gh/{org_name}/{repo_name}@main/assets/leaderboard_card.svg?v=2" alt="Engineering discipline and cadence overview" width="100%" />

</div>

{render_leaderboard(data, org_name, repo_name, dashboard_url)}

> **How this is measured.** Standing is based on how regularly an engineer shows up — the share of recent days with recorded work, streak continuity, and how many projects they are currently carrying. A day counts once whether it held one commit or a thousand, so nothing here can be inflated by pushing harder on a single day. Commit, pull request and review counts are deliberately not published and carry no weight: counting output rewards volume, and volume is easy to manufacture.
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
