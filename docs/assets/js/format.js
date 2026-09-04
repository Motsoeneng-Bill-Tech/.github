const Format = (() => {
  function number(n) {
    return (n ?? 0).toLocaleString('en-US');
  }

  function pct(n, digits = 1) {
    return `${(n ?? 0).toFixed(digits)}%`;
  }

  function date(iso, opts = { month: 'short', day: 'numeric', year: 'numeric' }) {
    return new Date(iso).toLocaleDateString('en-US', opts);
  }

  function relativeTime(iso) {
    const diffSec = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (diffSec < 60) return 'just now';
    const mins = Math.round(diffSec / 60);
    if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
    const days = Math.round(hours / 24);
    if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`;
    const months = Math.round(days / 30);
    return `${months} month${months === 1 ? '' : 's'} ago`;
  }

  function escapeHtml(str) {
    return String(str ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  return { number, pct, date, relativeTime, escapeHtml };
})();
