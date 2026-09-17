(async function () {
  const viewRoot = document.getElementById('view-root');
  const searchInput = document.getElementById('global-search');
  const STALE_AFTER_MS = 36 * 60 * 60 * 1000; // refreshes daily at noon — 36h means the pipeline is stuck

  // Bumped whenever metrics.json changes shape. The daily job can publish new data to a
  // browser still holding a cached copy of this script; without this guard that combination
  // throws deep inside rendering and the page just dies silently.
  const EXPECTED_SCHEMA = 3;

  let DATA = null;

  function isStale(iso) {
    return Date.now() - new Date(iso).getTime() > STALE_AFTER_MS;
  }

  function syncBadgeHTML() {
    return `<span class="sync-badge__dot"></span>Updated ${Format.relativeTime(DATA.generated_at)}`;
  }

  function attentionPanel() {
    const s = DATA.org.summary;
    const atRisk = DATA.projects.filter((p) => p.key_person_risk);
    const unstaffed = DATA.projects.filter((p) => p.unstaffed);
    const dormant = DATA.projects.filter((p) => p.status === 'Dormant' || p.status === 'No activity');
    const slowing = DATA.members.filter((m) => m.engagement_level !== 'active');

    if (!atRisk.length && !unstaffed.length && !dormant.length && !slowing.length) {
      return `<section class="panel panel--calm">
          <h3 class="panel__title">Nothing needs attention</h3>
          <p class="panel__hint">Every project has more than one recent contributor, none have gone quiet, and no engineer has dropped off.</p>
        </section>`;
    }

    const block = (title, hint, items) => items.length ? `
        <div class="attention__group">
          <div class="attention__heading">${title} <span class="attention__count">${items.length}</span></div>
          <p class="attention__hint">${hint}</p>
          <div class="attention__items">${items.join('')}</div>
        </div>` : '';

    return `<section class="panel panel--attention">
        <h3 class="panel__title">Needs attention</h3>
        ${block(
          'Carried by one engineer',
          'Live work that would stall if that person were unavailable.',
          atRisk.map((p) => `<a class="attention__item" href="./#/project/${encodeURIComponent(p.name)}">
              <span class="attention__item-name">${Format.escapeHtml(p.display_name)}</span>
              <span class="attention__item-meta">${p.current_engineers.map(Format.escapeHtml).join(', ') || 'unstaffed'}</span>
            </a>`)
        )}
        ${block(
          'Live work with nobody on it',
          'These are not finished, but no engineer has touched them inside the current window.',
          unstaffed.map((p) => `<a class="attention__item" href="./#/project/${encodeURIComponent(p.name)}">
              <span class="attention__item-name">${Format.escapeHtml(p.display_name)}</span>
              <span class="attention__item-meta">${p.days_since_activity !== null ? `quiet ${p.days_since_activity} days` : 'never started'}</span>
            </a>`)
        )}
        ${block(
          'Gone quiet',
          'No work has landed on these recently.',
          dormant.map((p) => `<a class="attention__item" href="./#/project/${encodeURIComponent(p.name)}">
              <span class="attention__item-name">${Format.escapeHtml(p.display_name)}</span>
              <span class="attention__item-meta">${p.days_since_activity !== null ? `${p.days_since_activity} days` : 'never'}</span>
            </a>`)
        )}
        ${block(
          'Engineers slowing down',
          'No commits recorded from them recently. Check for leave before reading anything into it.',
          slowing.map((m) => `<a class="attention__item" href="./#/member/${encodeURIComponent(m.login)}">
              <span class="attention__item-name">${Format.escapeHtml(m.name || m.login)}</span>
              <span class="attention__item-meta">${Format.escapeHtml(m.engagement_status)}</span>
            </a>`)
        )}
      </section>`;
  }

  let query = '';

  function filterProjects(list) {
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((p) => p.display_name.toLowerCase().includes(q)
      || p.name.toLowerCase().includes(q)
      || (p.primary_language || '').toLowerCase().includes(q));
  }

  function projectStatusClass(status) {
    if (status === 'Active') return 'status--active';
    if (status === 'Maintenance') return 'status--slowing';
    return 'status--dormant';
  }

  function projectGrid(list) {
    if (!list.length) return '<div class="empty-note">No projects match your search.</div>';
    return `<div class="pcard-grid">${list.map((p) => {
      // Maintenance is live work, just not this fortnight. Dimming it like a finished
      // project contradicted its own amber "Maintenance" chip on the same card.
      const cls = (p.status === 'Active' || p.status === 'Maintenance') ? 'pcard--current' : 'pcard--past';
      return `<a class="pcard ${cls}" href="./#/project/${encodeURIComponent(p.name)}">
          <div class="pcard__head">
            <div class="pcard__name">${Format.escapeHtml(p.display_name)}</div>
            ${p.primary_language ? `<span class="pcard__lang">${Format.escapeHtml(p.primary_language)}</span>` : ''}
          </div>
          <div class="pcard__days"><strong>${p.active_engineer_count}</strong> engineer${p.active_engineer_count === 1 ? '' : 's'} active
            <span class="pcard__of">of ${p.engineer_count}</span></div>
          <div class="pcard__span">${p.last_activity ? `Last work ${p.days_since_activity === 0 ? 'today' : `${p.days_since_activity}d ago`}` : 'No commits yet'}</div>
          <div class="pcard__foot">
            <span class="status-chip ${projectStatusClass(p.status)}">${Format.escapeHtml(p.status)}</span>
            ${p.key_person_risk ? '<span class="pcard__flag">Key-person risk</span>' : ''}
            ${p.unstaffed ? '<span class="pcard__flag">Nobody on it</span>' : ''}
          </div>
        </a>`;
    }).join('')}</div>`;
  }

  // Exposed on window because the member and project pages carry the same caveats.
  // Leaving them on the overview alone meant the README's "View full profile" deep
  // links dropped a partner straight onto a page that scores a named individual, with
  // the "this is not a performance rating" line sitting on a page they never opened.
  function disclosures() {
    const warnings = (DATA.meta.warnings || []).length
      ? `<div class="disclosure-warnings">
           <strong>Gaps in this run</strong>
           <ul>${DATA.meta.warnings.map((w) => `<li>${Format.escapeHtml(w)}</li>`).join('')}</ul>
         </div>`
      : '';
    return `<section class="panel panel--quiet">
        <h3 class="panel__title">How to read this page</h3>
        <ul class="disclosure-list">
          ${DATA.meta.disclosures.map((d) => `<li>${Format.escapeHtml(d)}</li>`).join('')}
        </ul>
        ${warnings}
      </section>`;
  }
  window.Disclosures = { html: disclosures };

  function overviewTemplate() {
    const org = DATA.org;
    const s = org.summary;
    return `
      <section class="hero view-enter">
        <div class="hero__top">
          <div>
            <h1 class="hero__title">Engineering Division</h1>
            <p class="hero__subtitle">${Format.escapeHtml(org.name)} — who is working on what, how reliably, and where the firm is exposed.</p>
          </div>
          <div class="sync-badge ${isStale(DATA.generated_at) ? 'is-stale' : ''}">${syncBadgeHTML()}</div>
        </div>

        <div class="stat-grid">
          <div class="stat-tile">
            <div class="stat-tile__label">Verified presence</div>
            <div class="stat-tile__value stat-tile__value--accent">${s.avg_reliability_pct.toFixed(0)}%</div>
            <div class="stat-tile__sub">average share of the last ${s.reliability_window_days} days with server-stamped evidence</div>
          </div>
          <div class="stat-tile">
            <div class="stat-tile__label">Active this week</div>
            <div class="stat-tile__value">${s.engineers_active_this_week}<span class="stat-tile__hint">of ${org.member_count}</span></div>
            <div class="stat-tile__sub">by commit activity${s.engineers_without_recent_evidence ? ` · ${s.engineers_without_recent_evidence} without recent verified evidence` : ''}</div>
          </div>
          <div class="stat-tile">
            <div class="stat-tile__label">Live projects</div>
            <div class="stat-tile__value">${s.projects_active}<span class="stat-tile__hint">of ${org.live_repo_count}</span></div>
            <div class="stat-tile__sub">${s.projects_dormant} with no recent work${s.projects_archived ? ` · ${s.projects_archived} archived` : ''}</div>
          </div>
          <div class="stat-tile ${s.projects_at_key_person_risk ? 'stat-tile--warn' : ''}">
            <div class="stat-tile__label">Key-person risk</div>
            <div class="stat-tile__value">${s.projects_at_key_person_risk}</div>
            <div class="stat-tile__sub">projects carried by one engineer</div>
          </div>
        </div>
      </section>

      ${attentionPanel()}

      <div class="section-head">
        <h2>Engineers</h2>
        <span class="section-head__hint">Ranked on verified presence — evidence GitHub timestamped, which no one can backdate</span>
      </div>
      <div class="table-scroll" id="leaderboard-table"></div>
      <div class="leaderboard-cards" id="leaderboard-cards"></div>

      <div class="section-head">
        <h2>Projects</h2>
        <span class="section-head__hint">${org.live_repo_count} live, discovered automatically${org.repo_count > org.live_repo_count ? ` · ${org.repo_count - org.live_repo_count} archived` : ''}</span>
      </div>
      <div id="project-grid">${projectGrid(filterProjects(DATA.projects))}</div>

      <section class="panel">
        <h3 class="panel__title">Firm-wide activity since ${Format.date(org.calendar.from)}</h3>
        <div id="org-calendar-slot"></div>
      </section>

      ${disclosures()}
    `;
  }

  function showOverview() {
    viewRoot.innerHTML = overviewTemplate();
    Calendar.render(document.getElementById('org-calendar-slot'), DATA.org.calendar, { mode: 'full', legend: true });
    Leaderboard.render(
      document.getElementById('leaderboard-table'),
      document.getElementById('leaderboard-cards'),
      DATA.members,
      { onSelect: (login) => { window.location.hash = `#/member/${login}`; } }
    );
    document.title = `${DATA.org.name} — Engineering Division`;
  }

  function notFound(what, value) {
    viewRoot.innerHTML = `<div class="error-state view-enter">
        <h2>${what} not found</h2>
        <p>${Format.escapeHtml(value)} isn't in the current dataset.</p>
        <a class="btn btn--primary" href="./#/">Back to overview</a>
      </div>`;
  }

  function showMember(login) {
    const member = DATA.members.find((m) => m.login.toLowerCase() === login.toLowerCase());
    if (!member) return notFound('Engineer', login);
    viewRoot.innerHTML = '<div class="view-enter" id="detail-root"></div>';
    MemberDetail.render(document.getElementById('detail-root'), member, DATA);
  }

  function showProject(name) {
    const project = DATA.projects.find((p) => p.name.toLowerCase() === name.toLowerCase());
    if (!project) return notFound('Project', name);
    viewRoot.innerHTML = '<div class="view-enter" id="detail-root"></div>';
    ProjectDetail.render(document.getElementById('detail-root'), project, DATA);
  }

  try {
    DATA = await DataStore.load();
  } catch (err) {
    viewRoot.innerHTML = `<div class="error-state">
        <h2>Couldn't load the latest data</h2>
        <p>${Format.escapeHtml(err.message)}</p>
      </div>`;
    return;
  }

  if (DATA.schema_version !== EXPECTED_SCHEMA) {
    viewRoot.innerHTML = `<div class="error-state">
        <h2>This page is out of date</h2>
        <p>The data was published in a newer format than this page understands. Reload to pick up the current version.</p>
        <button class="btn btn--primary" onclick="location.reload(true)">Reload</button>
      </div>`;
    return;
  }

  Router.init({ overview: showOverview, member: showMember, project: showProject });

  searchInput.addEventListener('input', (e) => {
    query = e.target.value;
    Leaderboard.setQuery(query);
    // The placeholder promises project search too; without this the grid sat there
    // unfiltered under a "No engineers match your search" note, reading as broken.
    const grid = document.getElementById('project-grid');
    if (grid) grid.innerHTML = projectGrid(filterProjects(DATA.projects));
    if (window.location.hash && window.location.hash !== '#/') {
      window.location.hash = '#/';
    }
  });

  setInterval(() => {
    const badge = document.querySelector('.sync-badge');
    if (badge) {
      badge.classList.toggle('is-stale', isStale(DATA.generated_at));
      badge.innerHTML = syncBadgeHTML();
    }
  }, 60000);
})();
