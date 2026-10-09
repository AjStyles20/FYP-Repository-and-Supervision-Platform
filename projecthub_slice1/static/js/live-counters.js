// Live counters: refresh the Alerts count, and for admins and coordinators the portal counters,
// without reloading the page. Loaded for every signed-in user; the 30-second polling itself
// (pause while hidden, stop on 401/403) is the shared helper in poll.js.
(function () {
  "use strict";
  var script = document.currentScript;
  var url = script && script.dataset.summaryUrl;

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

  window.ProjectHubPoll(url, apply);
})();
