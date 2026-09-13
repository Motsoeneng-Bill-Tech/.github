const MemberDetail = (() => {
  function render(container, member, data) {
    const repos = Object.entries(member.firm_commits.by_repo);
    const maxCount = repos.length ? repos[0][1] : 1;

    const c = member.consistency || {};
    const badge = member.tier_badge || '';
    const status = member.cadence_status || member.tier || 'Active';
    const isSporadic = status === 'Sporadic Pusher';

    container.innerHTML = `
      <a class="detail-back" href="./#/">&larr; Back to leaderboard</a>
      <div class="detail-header">
        <img src="${member.avatar_url}" alt="" width="72" height="72" />
        <div>
          <div class="detail-header__name">${Format.escapeHtml(member.name || member.login)}</div>
          <div class="detail-header__login">
            <a href="${member.html_url}" target="_blank" rel="noopener">@${Format.escapeHtml(member.login)} ↗</a>
            &middot; Member since ${Format.date(member.created_at)}
          </div>
          <div class="detail-header__badges">
            <span class="tier-chip ${isSporadic ? 'tier-chip--warn' : ''}">${badge} ${Format.escapeHtml(status)}</span>
            <span class="tier-chip">Rank #${member.rank} of ${data.org.member_count}</span>
          </div>
          <div class="detail-header__desc">${Format.escapeHtml(member.cadence_desc || '')}</div>
        </div>
      </div>

      ${isSporadic ? `
        <div class="alert-banner alert-banner--warn">
          <strong>⚠️ Cadence Notice:</strong> This engineer displays high commit bursts (${member.commits_per_active_day || 0} commits per active day) but low daily presence (${c.pct ? c.pct.toFixed(0) : 0}% of days). The engineering division prioritizes consistent daily presence and code reviews over commit volume.
        </div>
      ` : ''}

      <div class="stat-grid">
        <div class="stat-tile"><div class="stat-tile__label">Active Days</div><div class="stat-tile__value stat-tile__value--accent">${c.pct ? c.pct.toFixed(0) : 0}%<span class="stat-tile__hint">(${c.active_days || 0}/${c.total_days || 0}d)</span></div><div class="stat-tile__sub">Daily consistency</div></div>
        <div class="stat-tile"><div class="stat-tile__label">Record Streak</div><div class="stat-tile__value">${c.longest_streak || 0}<span class="stat-tile__hint">days</span></div><div class="stat-tile__sub">${c.current_streak || 0}d current streak</div></div>
        <div class="stat-tile"><div class="stat-tile__label">Peer Code Reviews</div><div class="stat-tile__value">${Format.number(member.contributions.reviews)}</div><div class="stat-tile__sub">Standards & guidelines</div></div>
        <div class="stat-tile"><div class="stat-tile__label">Pull Requests</div><div class="stat-tile__value">${Format.number(member.contributions.pull_requests)}</div><div class="stat-tile__sub">Delivered across ${c.repos_breadth || 0} repos</div></div>
      </div>

      <div class="detail-calendar-card">
        <div class="org-calendar-card__title">Contribution activity since ${Format.date(member.calendar.from)}</div>
        <div id="detail-calendar-slot"></div>
      </div>

      <div class="repo-breakdown">
        <div class="org-calendar-card__title">Firm repository breakdown</div>
        ${repos.length ? repos.map(([name, count]) => `
          <div class="repo-bar-row">
            <div class="repo-bar-row__name" title="${Format.escapeHtml(name)}">${Format.escapeHtml(name)}</div>
            <div class="repo-bar-row__track"><div class="repo-bar-row__fill" style="width:${((count / maxCount) * 100).toFixed(0)}%"></div></div>
            <div class="repo-bar-row__count">${Format.number(count)}</div>
          </div>
        `).join('') : '<p style="color:var(--text-tertiary);">No firm repository commits yet.</p>'}
      </div>
    `;

    Calendar.render(container.querySelector('#detail-calendar-slot'), member.calendar, { mode: 'full' });
    document.title = `${member.name || member.login} — Motsoeneng Bill Tech Engineering`;
  }

  return { render };
})();
