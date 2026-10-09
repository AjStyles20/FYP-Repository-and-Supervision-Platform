// Hamburger menu (every screen width): open/close with the button, close on Escape, on a click
// outside the menu, or after choosing a link.
(function () {
  "use strict";

  var button = document.querySelector(".nav-toggle");
  var menu = document.querySelector("#main-nav");
  if (!button || !menu) return;

  document.documentElement.classList.add("nav-js");

  function isOpen() {
    return button.getAttribute("aria-expanded") === "true";
  }

  function setMenuOpen(open) {
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    menu.classList.toggle("is-open", open);
    if (open) {
      var first = menu.querySelector("a, button");
      if (first) first.focus();
    }
  }

  button.addEventListener("click", function () {
    setMenuOpen(!isOpen());
  });

  menu.addEventListener("click", function (event) {
    if (event.target.closest("a, button")) setMenuOpen(false);
  });

  document.addEventListener("click", function (event) {
    if (isOpen() && !menu.contains(event.target) && !button.contains(event.target)) setMenuOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isOpen()) {
      setMenuOpen(false);
      button.focus();
    }
  });
})();
