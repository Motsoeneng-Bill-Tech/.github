const Leaderboard = (() => {
  // Ranked by consistency, never by volume — total contributions, commit counts, and PR
  // counts are deliberately not sortable columns here, since a single high-volume day
  // (someone padding out commits) can inflate any of them. Consistency % and streak
  // length can't be padded that way: showing up every day is the only lever that moves
  // either number.
  const COLUMNS = [
    { key: 'rank', label: 'Rank', sortable: true, get: (m) => m.rank, dir: 'asc' },
    { key: 'engineer', label: 'Engineer', sortable: false },
    { key: 'created_at', label: 'Member Since', sortable: true, get: (m) => new Date(m.created_at).getTime() },
    { key: 'consistency', label: 'Consistency (30d)', sortable: true, get: (m) => m.consistency.recent_active_pct },
    { key: 'streak', label: 'Current Streak', sortable: true, get: (m) => m.calendar.current_streak },
    { key: 'tier', label: 'Tier', sortable: false },
    { key: 'activity', label: 'Recent Activity', sortable: false },
    { key: 'repos', label: 'Top Repositories', sortable: false },
  ];

  const state = { sortKey: 'consistency', sortDir: 'desc', query: '' };
  let lastArgs = null;

  function filterAndSort(members) {
    const q = state.query.trim().toLowerCase();
    let list = q
      ? members.filter((m) => m.login.toLowerCase().includes(q) || (m.name || '').toLowerCase().includes(q))
      : members;
    const col = COLUMNS.find((c) => c.key === state.sortKey);
    if (col && col.get) {
      list = [...list].sort((a, b) => {
        const diff = col.get(a) - col.get(b);
        return state.sortDir === 'asc' ? diff : -diff;
      });
    }
    return list;
  }

  function engineerCell(m) {
    return `<div class="engineer-cell">
      <img src="${m.avatar_url}" alt="" width="30" height="30" loading="lazy" />
      <div>
        <div class="engineer-cell__name">${Format.escapeHtml(m.name || m.login)}</div>
        <div class="engineer-cell__login">@${Format.escapeHtml(m.login)}</div>
      </div>
    </div>`;
  }

  function repoTags(m) {
    const repos = m.firm_commits.top_repos.slice(0, 2);
    if (!repos.length) return '<span class="repo-tags">—</span>';
    return `<div class="repo-tags">${repos.map((r) => `<span class="repo-tag">${Format.escapeHtml(r)}</span>`).join('')}</div>`;
  }

  function renderTable(container, list) {
    const thead = `<thead><tr>${COLUMNS.map((c) => {
      if (!c.sortable) return `<th>${c.label}</th>`;
      const active = state.sortKey === c.key;
      const arrow = active ? (state.sortDir === 'asc' ? '↑' : '↓') : '↓';
      return `<th class="is-sortable ${active ? 'is-active' : ''}" data-sort-key="${c.key}" tabindex="0" role="button" aria-label="Sort by ${c.label}">${c.label} <span class="sort-arrow">${arrow}</span></th>`;
    }).join('')}</tr></thead>`;

    const rows = list.map((m) => `<tr data-login="${m.login}" tabindex="0" role="button" aria-label="View ${m.login}'s profile">
      <td class="rank-num">${String(m.rank).padStart(2, '0')}</td>
      <td>${engineerCell(m)}</td>
      <td>${Format.date(m.created_at)}</td>
      <td class="num-cell">${Format.pct(m.consistency.recent_active_pct, 0)}</td>
      <td class="num-cell">${m.calendar.current_streak}d</td>
      <td><span class="tier-chip">${Format.escapeHtml(m.tier)}</span></td>
      <td><div data-login-cal="${m.login}"></div></td>
      <td>${repoTags(m)}</td>
    </tr>`).join('');

    container.innerHTML = `<table class="leaderboard">${thead}<tbody>${rows}</tbody></table>`;
    list.forEach((m) => {
      const slot = container.querySelector(`[data-login-cal="${m.login}"]`);
      if (slot) Calendar.render(slot, m.calendar, { mode: 'compact', legend: false });
    });
  }

  function renderCards(container, list) {
    container.innerHTML = list.map((m) => `<div class="leaderboard-card" data-login="${m.login}" tabindex="0" role="button" aria-label="View ${m.login}'s profile">
      <div class="leaderboard-card__top">
        <img src="${m.avatar_url}" alt="" width="36" height="36" loading="lazy" />
        <div>
          <div class="engineer-cell__name">${Format.escapeHtml(m.name || m.login)}</div>
          <div class="engineer-cell__login">@${Format.escapeHtml(m.login)} &middot; <span class="tier-chip">${Format.escapeHtml(m.tier)}</span></div>
        </div>
      </div>
      <div class="leaderboard-card__meta">
        <div class="leaderboard-card__stat">Rank<strong>#${m.rank}</strong></div>
        <div class="leaderboard-card__stat">Consistency<strong>${Format.pct(m.consistency.recent_active_pct, 0)}</strong></div>
        <div class="leaderboard-card__stat">Streak<strong>${m.calendar.current_streak}d</strong></div>
      </div>
    </div>`).join('');
  }

  function wireActivation(container, onSelect) {
    container.querySelectorAll('[data-login]').forEach((el) => {
      el.addEventListener('click', () => onSelect(el.dataset.login));
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(el.dataset.login);
        }
      });
    });
  }

  function render(tableContainer, cardsContainer, members, { onSelect }) {
    lastArgs = { tableContainer, cardsContainer, members, onSelect };
    const list = filterAndSort(members);

    if (!list.length) {
      const msg = '<div class="empty-note">No engineers match your search.</div>';
      tableContainer.innerHTML = msg;
      cardsContainer.innerHTML = msg;
      return;
    }

    renderTable(tableContainer, list);
    renderCards(cardsContainer, list);
    wireActivation(tableContainer, onSelect);
    wireActivation(cardsContainer, onSelect);

    tableContainer.querySelectorAll('th.is-sortable').forEach((th) => {
      const activate = () => {
        const key = th.dataset.sortKey;
        state.sortDir = state.sortKey === key ? (state.sortDir === 'asc' ? 'desc' : 'asc') : 'desc';
        state.sortKey = key;
        render(tableContainer, cardsContainer, members, { onSelect });
      };
      th.addEventListener('click', activate);
      th.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
      });
    });
  }

  function setQuery(q) {
    state.query = q;
    if (lastArgs) render(lastArgs.tableContainer, lastArgs.cardsContainer, lastArgs.members, { onSelect: lastArgs.onSelect });
  }

  return { render, setQuery };
})();
