/**
 * Real interactive contribution calendar — SVG day-cells with genuine hover/focus
 * tooltips (not the dead <title> tags the old README SVGs relied on, which never
 * fired because GitHub strips interactivity from <img>-embedded SVG).
 *
 * One rendering path for both the compact leaderboard sparkline and the full
 * member-detail calendar, so the two views can never visually disagree.
 */
const Calendar = (() => {
  const RAMP = ['var(--cal-0)', 'var(--cal-1)', 'var(--cal-2)', 'var(--cal-3)', 'var(--cal-4)'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function buildSVG(calendar, { mode = 'compact' } = {}) {
    const weeks = calendar.weeks || [];
    const cell = mode === 'full' ? 11 : 9;
    const gap = mode === 'full' ? 3 : 2.5;
    const startX = 4;
    const startY = mode === 'full' ? 20 : 4;
    const width = startX + weeks.length * (cell + gap) + 4;
    const height = startY + 7 * (cell + gap) + 4;

    let rects = '';
    let monthLabels = '';
    const seenMonths = new Set();

    weeks.forEach((week, wIdx) => {
      const colX = startX + wIdx * (cell + gap);
      week.days.forEach((day) => {
        const rowY = startY + day.weekday * (cell + gap);
        const opacity = day.in_range ? 1 : 0.28;
        if (mode === 'full' && day.weekday === 0 && day.in_range) {
          const monthKey = day.date.slice(0, 7);
          if (!seenMonths.has(monthKey)) {
            seenMonths.add(monthKey);
            const m = MONTHS[parseInt(day.date.slice(5, 7), 10) - 1];
            monthLabels += `<text x="${colX}" y="${startY - 8}" class="cal-month-label">${m}</text>`;
          }
        }
        rects += '<rect class="cal-day" tabindex="0" role="img" '
          + `x="${colX.toFixed(1)}" y="${rowY.toFixed(1)}" width="${cell}" height="${cell}" rx="2" `
          + `fill="${RAMP[day.level]}" fill-opacity="${opacity}" `
          + `data-date="${day.date}" data-count="${day.count}" `
          + `aria-label="${day.count} contribution${day.count === 1 ? '' : 's'} on ${day.date}"></rect>`;
      });
    });

    return `<svg class="cal-svg" viewBox="0 0 ${width.toFixed(1)} ${height.toFixed(1)}" width="${width.toFixed(0)}" height="${height.toFixed(0)}" xmlns="http://www.w3.org/2000/svg">${monthLabels}<g>${rects}</g></svg>`;
  }

  function legendHTML() {
    return `<div class="cal-legend"><span>Less</span>${RAMP.map((c) => `<span class="cal-legend__swatch" style="background:${c}"></span>`).join('')}<span>More</span></div>`;
  }

  let listenersBound = false;
  function ensureTooltipListeners() {
    if (listenersBound) return;
    listenersBound = true;
    const tooltip = document.getElementById('tooltip');

    function position(x, y) {
      tooltip.style.left = `${x}px`;
      tooltip.style.top = `${y - 10}px`;
    }

    function show(target) {
      const date = target.getAttribute('data-date');
      const count = target.getAttribute('data-count');
      if (!date) return;
      const d = new Date(`${date}T00:00:00`);
      const label = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
      tooltip.innerHTML = `<strong>${count}</strong> contribution${count === '1' ? '' : 's'} on ${label}`;
      tooltip.hidden = false;
      const rect = target.getBoundingClientRect();
      position(rect.left + rect.width / 2, rect.top);
      requestAnimationFrame(() => tooltip.classList.add('is-visible'));
    }

    function hide() {
      tooltip.classList.remove('is-visible');
      tooltip.hidden = true;
    }

    document.addEventListener('mouseover', (e) => {
      const target = e.target.closest('.cal-day');
      if (target) show(target);
    });
    document.addEventListener('mousemove', (e) => {
      if (tooltip.hidden) return;
      const target = e.target.closest('.cal-day');
      if (target) {
        const rect = target.getBoundingClientRect();
        position(rect.left + rect.width / 2, rect.top);
      }
    });
    document.addEventListener('mouseout', (e) => {
      if (e.target.closest('.cal-day')) hide();
    });
    document.addEventListener('focusin', (e) => {
      const target = e.target.closest('.cal-day');
      if (target) show(target);
    });
    document.addEventListener('focusout', (e) => {
      if (e.target.closest('.cal-day')) hide();
    });
  }

  function render(container, calendar, opts = {}) {
    ensureTooltipListeners();
    container.innerHTML = buildSVG(calendar, opts) + (opts.legend === false ? '' : legendHTML());
  }

  return { render, buildSVG, legendHTML };
})();
