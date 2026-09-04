const Router = (() => {
  let handlers = { overview: null, member: null };

  function parseHash() {
    const hash = window.location.hash.replace(/^#/, '') || '/';
    const parts = hash.split('/').filter(Boolean);
    if (parts[0] === 'member' && parts[1]) {
      return { view: 'member', login: decodeURIComponent(parts[1]) };
    }
    return { view: 'overview' };
  }

  function dispatch() {
    const route = parseHash();
    if (route.view === 'member' && handlers.member) {
      handlers.member(route.login);
    } else if (handlers.overview) {
      handlers.overview();
    }
    window.scrollTo(0, 0);
  }

  function init({ overview, member }) {
    handlers = { overview, member };
    window.addEventListener('hashchange', dispatch);
    dispatch();
  }

  return { init };
})();
