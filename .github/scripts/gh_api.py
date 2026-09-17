"""
GitHub API access layer for the Motsoeneng Bill Tech telemetry engine.

Everything here talks to the real GitHub GraphQL API — there is no cached/fake
fallback anywhere in this module. A call either returns real data or raises.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "Motsoeneng-Bill-Tech-Leaderboard-Bot"


class GraphQLError(RuntimeError):
    """A definitive API failure (bad auth, bad scope, malformed query, exhausted retries).

    Never retried past its budget and never papered over with synthetic data — the caller
    is expected to abort the whole run rather than publish a partial/guessed dataset.
    """


class DataIntegrityError(RuntimeError):
    """The API call itself succeeded, but the result is structurally incomplete
    (e.g. an org with zero members, or a discovered member missing from a later step).
    """


def get_token():
    """ORG_LEADERBOARD_TOKEN (needs read:org + repo) > GITHUB_TOKEN > local `gh auth token`."""
    token = os.environ.get("ORG_LEADERBOARD_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip().strip("\ufeff").strip()
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().strip("\ufeff").strip()
    except Exception:
        pass
    return None


def gh_graphql(query, token, retries=2):
    """POST a GraphQL query and return its `data` object.

    A GraphQL `errors` payload or an HTTP 401/403 raises immediately — those mean the
    token/query is wrong, not that the network is flaky, so retrying would just delay
    an inevitable failure. Only transport-level failures (timeouts, 5xx) are retried.
    """
    if not token:
        raise GraphQLError(
            "No GitHub token available. Set ORG_LEADERBOARD_TOKEN (or GITHUB_TOKEN), "
            "or run `gh auth login` locally."
        )

    clean_token = token.strip().strip("\ufeff").strip()
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {clean_token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )

    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            if e.code in (401, 403):
                raise GraphQLError(
                    f"GitHub API auth error {e.code}: {raw[:500]} "
                    "(token needs read:org + repo scopes)"
                ) from e
            if e.code >= 500 and attempt < retries:
                attempt += 1
                time.sleep(1.5 * attempt)
                continue
            raise GraphQLError(f"GitHub API HTTP error {e.code}: {raw[:500]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                attempt += 1
                time.sleep(1.5 * attempt)
                continue
            raise GraphQLError(f"Network error calling GitHub API after {retries} retries: {e}") from e

    if payload.get("errors"):
        raise GraphQLError(f"GraphQL errors: {json.dumps(payload['errors'])[:800]}")
    if "data" not in payload:
        raise GraphQLError(f"Malformed GraphQL response (no data/errors key): {json.dumps(payload)[:500]}")
    return payload["data"]


def get_rate_limit(token):
    """Best-effort — never fatal, since it's only used for the meta.rate_limit telemetry field."""
    try:
        data = gh_graphql("query { rateLimit { limit cost remaining resetAt } }", token)
        return data.get("rateLimit") or {}
    except GraphQLError:
        return {}


def discover_org_members(org, token):
    """GraphQL organization.membersWithRole, paginated. This — not a hardcoded list — is the
    org roster. Anyone added or removed from the org shows up automatically on the next run."""
    members = []
    after = "null"
    while True:
        query = f"""
        query {{
          organization(login: "{_esc(org)}") {{
            membersWithRole(first: 100, after: {after}) {{
              edges {{
                role
                node {{ id login name createdAt bio company location websiteUrl avatarUrl }}
              }}
              pageInfo {{ hasNextPage endCursor }}
            }}
          }}
        }}"""
        data = gh_graphql(query, token)
        org_data = data.get("organization")
        if org_data is None:
            raise GraphQLError(f"Organization '{org}' not found or not visible to this token.")
        conn = org_data["membersWithRole"]
        for edge in conn["edges"]:
            node = edge["node"]
            members.append({
                "id": node["id"],
                "login": node["login"],
                "name": node.get("name"),
                "created_at": node["createdAt"],
                "bio": node.get("bio"),
                "company": node.get("company"),
                "location": node.get("location"),
                "website_url": node.get("websiteUrl"),
                "avatar_url": node.get("avatarUrl") or f"https://github.com/{node['login']}.png",
                "org_role": edge["role"],
            })
        page = conn["pageInfo"]
        if not page["hasNextPage"]:
            break
        after = json.dumps(page["endCursor"])

    if not members:
        raise DataIntegrityError(f"Organization '{org}' returned zero members — refusing to publish an empty roster.")
    return members


def discover_org_repos(org, token):
    """GraphQL organization.repositories, paginated. This is what makes every real repo
    (private ones included) show up automatically — no repo can be silently forgotten."""
    repos = []
    after = "null"
    while True:
        query = f"""
        query {{
          organization(login: "{_esc(org)}") {{
            repositories(first: 100, after: {after}, isFork: false) {{
              nodes {{
                name
                description
                url
                isPrivate
                isArchived
                isEmpty
                primaryLanguage {{ name }}
                defaultBranchRef {{ name }}
              }}
              pageInfo {{ hasNextPage endCursor }}
            }}
          }}
        }}"""
        data = gh_graphql(query, token)
        org_data = data.get("organization")
        if org_data is None:
            raise GraphQLError(f"Organization '{org}' not found or not visible to this token.")
        conn = org_data["repositories"]
        for node in conn["nodes"]:
            repos.append({
                "name": node["name"],
                "description": node.get("description"),
                "html_url": node["url"],
                "visibility": "PRIVATE" if node["isPrivate"] else "PUBLIC",
                "primary_language": (node.get("primaryLanguage") or {}).get("name"),
                "default_branch": (node.get("defaultBranchRef") or {}).get("name"),
                "is_empty": node["isEmpty"],
                "is_archived": node["isArchived"],
            })
        page = conn["pageInfo"]
        if not page["hasNextPage"]:
            break
        after = json.dumps(page["endCursor"])

    if not repos:
        raise DataIntegrityError(f"Organization '{org}' returned zero repositories — refusing to publish empty data.")
    return repos


def fetch_member_contributions(login, from_iso, to_iso, token):
    """Real contributionsCollection for one member over [from_iso, to_iso].

    GitHub caps each call's span at ~1 year, so the caller must pass an explicit window
    (e.g. account creation -> now) rather than relying on the ~365-day default, which
    would otherwise mostly show empty days from before the account even existed.
    """
    query = f"""
    query {{
      user(login: "{_esc(login)}") {{
        contributionsCollection(from: "{from_iso}", to: "{to_iso}") {{
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          restrictedContributionsCount
          contributionCalendar {{
            totalContributions
            weeks {{ contributionDays {{ contributionCount date weekday }} }}
          }}
        }}
      }}
    }}"""
    data = gh_graphql(query, token)
    user = data.get("user")
    if user is None:
        raise DataIntegrityError(f"User '{login}' not found via GraphQL (was a real org member moments ago).")
    return user["contributionsCollection"]


def fetch_repo_commit_history(org, repo, token, max_pages=40):
    """Walk one repo's default-branch history once, returning (date, login) pairs.

    This is deliberately date-based, not count-based: everything downstream is derived
    from DISTINCT ACTIVE DAYS, which a burst of commits on a single day cannot inflate.
    One paginated pass per repo is also far cheaper than a per-member-per-repo query
    (the whole org is ~27 pages, ~27 rate-limit points of a 5,000/hour budget).

    History comes back newest-first, so if a repo ever exceeds max_pages the oldest
    commits are the ones dropped — `truncated` is surfaced so the caller can disclose it
    rather than silently under-reporting someone's start date.
    """
    if repo.get("is_empty") or not repo.get("default_branch"):
        return {"commits": [], "total_count": 0, "truncated": False}

    commits = []
    total_count = 0
    after = "null"
    pages = 0
    truncated = False

    while True:
        query = f"""
        query {{
          repository(owner: "{_esc(org)}", name: "{_esc(repo['name'])}") {{
            defaultBranchRef {{
              target {{
                ... on Commit {{
                  history(first: 100, after: {after}) {{
                    totalCount
                    pageInfo {{ hasNextPage endCursor }}
                    nodes {{ committedDate author {{ user {{ login }} }} }}
                  }}
                }}
              }}
            }}
          }}
        }}"""
        data = gh_graphql(query, token)
        target = ((data.get("repository") or {}).get("defaultBranchRef") or {}).get("target") or {}
        hist = target.get("history")
        if not hist:
            break

        total_count = hist["totalCount"]
        for node in hist["nodes"]:
            user = (node.get("author") or {}).get("user") or {}
            commits.append({
                "date": node["committedDate"][:10],
                "login": user.get("login"),  # None when the commit email isn't linked to a GitHub account
            })

        pages += 1
        if not hist["pageInfo"]["hasNextPage"]:
            break
        if pages >= max_pages:
            truncated = True
            break
        after = json.dumps(hist["pageInfo"]["endCursor"])

    return {"commits": commits, "total_count": total_count, "truncated": truncated}


def _esc(value):
    """Defensive escaping for values interpolated into a GraphQL string literal.
    Org/repo/login names are already GitHub-restricted charsets, but this costs nothing."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
