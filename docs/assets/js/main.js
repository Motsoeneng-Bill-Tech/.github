(async function () {
  const viewRoot = document.getElementById('view-root');
  const searchInput = document.getElementById('global-search');
  const STALE_AFTER_MS = 24 * 60 * 60 * 1000; // data refreshes every 6h — 24h+ means the pipeline is stuck

  let DATA = null;

  function isStale(iso) {
    return Date.now() - new Date(iso).getTime() > STALE_AFTER_MS;
  }

  function syncBadgeHTML() {
    return `<span class="sync-badge__dot"></span>Synced ${Format.relativeTime(DATA.generated_at)}`;
  }

  function overviewTemplate() {
    const org = DATA.org;
    return `
      <section class="hero view-enter">
        <div class="hero__top">
          <div>
            <h1 class="hero__title">Engineering Dashboard</h1>
            <p class="hero__subtitle">Real, live GitHub contribution data for every ${Format.escapeHtml(org.name)} engineer.</p>
          </div>
          <div class="sync-badge ${isStale(DATA.generated_at) ? 'is-stale' : ''}">${syncBadgeHTML()}</div>
        </div>

        <div class="stat-grid">
          <div class="stat-tile"><div class="stat-tile__label">Total Contributions</div><div class="stat-tile__value">${Format.number(org.totals.total_contributions)}</div></div>
          <div class="stat-tile"><div class="stat-tile__label">Firm Commits</div><div class="stat-tile__value stat-tile__value--accent">${Format.number(org.totals.total_firm_commits)}</div></div>
          <div class="stat-tile"><div class="stat-tile__label">Engineers</div><div class="stat-tile__value">${org.member_count}</div></div>
          <div class="stat-tile"><div class="stat-tile__label">Repositories</div><div class="stat-tile__value">${org.repo_count}</div></div>
        </div>

        <div class="org-calendar-card">
          <div class="org-calendar-card__title">Firm-wide activity since ${Format.date(org.calendar.from)}</div>
          <div id="org-calendar-slot"></div>
        </div>
      </section>

      <div class="section-head">
        <h2>Engineering Leaderboard</h2>
        <span class="section-head__hint">Click any engineer for their full profile</span>
      </div>
      <div class="table-scroll" id="leaderboard-table"></div>
      <div class="leaderboard-cards" id="leaderboard-cards"></div>
    `;
  }

  function showOverview() {
    viewRoot.innerHTML = overviewTemplate();
    Calendar.render(document.getElementById('org-calendar-slot'), DATA.org.calendar, { mode: 'full', legend: false });
    Leaderboard.render(
      document.getElementById('leaderboard-table'),
      document.getElementById('leaderboard-cards'),
      DATA.members,
      { onSelect: (login) => { window.location.hash = `#/member/${login}`; } }
    );
  }

  function showMember(login) {
    const member = DATA.members.find((m) => m.login === login);
    if (!member) {
      viewRoot.innerHTML = `<div class="error-state view-enter">
        <h2>Engineer not found</h2>
        <p>@${Format.escapeHtml(login)} isn't in the current roster.</p>
        <a class="btn btn--primary" href="./#/">Back to leaderboard</a>
      </div>`;
      return;
    }
    viewRoot.innerHTML = '<div class="view-enter" id="member-detail-root"></div>';
    MemberDetail.render(document.getElementById('member-detail-root'), member, DATA);
  }

  try {
    DATA = await DataStore.load();
  } catch (err) {
    viewRoot.innerHTML = `<div class="error-state">
      <h2>Couldn't load live telemetry</h2>
      <p>${Format.escapeHtml(err.message)}</p>
    </div>`;
    return;
  }

  Router.init({ overview: showOverview, member: showMember });

  searchInput.addEventListener('input', (e) => {
    Leaderboard.setQuery(e.target.value);
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
