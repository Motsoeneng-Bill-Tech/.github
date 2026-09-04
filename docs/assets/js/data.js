const DataStore = (() => {
  let promise = null;

  function load() {
    if (!promise) {
      promise = fetch('./data/metrics.json', { cache: 'no-store' }).then((res) => {
        if (!res.ok) throw new Error(`Could not load metrics.json (HTTP ${res.status})`);
        return res.json();
      });
    }
    return promise;
  }

  return { load };
})();
