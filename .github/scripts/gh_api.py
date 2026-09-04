"""
GitHub API access layer for the Motsoeneng Bill Tech telemetry engine.

Everything here talks to the real GitHub GraphQL API — there is no cached/fake
fallback anywhere in this module. A call either returns real data or raises.
"""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "Motsoeneng-Bill-Tech-Leaderboard-Bot"

_ALIAS_RE = re.compile(r"[^A-Za-z0-9_]")


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
        return token.strip()
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
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

    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
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


def _member_alias(login):
    """GraphQL field aliases must match [_A-Za-z][_0-9A-Za-z]* — logins like 'Akonisaho-MB'
    contain hyphens and aren't valid identifiers as-is."""
    return "m_" + _ALIAS_RE.sub("_", login)


def fetch_firm_commit_matrix(org, repos, members, token, chunk_size=6):
    """The core fix for this whole pipeline: real, live commit counts per member per repo,
    computed fresh every run — never a hardcoded/cached number.

    For each chunk of repos, builds ONE GraphQL query that aliases every repo and, inside
    each, aliases `history(author:{id})` for every member — the exact batched shape proven
    live against this org before writing this function. Uses each repo's actual discovered
    default branch (never hardcodes "main" — this org already has one repo on "dev").

    Returns {repo_name: {"total_commits": int, "by_login": {login: count}}}.
    Repos with no commits yet (isEmpty / no default branch) are recorded as zero without
    spending a query on them.
    """
    alias_to_login = {}
    for m in members:
        alias = _member_alias(m["login"])
        if alias in alias_to_login and alias_to_login[alias] != m["login"]:
            raise DataIntegrityError(
                f"GraphQL alias collision between logins {alias_to_login[alias]!r} and {m['login']!r}"
            )
        alias_to_login[alias] = m["login"]

    matrix = {}
    queryable = [r for r in repos if not r["is_empty"] and r["default_branch"]]
    queryable_names = {r["name"] for r in queryable}
    for r in repos:
        if r["name"] not in queryable_names:
            matrix[r["name"]] = {"total_commits": 0, "by_login": {}}

    for i in range(0, len(queryable), chunk_size):
        chunk = queryable[i:i + chunk_size]
        member_fields = "\n".join(
            f'{_member_alias(m["login"])}: history(author: {{ id: "{m["id"]}" }}) {{ totalCount }}'
            for m in members
        )
        parts = []
        for ridx, repo in enumerate(chunk):
            parts.append(f"""
  r{ridx}: repository(owner: "{_esc(org)}", name: "{_esc(repo['name'])}") {{
    defaultBranchRef {{
      target {{
        ... on Commit {{
          totalHistory: history {{ totalCount }}
          {member_fields}
        }}
      }}
    }}
  }}""")
        query = "query {" + "".join(parts) + "\n}"
        data = gh_graphql(query, token)
        for ridx, repo in enumerate(chunk):
            node = data.get(f"r{ridx}")
            target = ((node or {}).get("defaultBranchRef") or {}).get("target")
            if not target:
                matrix[repo["name"]] = {"total_commits": 0, "by_login": {}}
                continue
            by_login = {}
            for m in members:
                count = target.get(_member_alias(m["login"]), {}).get("totalCount", 0)
                if count:
                    by_login[m["login"]] = count
            matrix[repo["name"]] = {
                "total_commits": target["totalHistory"]["totalCount"],
                "by_login": by_login,
            }

    return matrix


def _esc(value):
    """Defensive escaping for values interpolated into a GraphQL string literal.
    Org/repo/login names are already GitHub-restricted charsets, but this costs nothing."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
