"""
Derivation layer: turns raw commit dates and contribution calendars into the
executive-facing picture — who works on what, how reliably, and where the firm
carries key-person risk.

Every metric in here is built from the DISTINCT ACTIVE DAY as its atom: a day on
which an engineer touched something counts exactly once, whether it carried one
commit or a thousand. Nothing here counts commits, pull requests, or reviews, so
there is no quantity anyone can inflate to move a number on the dashboard.
"""

from datetime import date, timedelta

CURRENT_WINDOW_DAYS = 14   # "currently working on it"
MAINTENANCE_WINDOW_DAYS = 60  # beyond this with no activity, a project reads as dormant


def is_bot(login):
    """GitHub suffixes every bot account with '[bot]'. Their commits must not set a
    project's liveness: this repo's own telemetry job pushes to it every single day, so
    counting bot pushes would make the dashboard's robot keep the dashboard's repo
    permanently 'Active' — a project that looks staffed because nobody is working on it."""
    return bool(login) and login.endswith("[bot]")


def _to_date(iso_day):
    return date.fromisoformat(iso_day)


# --- Projects: who works on what -------------------------------------------

def build_project_involvement(repo_histories, member_logins, today):
    """repo_histories: {repo_name: {"commits": [{"date","login"}], "truncated": bool}}

    Returns (by_member, by_project):
      by_member[login]  -> [{repo, active_days, first_active, last_active, days_since_last, is_current}]
      by_project[repo]  -> {engineers: [...], plus liveness/risk fields}

    Attribution follows GitHub's own commit->account linking. Commits whose author
    email isn't linked to any GitHub account, or is linked to an account outside the
    org, are kept separately as `outside_contributors` rather than silently dropped or
    quietly folded into a member's numbers.
    """
    members = set(member_logins)
    by_member = {login: {} for login in members}
    by_project = {}

    for repo_name, history in repo_histories.items():
        member_days = {}      # login -> set of dates
        outside_days = {}     # login or None -> set of dates
        all_days = set()

        automation_days = {}   # bot login -> set of dates, reported but never counted as work

        for commit in history.get("commits", []):
            day = commit["date"]
            login = commit.get("login")
            if is_bot(login):
                automation_days.setdefault(login, set()).add(day)
                continue
            all_days.add(day)
            if login in members:
                member_days.setdefault(login, set()).add(day)
            else:
                outside_days.setdefault(login, set()).add(day)

        engineers = []
        for login, days in member_days.items():
            record = _involvement_record(repo_name, days, today)
            engineers.append(record)
            by_member[login][repo_name] = record
        engineers.sort(key=lambda e: (-e["active_days"], e["repo"]))

        last_activity = max(all_days) if all_days else None
        days_since = (today - _to_date(last_activity)).days if last_activity else None
        active_engineers = [e for e in engineers if e["is_current"]]

        if last_activity is None:
            status = "No activity"
        elif days_since <= CURRENT_WINDOW_DAYS:
            status = "Active"
        elif days_since <= MAINTENANCE_WINDOW_DAYS:
            status = "Maintenance"
        else:
            status = "Dormant"

        by_project[repo_name] = {
            "engineers": engineers,
            "engineer_count": len(engineers),
            "active_engineer_count": len(active_engineers),
            "active_days_total": len(all_days),
            "last_activity": last_activity,
            "days_since_activity": days_since,
            "status": status,
            # Key-person risk: the project is live and exactly ONE engineer has been
            # near it recently. "Maintenance" means the last commit is already older
            # than the is_current window, so no engineer can be current on one — it
            # used to be included here, which flagged every maintenance project as
            # carried by one engineer while reporting zero active engineers.
            "key_person_risk": status == "Active" and len(active_engineers) == 1,
            # A live project nobody has touched recently is a different problem, and
            # saying "carried by one engineer" about it would be plainly false.
            "unstaffed": status in ("Active", "Maintenance") and not active_engineers,
            "sole_engineer": engineers[0]["login"] if len(engineers) == 1 else None,
            "outside_contributors": sorted(
                [
                    {"login": login or "unlinked commit author", "active_days": len(days)}
                    for login, days in outside_days.items()
                ],
                key=lambda o: -o["active_days"],
            ),
            "history_truncated": bool(history.get("truncated")),
            "automation": sorted(
                [{"login": login, "active_days": len(days)} for login, days in automation_days.items()],
                key=lambda a: -a["active_days"],
            ),
        }

    # Flatten each member's map into a list ordered by depth of involvement.
    by_member_lists = {}
    for login, repo_map in by_member.items():
        records = sorted(repo_map.values(), key=lambda r: (-r["active_days"], r["repo"]))
        by_member_lists[login] = records

    return by_member_lists, by_project


def _involvement_record(repo_name, days, today):
    ordered = sorted(days)
    last_active = ordered[-1]
    days_since = (today - _to_date(last_active)).days
    return {
        "repo": repo_name,
        "login": None,  # filled in by caller context where needed
        "active_days": len(days),
        "first_active": ordered[0],
        "last_active": last_active,
        "days_since_last": days_since,
        "is_current": days_since <= CURRENT_WINDOW_DAYS,
    }


def attach_logins(by_member_lists, by_project):
    """The per-project engineer records are shared objects; stamp the login on each so a
    project page can name its engineers without a reverse lookup."""
    for login, records in by_member_lists.items():
        for record in records:
            record["login"] = login
    for project in by_project.values():
        for engineer in project["engineers"]:
            if engineer["login"] is None:
                engineer["login"] = _find_login(by_member_lists, engineer)
        # Resolved only now that logins exist — sole_engineer is meaningless before this.
        project["sole_engineer"] = (
            project["engineers"][0]["login"] if len(project["engineers"]) == 1 else None
        )
        project["current_engineers"] = [e["login"] for e in project["engineers"] if e["is_current"]]
    return by_member_lists, by_project


def _find_login(by_member_lists, engineer):
    for login, records in by_member_lists.items():
        if any(r is engineer for r in records):
            return login
    return None


# --- Cadence shape: how someone actually works ------------------------------

def weekday_pattern(day_counts, today):
    """For each weekday (Sun=0 .. Sat=6), the share of those weekdays the engineer was
    active. Shows an executive whether someone keeps a steady working week, or is a
    weekend/irregular worker, without exposing any volume."""
    totals = [0] * 7
    actives = [0] * 7
    for iso_day, count in day_counts.items():
        d = _to_date(iso_day)
        if d > today:
            continue
        idx = (d.weekday() + 1) % 7
        totals[idx] += 1
        if count > 0:
            actives[idx] += 1
    return [
        {
            "weekday": i,
            "active_days": actives[i],
            "total_days": totals[i],
            "pct": round(actives[i] / totals[i] * 100, 1) if totals[i] else 0.0,
        }
        for i in range(7)
    ]


MIN_TREND_WEEKS = 4  # below this there is no "before" to compare a "now" against


def cadence_trend(day_counts, today, weeks=12, start_date=None):
    """Active days per week over the recent past, plus a direction. Answers the question
    an executive actually asks about a person: is this getting better or worse?

    Weeks that end before `start_date` are dropped rather than recorded as zero. Without
    that clamp a four-week-old joiner is charted against eight weeks when they did not
    work here, the empty bars read as months of doing nothing, and the zero baseline they
    create biases the direction toward "Improving" for the simple reason that the person
    did not exist in the earlier window."""
    series = []
    for w in range(weeks - 1, -1, -1):
        week_end = today - timedelta(days=7 * w)
        week_start = week_end - timedelta(days=6)
        if start_date is not None and week_end < start_date:
            continue
        active = sum(
            1 for iso_day, count in day_counts.items()
            if count > 0 and week_start <= _to_date(iso_day) <= week_end
        )
        series.append({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "active_days": active,
        })

    if len(series) < MIN_TREND_WEEKS:
        return {
            "weeks": series,
            "recent_avg_active_days": None,
            "earlier_avg_active_days": None,
            "direction": "Not enough history",
            "weeks_observed": len(series),
        }

    half = max(1, len(series) // 2)
    recent = series[-half:]
    earlier = series[:-half] or recent
    recent_avg = sum(s["active_days"] for s in recent) / len(recent)
    earlier_avg = sum(s["active_days"] for s in earlier) / len(earlier)
    delta = recent_avg - earlier_avg

    if delta >= 0.75:
        direction = "Improving"
    elif delta <= -0.75:
        direction = "Declining"
    else:
        direction = "Steady"

    return {
        "weeks": series,
        "recent_avg_active_days": round(recent_avg, 1),
        "earlier_avg_active_days": round(earlier_avg, 1),
        "direction": direction,
        "weeks_observed": len(series),
    }


def presence_from_dates(active_dates, tenure_start, today, window_days=30):
    """Presence derived from a set of dates rather than a day->count calendar.

    Used for verified presence, where the input is the set of dates GitHub's servers
    stamped an action. The window is anchored on tenure, not on the first recorded
    action — otherwise someone whose first verified day was yesterday would score 100%.
    """
    dates = {d if isinstance(d, str) else d.isoformat() for d in active_dates}
    window = min(window_days, (today - tenure_start).days + 1)
    window = max(window, 0)
    window_start = today - timedelta(days=window - 1) if window else today
    in_window = sum(1 for d in dates if window and window_start <= _to_date(d) <= today)

    ordered = sorted(_to_date(d) for d in dates)
    longest = current = 0
    run = 0
    previous = None
    for d in ordered:
        run = run + 1 if (previous is not None and (d - previous).days == 1) else 1
        longest = max(longest, run)
        previous = d
    # A current streak only counts if it reaches today or yesterday — otherwise a run
    # that ended weeks ago would read as if the person were still going.
    if ordered:
        last = ordered[-1]
        if (today - last).days <= 1:
            current = 1
            cursor = last
            for d in reversed(ordered[:-1]):
                if (cursor - d).days == 1:
                    current += 1
                    cursor = d
                else:
                    break

    last_date = ordered[-1].isoformat() if ordered else None
    return {
        "window_days": window,
        "active_days": in_window,
        "pct": round(in_window / window * 100, 1) if window else 0.0,
        "total_days": len(dates),
        "longest_streak": longest,
        "current_streak": current,
        "last_date": last_date,
        "days_since_last": (today - ordered[-1]).days if ordered else None,
    }


def recent_active_ratio(day_counts, today, window_days=30):
    """% of the last `window_days` days with activity (or the engineer's whole tenure if
    they're newer than the window). The headline reliability number."""
    if not day_counts:
        return {"window_days": 0, "active_days": 0, "pct": 0.0}
    earliest = _to_date(min(day_counts.keys()))
    window = min(window_days, (today - earliest).days + 1)
    if window <= 0:
        return {"window_days": 0, "active_days": 0, "pct": 0.0}
    window_start = today - timedelta(days=window - 1)
    active = sum(
        1 for iso_day, count in day_counts.items()
        if count > 0 and window_start <= _to_date(iso_day) <= today
    )
    return {
        "window_days": window,
        "active_days": active,
        "pct": round(active / window * 100, 1),
    }
