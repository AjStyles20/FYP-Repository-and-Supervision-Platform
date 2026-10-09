// Staff account forms: an Administrator has no department, title or allocation permission, so hide
// those fields while "Administrator" is selected. The server ignores them for administrators anyway;
// without JavaScript the fields simply stay visible.
(function () {
  "use strict";
  var role = document.querySelector('select[name="role"]');
  if (!role) return;
  var rows = document.querySelectorAll("[data-staff-only]");

  function update() {
    var isAdmin = role.value === "admin";
    rows.forEach(function (row) { row.hidden = isAdmin; });
  }

  role.addEventListener("change", update);
  update();
})();
