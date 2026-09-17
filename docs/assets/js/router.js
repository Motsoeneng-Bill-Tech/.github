const Router = (() => {
  let handlers = { overview: null, member: null, project: null };

  function parseHash() {
    const hash = window.location.hash.replace(/^#/, '') || '/';
    const parts = hash.split('/').filter(Boolean);
    if (parts[0] === 'member' && parts[1]) {
      return { view: 'member', key: decodeURIComponent(parts[1]) };
    }
    if (parts[0] === 'project' && parts[1]) {
      return { view: 'project', key: decodeURIComponent(parts.slice(1).join('/')) };
    }
    return { view: 'overview' };
  }

  function dispatch() {
    const route = parseHash();
    if (route.view === 'member' && handlers.member) {
      handlers.member(route.key);
    } else if (route.view === 'project' && handlers.project) {
      handlers.project(route.key);
    } else if (handlers.overview) {
      handlers.overview();
    }
    window.scrollTo(0, 0);
  }

  function init(routeHandlers) {
    handlers = routeHandlers;
    window.addEventListener('hashchange', dispatch);
    dispatch();
  }

  return { init };
})();
