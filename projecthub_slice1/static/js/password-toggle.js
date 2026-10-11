// Show / hide password: every password field gets an eye button that switches it between hidden
// and visible text. The button says what it will do ("Show password" / "Hide password") to screen
// readers, and the field goes back to hidden when its form is submitted.
(function () {
  "use strict";

  var EYE = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
    '<path fill="none" stroke="currentColor" stroke-width="2" d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/>' +
    '<circle fill="none" stroke="currentColor" stroke-width="2" cx="12" cy="12" r="3"/></svg>';
  var EYE_OFF = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
    '<path fill="none" stroke="currentColor" stroke-width="2" d="M3 3l18 18M10.6 5.1A10.9 10.9 0 0 1 12 5c7 0 11 7 11 7a18.6 18.6 0 0 1-3.2 4.1M6.6 6.6C3.5 8.6 1 12 1 12s4 7 11 7a10.6 10.6 0 0 0 5.4-1.5M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';

  function addToggle(input) {
    if (input.dataset.passwordToggle) return;
    input.dataset.passwordToggle = "on";

    var wrapper = document.createElement("span");
    wrapper.className = "password-field";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "password-toggle";

    function render(visible) {
      input.type = visible ? "text" : "password";
      button.setAttribute("aria-pressed", String(visible));
      button.setAttribute("aria-label", visible ? "Hide password" : "Show password");
      button.title = visible ? "Hide password" : "Show password";
      button.innerHTML = visible ? EYE_OFF : EYE;
    }

    button.addEventListener("click", function () {
      render(input.type === "password");
      input.focus();
    });
    if (input.form) {
      input.form.addEventListener("submit", function () { render(false); });
    }
    render(false);
    wrapper.appendChild(button);
  }

  Array.prototype.forEach.call(document.querySelectorAll('input[type="password"]'), addToggle);
})();
