// Registration status page: ask the server every 30 seconds (shared poll.js) and show the panel
// for the current status. Stops once the registration has been decided.
(function () {
  "use strict";
  var page = document.querySelector("[data-registration-status]");
  if (!page) return;

  function show(status) {
    page.setAttribute("data-registration-status", status);
    page.querySelectorAll("[data-status-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-status-panel") !== status;
    });
  }

  window.ProjectHubPoll(page.getAttribute("data-status-url"), function (data) {
    if (!data.status) return true;
    show(data.status);
    if (data.reason) {
      var reason = page.querySelector("[data-rejection-reason]");
      if (reason) { reason.textContent = data.reason; reason.parentElement.hidden = false; }
    }
    return data.status === "pending"; // keep asking only while nothing has been decided
  });
})();
