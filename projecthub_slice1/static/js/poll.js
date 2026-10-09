// Shared 30-second JSON poller, used by live-counters.js and registration-status.js.
//
//   ProjectHubPoll(url, onData)
//
// Waits 30 seconds (the page was just rendered with fresh data), then fetches `url` every 30
// seconds while the tab is visible. It pauses while the tab is hidden and catches up as soon as
// it is shown again. It stops for good on 401/403/404, or when onData(json) returns false.
// A server error or being offline keeps the current page as it is and simply tries again later.
window.ProjectHubPoll = function (url, onData) {
  "use strict";
  if (!url || !window.fetch) return;

  var INTERVAL_MS = 30000;
  var timer = null;
  var stopped = false;

  function schedule() {
    clearTimeout(timer);
    if (!stopped && !document.hidden) timer = setTimeout(poll, INTERVAL_MS);
  }

  function poll() {
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (response) {
        if (response.status === 401 || response.status === 403 || response.status === 404) {
          stopped = true;
          return null;
        }
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        if (data && onData(data) === false) stopped = true;
      })
      .catch(function () { /* offline: try again next time */ })
      .then(schedule);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      clearTimeout(timer); // no requests while nobody is looking
    } else if (!stopped) {
      poll(); // catch up straight away when the tab comes back
    }
  });

  schedule();
};
