/**
 * Engineering roster. Every sortable column here is day-based — reliability, streak
 * length, project counts. There is deliberately no column counting commits, pull
 * requests or reviews, because a count is the one thing an engineer can inflate in an
 * afternoon, and ranking on it is what this dashboard exists to stop doing.
 */
const Leaderboard = (() => {
  const COLUMNS = [
    { key: 'rank', label: '#', sortable: true, get: (m) => m.rank, dir: 'asc' },
    { key: 'engineer', label: 'Engineer', sortable: false },
    { key: 'reliability', label: 'Verified presence', sortable: true, get: (m) => m.reliability.pct, dir: 'desc' },
    { key: 'streak', label: 'Verified streak', sortable: true, get: (m) => m.reliability.current_streak, dir: 'desc' },
    { key: 'recorded', label: 'Recorded', sortable: true, get: (m) => m.recorded.pct, dir: 'desc' },
    { key: 'projects', label: 'Projects', sortable: true, get: (m) => m.current_project_count, dir: 'desc' },
    { key: 'trend', label: 'Trend', sortable: false },
    { key: 'status', label: 'Status', sortable: false },
    { key: 'activity', label: 'Activity', sortable: false },
  ];

  const state = { sortKey: 'rank', sortDir: 'asc', query: '' };
  let lastArgs = null;

  function filterAndSort(members) {
    const q = state.query.trim().toLowerCase();
    let list = q
      ? members.filter((m) => m.login.toLowerCase().includes(q)
          || (m.name || '').toLowerCase().includes(q)
          || m.projects.some((p) => p.display_name.toLowerCase().includes(q)))
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
    const risk = m.carries_key_person_risk_for.length
      ? `<span class="risk-dot" title="Sole active engineer on ${m.carries_key_person_risk_for.length} project(s)"></span>`
      : '';
    return `<div class="engineer-cell">
      <img src="${m.avatar_url}" alt="" width="34" height="34" loading="lazy" />
      <div>
        <div class="engineer-cell__name">${Format.escapeHtml(m.name || m.login)}${risk}</div>
        <div class="engineer-cell__login">@${Format.escapeHtml(m.login)} &middot; ${m.cadence_band}</div>
      </div>
    </div>`;
  }

  function reliabilityCell(m) {
    const rel = m.reliability;
    return `<div class="meter">
        <div class="meter__bar"><div class="meter__fill" style="width:${rel.pct.toFixed(0)}%"></div></div>
        <div class="meter__label"><strong>${rel.pct.toFixed(0)}%</strong> <span>${rel.active_days}/${rel.window_days}d</span></div>
      </div>`;
  }

  function trendCell(m) {
    const dir = m.trend.direction;
    const cls = dir === 'Improving' ? 'trend--up' : dir === 'Declining' ? 'trend--down' : 'trend--flat';
    const glyph = dir === 'Improving' ? '▲' : dir === 'Declining' ? '▼' : '—';
    return `<span class="trend ${cls}">${glyph} ${dir}</span>`;
  }

  function statusCell(m) {
    const cls = m.engagement_level === 'stale' ? 'status--dormant'
      : m.engagement_level === 'slowing' ? 'status--slowing' : 'status--active';
    return `<span class="status-chip ${cls}">${Format.escapeHtml(m.engagement_status)}</span>`;
  }

  function projectsCell(m) {
    return `<div class="num-cell"><strong>${m.current_project_count}</strong>
      <div class="cell-sub">of ${m.project_count} worked on</div></div>`;
  }

  function renderTable(container, list) {
    const thead = `<thead><tr>${COLUMNS.map((c) => {
      if (!c.sortable) return `<th>${c.label}</th>`;
      const active = state.sortKey === c.key;
      const arrow = active ? (state.sortDir === 'asc' ? '↑' : '↓') : '↓';
      return `<th class="is-sortable ${active ? 'is-active' : ''}" data-sort-key="${c.key}" tabindex="0" role="button" aria-label="Sort by ${c.label}">${c.label} <span class="sort-arrow">${arrow}</span></th>`;
    }).join('')}</tr></thead>`;

    const rows = list.map((m) => `<tr data-login="${m.login}" tabindex="0" role="button" aria-label="Open ${m.login}'s profile">
        <td class="rank-num">${String(m.rank).padStart(2, '0')}</td>
        <td>${engineerCell(m)}</td>
        <td>${reliabilityCell(m)}</td>
        <td class="num-cell"><strong>${m.reliability.current_streak}d</strong><div class="cell-sub">${m.reliability.longest_streak}d best</div></td>
        <td class="num-cell"><strong>${m.recorded.pct.toFixed(0)}%</strong><div class="cell-sub">${m.reliability.corroboration_pct.toFixed(0)}% corroborated</div></td>
        <td>${projectsCell(m)}</td>
        <td>${trendCell(m)}</td>
        <td>${statusCell(m)}</td>
        <td><div data-login-cal="${m.login}"></div></td>
      </tr>`).join('');

    container.innerHTML = `<table class="leaderboard">${thead}<tbody>${rows}</tbody></table>`;
    list.forEach((m) => {
      const slot = container.querySelector(`[data-login-cal="${m.login}"]`);
      if (slot) Calendar.render(slot, m.calendar, { mode: 'compact', legend: false });
    });
  }

  function renderCards(container, list) {
    container.innerHTML = list.map((m) => `<div class="leaderboard-card" data-login="${m.login}" tabindex="0" role="button" aria-label="Open ${m.login}'s profile">
        <div class="leaderboard-card__top">
          <img src="${m.avatar_url}" alt="" width="40" height="40" loading="lazy" />
          <div>
            <div class="engineer-cell__name">${Format.escapeHtml(m.name || m.login)}</div>
            <div class="engineer-cell__login">@${Format.escapeHtml(m.login)} &middot; <span class="tier-chip">${Format.escapeHtml(m.cadence_band)}</span></div>
          </div>
        </div>
        <div class="leaderboard-card__meta">
          <div class="leaderboard-card__stat">Verified<strong>${m.reliability.pct.toFixed(0)}%</strong></div>
          <div class="leaderboard-card__stat">Streak<strong>${m.reliability.current_streak}d</strong></div>
          <div class="leaderboard-card__stat">Projects<strong>${m.current_project_count}</strong></div>
          <div class="leaderboard-card__stat">Status<strong>${Format.escapeHtml(m.engagement_status)}</strong></div>
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
