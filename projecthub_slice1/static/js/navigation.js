(function () {
  "use strict";

  var button = document.querySelector(".nav-toggle");
  var menu = document.querySelector("#main-nav");
  if (!button || !menu) return;

  document.documentElement.classList.add("nav-js");

  function setMenuOpen(open) {
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    menu.classList.toggle("is-open", open);
  }

  button.addEventListener("click", function () {
    setMenuOpen(button.getAttribute("aria-expanded") !== "true");
  });

  menu.addEventListener("click", function (event) {
    if (event.target.closest("a, button")) setMenuOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
      setMenuOpen(false);
      button.focus();
    }
  });

})();
