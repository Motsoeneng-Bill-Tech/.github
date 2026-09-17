# Motsoeneng Bill Tech · Organization Profile & Health Files

This repository (`Motsoeneng-Bill-Tech/.github`) hosts the public organization profile, health files, and the automated engineering telemetry pipeline for **Motsoeneng Bill Tech**.

### 📌 Organization Profile README
The public-facing profile displayed on the [Motsoeneng Bill Tech GitHub Organization](https://github.com/Motsoeneng-Bill-Tech) is located at:
👉 **[`profile/README.md`](profile/README.md)**

### 📊 Executive dashboard
The interactive view — every engineer, every project, continuity risk — is published from [`docs/`](docs/):
👉 **<https://motsoeneng-bill-tech.github.io/.github/>**

---

### ⚙️ Engineering cadence telemetry

This pipeline measures **how reliably engineers show up**, never how much they push.

Nothing here is a count of commits, pull requests or reviews. Every figure is built from the
**distinct active day** — a day counts once whether it carried one action or a thousand — and
standing is ranked on *verified presence*: dates GitHub's own servers stamped when a pull
request, review or issue arrived, which a contributor's machine cannot set. Commit dates are
reported alongside as *recorded activity* and are deliberately excluded from ranking, because
git lets any author date be supplied after the fact.

- **Workflow**: [`.github/workflows/update-readme.yml`](.github/workflows/update-readme.yml)
- **Orchestration**: [`.github/scripts/update_leaderboard.py`](.github/scripts/update_leaderboard.py)
- **GitHub API layer**: [`.github/scripts/gh_api.py`](.github/scripts/gh_api.py)
- **Derivation (projects, cadence, key-person risk)**: [`.github/scripts/analytics.py`](.github/scripts/analytics.py)
- **Rendering (SVG + README markers)**: [`.github/scripts/render.py`](.github/scripts/render.py)
- **Dashboard**: [`docs/`](docs/) — reads the single canonical dataset at [`docs/data/metrics.json`](docs/data/metrics.json)
- **Generated assets**: [`assets/graphs/`](assets/graphs/) and [`assets/leaderboard_card.svg`](assets/leaderboard_card.svg)

#### Schedule & triggers
- Runs once a day at **10:00 UTC — 12:00 SAST** (`0 10 * * *`). GitHub cron is always UTC; South Africa does not observe daylight saving, so this stays at local midday year-round.
- Also runs on pushes that touch the scripts, the workflow or the dashboard.
- Can be triggered at any time from the **Actions** tab via `workflow_dispatch`.

#### Failure behaviour
The run is fail-loud by design. If any API call needed for a complete dataset fails, the script
exits non-zero **before writing anything**, the commit step is skipped and the Pages deploy is
gated on it — so the last known-good data stays live and visibly timestamped rather than being
silently replaced with a guess. There is no cached fallback and no hardcoded roster anywhere in
this pipeline.

#### Requirements
`ORG_LEADERBOARD_TOKEN` must be set as a repository secret — a token with `read:org` (to list
organization members; a repo-scoped token structurally cannot do this) and `repo` (to read commit
history across private repositories). The default `GITHUB_TOKEN` cannot read org membership.
