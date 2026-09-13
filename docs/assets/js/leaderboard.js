const Leaderboard = (() => {
  const COLUMNS = [
    { key: 'rank', label: 'Rank', sortable: true, get: (m) => m.rank, dir: 'asc' },
    { key: 'engineer', label: 'Engineer', sortable: false },
    { key: 'status', label: 'Cadence Status', sortable: false },
    { key: 'consistency', label: 'Active Days', sortable: true, get: (m) => m.consistency.pct, dir: 'desc' },
    { key: 'streak', label: 'Record Streak', sortable: true, get: (m) => m.consistency.longest_streak, dir: 'desc' },
    { key: 'reviews', label: 'Code Reviews', sortable: true, get: (m) => m.contributions.reviews, dir: 'desc' },
    { key: 'prs', label: 'PRs Delivered', sortable: true, get: (m) => m.contributions.pull_requests, dir: 'desc' },
    { key: 'activity', label: '14-Week Activity Heatmap', sortable: false },
  ];

  const state = { sortKey: 'rank', sortDir: 'asc', query: '' };
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
      <img src="${m.avatar_url}" alt="" width="34" height="34" loading="lazy" />
      <div>
        <div class="engineer-cell__name">${Format.escapeHtml(m.name || m.login)}</div>
        <div class="engineer-cell__login">@${Format.escapeHtml(m.login)}</div>
      </div>
    </div>`;
  }

  function renderTable(container, list) {
    const thead = `<thead><tr>${COLUMNS.map((c) => {
      if (!c.sortable) return `<th>${c.label}</th>`;
      const active = state.sortKey === c.key;
      const arrow = active ? (state.sortDir === 'asc' ? '↑' : '↓') : '↓';
      return `<th class="is-sortable ${active ? 'is-active' : ''}" data-sort-key="${c.key}" tabindex="0" role="button" aria-label="Sort by ${c.label}">${c.label} <span class="sort-arrow">${arrow}</span></th>`;
    }).join('')}</tr></thead>`;

    const rows = list.map((m) => {
      const c = m.consistency;
      const badge = m.tier_badge || '';
      const status = m.cadence_status || m.tier || 'Active';
      const isSporadic = status === 'Sporadic Pusher';
      const chipClass = isSporadic ? 'tier-chip tier-chip--warn' : 'tier-chip';

      return `<tr data-login="${m.login}" tabindex="0" role="button" aria-label="View ${m.login}'s profile">
        <td class="rank-num">#${String(m.rank).padStart(2, '0')}</td>
        <td>${engineerCell(m)}</td>
        <td><span class="${chipClass}">${badge} ${Format.escapeHtml(status)}</span></td>
        <td class="num-cell">
          <strong>${c.pct.toFixed(0)}%</strong>
          <div class="cell-sub">${c.active_days} / ${c.total_days} days</div>
        </td>
        <td class="num-cell">
          <strong>${c.longest_streak}d</strong>
          <div class="cell-sub">${c.current_streak}d current</div>
        </td>
        <td class="num-cell">${Format.number(m.contributions.reviews)}</td>
        <td class="num-cell">${Format.number(m.contributions.pull_requests)}</td>
        <td><div data-login-cal="${m.login}"></div></td>
      </tr>`;
    }).join('');

    container.innerHTML = `<table class="leaderboard">${thead}<tbody>${rows}</tbody></table>`;
    list.forEach((m) => {
      const slot = container.querySelector(`[data-login-cal="${m.login}"]`);
      if (slot) Calendar.render(slot, m.calendar, { mode: 'compact', legend: false });
    });
  }

  function renderCards(container, list) {
    container.innerHTML = list.map((m) => {
      const c = m.consistency;
      const status = m.cadence_status || m.tier;
      return `<div class="leaderboard-card" data-login="${m.login}" tabindex="0" role="button" aria-label="View ${m.login}'s profile">
        <div class="leaderboard-card__top">
          <img src="${m.avatar_url}" alt="" width="40" height="40" loading="lazy" />
          <div>
            <div class="engineer-cell__name">${Format.escapeHtml(m.name || m.login)}</div>
            <div class="engineer-cell__login">@${Format.escapeHtml(m.login)} &middot; <span class="tier-chip">${m.tier_badge || ''} ${Format.escapeHtml(status)}</span></div>
          </div>
        </div>
        <div class="leaderboard-card__meta">
          <div class="leaderboard-card__stat">Rank<strong>#${m.rank}</strong></div>
          <div class="leaderboard-card__stat">Active Days<strong>${c.pct.toFixed(0)}% (${c.active_days}d)</strong></div>
          <div class="leaderboard-card__stat">Streak<strong>${c.longest_streak} days</strong></div>
          <div class="leaderboard-card__stat">Reviews<strong>${m.contributions.reviews}</strong></div>
        </div>
      </div>`;
    }).join('');
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
