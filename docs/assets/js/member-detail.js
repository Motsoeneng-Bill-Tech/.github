const MemberDetail = (() => {
  function render(container, member, data) {
    const repos = Object.entries(member.firm_commits.by_repo);
    const maxCount = repos.length ? repos[0][1] : 1;

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
            <span class="tier-chip">${Format.escapeHtml(member.tier)}</span>
            <span class="tier-chip">Rank #${member.rank} of ${data.org.member_count}</span>
          </div>
        </div>
      </div>

      <div class="stat-grid">
        <div class="stat-tile"><div class="stat-tile__label">Total Contributions</div><div class="stat-tile__value">${Format.number(member.contributions.total)}</div></div>
        <div class="stat-tile"><div class="stat-tile__label">Firm Commits</div><div class="stat-tile__value stat-tile__value--accent">${Format.number(member.firm_commits.total)}</div></div>
        <div class="stat-tile"><div class="stat-tile__label">Active Days</div><div class="stat-tile__value">${Format.number(member.calendar.active_days)}<span class="stat-tile__hint">${Format.pct(member.calendar.active_pct, 0)}</span></div></div>
        <div class="stat-tile"><div class="stat-tile__label">Longest Streak</div><div class="stat-tile__value">${Format.number(member.calendar.longest_streak)}<span class="stat-tile__hint">days</span></div></div>
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
