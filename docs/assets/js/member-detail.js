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
            &middot; Joined ${Format.date(member.created_at)} &middot; ${member.tenure_days} days with the firm
          </div>
          <div class="detail-header__badges">
            <span class="tier-chip">${Format.escapeHtml(member.cadence_band)}</span>
            <span class="status-chip ${member.engagement_status === 'Dormant' ? 'status--dormant' : 'status--active'}">${Format.escapeHtml(member.engagement_status)}</span>
            <span class="tier-chip tier-chip--quiet">#${member.rank} of ${data.org.member_count} by reliability</span>
          </div>
        </div>
      </div>

      ${riskBanner}

      <div class="stat-grid">
        <div class="stat-tile">
          <div class="stat-tile__label">Reliability</div>
          <div class="stat-tile__value stat-tile__value--accent">${rel.pct.toFixed(0)}%</div>
          <div class="stat-tile__sub">present ${rel.active_days} of the last ${rel.window_days} days</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Current streak</div>
          <div class="stat-tile__value">${c.current_streak}<span class="stat-tile__hint">days</span></div>
          <div class="stat-tile__sub">best run ${c.longest_streak} days</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Active projects</div>
          <div class="stat-tile__value">${member.current_project_count}</div>
          <div class="stat-tile__sub">${member.project_count} worked on in total</div>
        </div>
        <div class="stat-tile">
          <div class="stat-tile__label">Direction</div>
          <div class="stat-tile__value stat-tile__value--sm">${Format.escapeHtml(member.trend.direction)}</div>
          <div class="stat-tile__sub">${member.trend.recent_avg_active_days} active days/week recently vs ${member.trend.earlier_avg_active_days} before</div>
        </div>
      </div>

      <div class="panel-row">
        <section class="panel">
          <h3 class="panel__title">Cadence over the last ${member.trend.weeks.length} weeks</h3>
          <p class="panel__hint">Active days per week. Each bar tops out at 7.</p>
          ${trendSparkline(member.trend)}
        </section>
        <section class="panel">
          <h3 class="panel__title">Working pattern</h3>
          <p class="panel__hint">Share of each weekday spent working, across their whole time here.</p>
          ${weekdayPattern(member.weekday_pattern)}
        </section>
      </div>

      <section class="panel">
        <h3 class="panel__title">Projects — currently working on ${current.length ? `(${current.length})` : ''}</h3>
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
        <h3 class="panel__title">Daily activity since joining</h3>
        <p class="panel__hint">Each square is one day. Shade shows relative activity; a day counts once no matter how much was pushed.</p>
        <div id="detail-calendar-slot"></div>
      </section>
    `;

    Calendar.render(container.querySelector('#detail-calendar-slot'), member.calendar, { mode: 'full' });
    document.title = `${member.name || member.login} — ${data.org.name} Engineering`;
  }

  return { render };
})();
