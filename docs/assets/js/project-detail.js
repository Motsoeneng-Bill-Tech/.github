/**
 * The per-project executive view: what it is, whether it is alive, who is carrying it,
 * and whether the firm would be exposed if that person stepped away.
 */
const ProjectDetail = (() => {
  function statusClass(status) {
    if (status === 'Active') return 'status--active';
    if (status === 'Maintenance') return 'status--slowing';
    return 'status--dormant';
  }

  function recentEngineerCount(project) {
    return project.engineers.filter((e) => e.days_since_last !== null && e.days_since_last <= 30).length;
  }

  function engineerRow(e, membersByLogin) {
    const m = membersByLogin[e.login];
    const avatar = m ? m.avatar_url : `https://github.com/${e.login}.png`;
    const name = m ? (m.name || m.login) : e.login;
    const cls = e.is_current ? 'status--active' : 'status--dormant';
    const position = `<span class="status-chip ${cls}">Last worked ${Format.dayAgo(e.days_since_last)}</span>`;
    return `<a class="erow" href="./#/member/${encodeURIComponent(e.login)}">
        <img src="${avatar}" alt="" width="34" height="34" loading="lazy" />
        <div class="erow__main">
          <div class="erow__name">${Format.escapeHtml(name)}</div>
          <div class="erow__meta">@${Format.escapeHtml(e.login)} &middot; ${e.active_days} day${e.active_days === 1 ? '' : 's'} engaged &middot; ${Format.date(e.first_active)} → ${Format.date(e.last_active)}</div>
        </div>
        ${position}
      </a>`;
  }

  function render(container, project, data) {
    const membersByLogin = {};
    data.members.forEach((m) => { membersByLogin[m.login] = m; });

    const riskBanner = project.key_person_risk ? `
      <div class="alert-banner alert-banner--warn">
        <strong>Key-person risk.</strong> This project is live but only
        ${project.current_engineers.length === 1
          ? `<strong>${Format.escapeHtml(project.current_engineers[0])}</strong> has worked on it recently.`
          : 'one engineer has worked on it recently.'}
        Consider pairing a second engineer onto it.
      </div>` : '';

    const unstaffedBanner = project.unstaffed ? `
      <div class="alert-banner alert-banner--warn">
        <strong>Nobody is on this.</strong> It is not finished, but no engineer has touched it
        ${project.days_since_activity !== null ? `for ${project.days_since_activity} days.` : 'at all yet.'}
        It needs an owner before it is treated as in flight.
      </div>` : '';

    const truncatedBanner = project.history_truncated ? `
      <div class="alert-banner">
        <strong>Partial history.</strong> This project has more commits than a single run can read,
        so the earliest dates below may be later than the truth. Figures for recent work are unaffected.
      </div>` : '';

    const dormantBanner = (project.status === 'Dormant' || project.status === 'No activity') ? `
      <div class="alert-banner">
        <strong>No recent activity.</strong> Nothing has landed on this project
        ${project.days_since_activity !== null ? `for ${project.days_since_activity} days.` : 'yet.'}
        If it is still expected to be in flight, it needs owners.
      </div>` : '';

    const outside = project.outside_contributors.length ? `
      <section class="panel">
        <h3 class="panel__title">Unmatched commit authors</h3>
        <p class="panel__hint">Work committed from an email address not linked to an organization member's GitHub account. Shown separately rather than credited to anyone.</p>
        <div class="tag-row">${project.outside_contributors.map((o) =>
          `<span class="repo-tag">${Format.escapeHtml(o.login)} · ${o.active_days}d</span>`).join('')}</div>
      </section>` : '';

    const automation = (project.automation || []).length ? `
      <section class="panel">
        <h3 class="panel__title">Automation</h3>
        <p class="panel__hint">Bot accounts that push to this project. Their activity is listed for completeness and is excluded from every figure above — a project kept moving by a robot is not staffed.</p>
        <div class="tag-row">${project.automation.map((a) =>
          `<span class="repo-tag">${Format.escapeHtml(a.login)} · ${a.active_days}d</span>`).join('')}</div>
      </section>` : '';

    container.innerHTML = `
      <a class="detail-back" href="./#/">&larr; Back to overview</a>

      <div class="detail-header detail-header--project">
        <div class="detail-header__main">
          <div class="detail-header__name">${Format.escapeHtml(project.display_name)}</div>
          <div class="detail-header__login">
            <a href="${project.html_url}" target="_blank" rel="noopener">${Format.escapeHtml(project.name)} ↗</a>
            &middot; ${project.visibility === 'PUBLIC' ? 'Public' : 'Private'}
            &middot; <span title="The main version of the project that this page measures">main version: ${Format.escapeHtml(project.default_branch || '—')}</span>
            ${project.primary_language ? `&middot; ${Format.escapeHtml(project.primary_language)}` : ''}
          </div>
          <div class="detail-header__badges">
            <span class="status-chip ${statusClass(project.status)}">${Format.escapeHtml(project.status)}</span>
            ${project.key_person_risk ? '<span class="tier-chip tier-chip--warn">Key-person risk</span>' : ''}
          </div>
          ${project.description ? `<p class="detail-header__desc">${Format.escapeHtml(project.description)}</p>` : ''}
        </div>
      </div>

      ${riskBanner}
      ${unstaffedBanner}
      ${truncatedBanner}
      ${dormantBanner}

      <div class="stat-grid">
        <div class="stat-tile">
          <div class="stat-tile__label">Engineers active</div>
          <div class="stat-tile__value stat-tile__value--accent">${project.active_engineer_count}</div>
          <div class="stat-tile__sub">${project.engineer_count} have worked on it</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Last activity</div>
          <div class="stat-tile__value stat-tile__value--sm">${project.last_activity ? Format.date(project.last_activity) : '—'}</div>
          <div class="stat-tile__sub">${project.days_since_activity !== null ? `${project.days_since_activity} days ago` : 'no commits yet'}</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Days worked on</div>
          <div class="stat-tile__value">${project.active_days_total}</div>
          <div class="stat-tile__sub">distinct days with work landed</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Engineers in last 30 days</div>
          <div class="stat-tile__value">${recentEngineerCount(project)}</div>
          <div class="stat-tile__sub">how wide the recent knowledge of this project is</div>
        </div>
      </div>

      <section class="panel">
        <h3 class="panel__title">Who works on this</h3>
        ${project.engineers.length
          ? `<div class="erow-list">${project.engineers.map((e) => engineerRow(e, membersByLogin)).join('')}</div>`
          : '<p class="panel__hint">No organization member has landed work here yet.</p>'}
      </section>

      ${outside}
      ${automation}

      ${window.Disclosures ? window.Disclosures.html() : ''}
    `;

    document.title = `${project.display_name} — ${data.org.name} Engineering`;
  }

  return { render };
})();
