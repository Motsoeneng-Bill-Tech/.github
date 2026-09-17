/**
 * The per-engineer executive profile: who they are, what they are working on, how
 * reliably they show up, and what the firm depends on them for.
 *
 * Nothing on this page is a count of output. Every figure is a count of DAYS, which is
 * the one thing a burst of activity cannot manufacture.
 */
const MemberDetail = (() => {
  const WEEKDAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  function trendSparkline(trend) {
    const weeks = trend.weeks || [];
    if (!weeks.length) return '';
    const w = 8;
    const gap = 3;
    const maxH = 34;
    const bars = weeks.map((wk, i) => {
      const h = Math.max(2, (wk.active_days / 7) * maxH);
      const x = i * (w + gap);
      const y = maxH - h;
      return `<rect x="${x}" y="${y.toFixed(1)}" width="${w}" height="${h.toFixed(1)}" rx="2" fill="var(--accent)" fill-opacity="${0.35 + (wk.active_days / 7) * 0.65}">
          <title>${wk.active_days} active day${wk.active_days === 1 ? '' : 's'} in week of ${wk.week_start}</title>
        </rect>`;
    }).join('');
    const width = weeks.length * (w + gap);
    return `<svg class="sparkline" viewBox="0 0 ${width} ${maxH}" width="${width}" height="${maxH}" role="img" aria-label="Active days per week over the last ${weeks.length} weeks">${bars}</svg>`;
  }

  function weekdayPattern(pattern) {
    return `<div class="weekday-grid">${pattern.map((d, i) => `
        <div class="weekday-cell" title="${d.pct.toFixed(0)}% of ${WEEKDAY_LABELS[i]} days active (${d.active_days} of ${d.total_days})">
          <div class="weekday-cell__bar"><div class="weekday-cell__fill" style="height:${Math.max(3, d.pct).toFixed(0)}%"></div></div>
          <div class="weekday-cell__label">${WEEKDAY_LABELS[i]}</div>
        </div>`).join('')}</div>`;
  }

  function projectCard(p) {
    const statusCls = p.is_current ? 'pcard--current' : 'pcard--past';
    const lastLine = `Last worked ${Format.dayAgo(p.days_since_last)}`;
    const soleFlag = p.is_only_active_engineer
      ? '<span class="pcard__flag">Sole active engineer</span>'
      : '';
    return `<a class="pcard ${statusCls}" href="./#/project/${encodeURIComponent(p.repo)}">
        <div class="pcard__head">
          <div class="pcard__name">${Format.escapeHtml(p.display_name)}</div>
          ${p.primary_language ? `<span class="pcard__lang">${Format.escapeHtml(p.primary_language)}</span>` : ''}
        </div>
        <div class="pcard__days"><strong>${p.active_days}</strong> day${p.active_days === 1 ? '' : 's'} engaged</div>
        <div class="pcard__span">${Format.date(p.first_active)} → ${Format.date(p.last_active)}</div>
        <div class="pcard__foot">${lastLine}${soleFlag}</div>
      </a>`;
  }

  function render(container, member, data) {
    const c = member.consistency;
    const rel = member.reliability;
    const rec = member.recorded;
    const current = member.projects.filter((p) => p.is_current);
    const past = member.projects.filter((p) => !p.is_current);

    const riskBanner = member.carries_key_person_risk_for.length ? `
      <div class="alert-banner alert-banner--warn">
        <strong>Continuity risk.</strong> ${Format.escapeHtml(member.name || member.login)} is currently the only
        engineer working on ${member.carries_key_person_risk_for.map((n) => `<strong>${Format.escapeHtml(n)}</strong>`).join(' and ')}.
        If they were unavailable, that work would stall.
      </div>` : '';

    container.innerHTML = `
      <a class="detail-back" href="./#/">&larr; Back to overview</a>

      <div class="detail-header">
        <img src="${member.avatar_url}" alt="" width="76" height="76" />
        <div class="detail-header__main">
          <div class="detail-header__name">${Format.escapeHtml(member.name || member.login)}</div>
          <div class="detail-header__login">
            <a href="${member.html_url}" target="_blank" rel="noopener">@${Format.escapeHtml(member.login)} ↗</a>
            &middot; First seen working here ${Format.date(member.observed_from)} &middot; ${member.observed_days} days observed
          </div>
          <div class="detail-header__badges">
            <span class="tier-chip">${Format.escapeHtml(member.cadence_band)}</span>
            <span class="status-chip ${member.engagement_level === 'stale' ? 'status--dormant' : member.engagement_level === 'slowing' ? 'status--slowing' : 'status--active'}">${Format.escapeHtml(member.engagement_status)}</span>
            <span class="tier-chip tier-chip--quiet">#${member.rank} of ${data.org.member_count} by verified presence</span>
            ${member.is_new_joiner ? '<span class="tier-chip tier-chip--warn">New joiner</span>' : ''}
          </div>
        </div>
      </div>

      ${riskBanner}

      <div class="stat-grid">
        <div class="stat-tile">
          <div class="stat-tile__label">Verified presence</div>
          <div class="stat-tile__value stat-tile__value--accent">${rel.pct.toFixed(0)}%</div>
          <div class="stat-tile__sub">${rel.active_days} of the last ${rel.window_days} days carry server-stamped evidence</div>
          <div class="stat-tile__caveat">A measure of engagement and cadence — not a performance rating, and blind to leave.</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Verified streak</div>
          <div class="stat-tile__value">${rel.current_streak}<span class="stat-tile__hint">days</span></div>
          <div class="stat-tile__sub">best run ${rel.longest_streak} days</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Active projects</div>
          <div class="stat-tile__value">${member.current_project_count}</div>
          <div class="stat-tile__sub">${member.project_count} worked on in total</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Direction</div>
          <div class="stat-tile__value stat-tile__value--sm">${Format.escapeHtml(member.trend.direction)}</div>
          <div class="stat-tile__sub">${member.trend.recent_avg_active_days === null
            ? `only ${member.trend.weeks_observed} full week${member.trend.weeks_observed === 1 ? '' : 's'} here so far`
            : `${member.trend.recent_avg_active_days} active days/week recently vs ${member.trend.earlier_avg_active_days} before`}</div>
        </div>
      </div>

      <div class="panel-row">
        <section class="panel">
          <h3 class="panel__title">Cadence over the last ${member.trend.weeks.length} week${member.trend.weeks.length === 1 ? '' : 's'}</h3>
          <p class="panel__hint">Active days per week since they were first seen here. Each bar tops out at 7. Weeks before they joined are not charted.</p>
          ${trendSparkline(member.trend)}
        </section>
        <section class="panel">
          <h3 class="panel__title">Working pattern</h3>
          <p class="panel__hint">Share of each weekday spent working, across their whole time here.</p>
          ${weekdayPattern(member.weekday_pattern)}
        </section>
      </div>

      <section class="panel">
        <h3 class="panel__title">Projects — active in the last 14 days ${current.length ? `(${current.length})` : ''}</h3>
        ${current.length
          ? `<div class="pcard-grid">${current.map(projectCard).join('')}</div>`
          : '<p class="panel__hint">Not currently working on any firm project.</p>'}
      </section>

      ${past.length ? `
      <section class="panel">
        <h3 class="panel__title">Previously worked on (${past.length})</h3>
        <div class="pcard-grid">${past.map(projectCard).join('')}</div>
      </section>` : ''}

      ${member.languages.length ? `
      <section class="panel">
        <h3 class="panel__title">Technologies</h3>
        <div class="tag-row">${member.languages.map((l) => `<span class="repo-tag">${Format.escapeHtml(l)}</span>`).join('')}</div>
      </section>` : ''}

      <section class="panel">
        <h3 class="panel__title">Evidence behind these figures</h3>
        <div class="evidence-row">
          <div class="evidence">
            <div class="evidence__label">Verified presence</div>
            <div class="evidence__value">${rel.total_days} days</div>
            <div class="evidence__note">Dates GitHub's servers stamped when a pull request, review or issue arrived. A contributor's computer cannot set these.</div>
          </div>
          <div class="evidence">
            <div class="evidence__label">Recorded activity</div>
            <div class="evidence__value">${c.active_days} days</div>
            <div class="evidence__note">GitHub's commit calendar. Commit dates are supplied by the contributor's own machine, so this is reported here but never ranked.</div>
          </div>
          <div class="evidence">
            <div class="evidence__label">Corroborated</div>
            <div class="evidence__value">${rel.corroboration_pct.toFixed(0)}%</div>
            <div class="evidence__note">${rel.corroboration_pct >= 60
              ? 'Most recorded days carry independent evidence.'
              : 'Much of the recorded activity has no independent evidence. That can simply mean work goes straight to a branch without pull requests — read it as a question, not a verdict.'}</div>
          </div>
        </div>
      </section>

      <section class="panel">
        <h3 class="panel__title">Daily activity since joining</h3>
        <p class="panel__hint">GitHub's recorded calendar — ${rec.pct.toFixed(0)}% of the last ${rec.window_days} days. Each square is one day: worked, or not worked. Nothing here varies with how much was pushed.</p>
        <div id="detail-calendar-slot"></div>
      </section>

      ${window.Disclosures ? window.Disclosures.html() : ''}
    `;

    Calendar.render(container.querySelector('#detail-calendar-slot'), member.calendar, { mode: 'full' });
    document.title = `${member.name || member.login} — ${data.org.name} Engineering`;
  }

  return { render };
})();
