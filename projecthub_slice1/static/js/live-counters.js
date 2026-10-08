// Live counters: refresh the portal counters and the Alerts count without reloading the page.
// Loaded only for admin and coordinator accounts. Asks /api/summary/ every 30 seconds while the
// tab is visible, pauses while it is hidden, and stops for good on 401/403 (signed out or no access).
(function () {
  "use strict";
  var script = document.currentScript;
  var url = script && script.dataset.summaryUrl;
  if (!url || !window.fetch) return;

  var INTERVAL_MS = 30000;
  var timer = null;
  var stopped = false;

  function setCounter(name, value) {
    document.querySelectorAll('[data-counter="' + name + '"]').forEach(function (element) {
      element.textContent = String(value);
      if (name === "unread_notifications") element.hidden = value === 0;
    });
  }

  function apply(summary) {
    Object.keys(summary.counters || {}).forEach(function (name) {
      setCounter(name, summary.counters[name]);
    });
    var unread = summary.unread_notifications || 0;
    setCounter("unread_notifications", unread);
    document.querySelectorAll("[data-alerts-link]").forEach(function (link) {
      link.setAttribute("aria-label", unread ? "Alerts, " + unread + " unread" : "Alerts");
    });
  }

  function schedule() {
    clearTimeout(timer);
    if (!stopped && !document.hidden) timer = setTimeout(poll, INTERVAL_MS);
  }

  function poll() {
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (response) {
        if (response.status === 401 || response.status === 403) {
          stopped = true;
          return null;
        }
        return response.ok ? response.json() : null; // a server error: keep the old numbers, try later
      })
      .then(function (summary) {
        if (summary) apply(summary);
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

  schedule(); // the page already has fresh numbers, so the first request waits 30 seconds
})();
