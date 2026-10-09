// Portal greeting: "Good morning / afternoon / evening" from the viewer's own device clock.
// The server already wrote one for Lagos time; this corrects it to the device's time and checks
// again every minute, so a page left open changes from morning to afternoon on its own.
// The hour bands must match part_of_day() in apps/accounts/templatetags/greeting.py.
(function () {
  "use strict";
  var targets = document.querySelectorAll("[data-greeting]");
  if (!targets.length) return;

  function salutation(hour) {
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }

  function update() {
    var text = salutation(new Date().getHours());
    targets.forEach(function (element) {
      if (element.textContent !== text) element.textContent = text;
    });
  }

  update();
  setInterval(update, 60000);
})();
