// Year filter as a calendar-style year grid. The native <select data-year-picker> stays in the
// form (it still submits the value, and works on its own without JavaScript); this script hides
// it and shows a button that opens a panel of twelve years. Years with projects are clickable,
// the others are greyed out. Keys: arrows move, Enter picks, Escape closes.
(function () {
  "use strict";

  document.querySelectorAll("select[data-year-picker]").forEach(function (select) {
    var available = {};
    Array.prototype.forEach.call(select.options, function (option) {
      if (option.value) available[option.value] = true;
    });
    var allLabel = select.options[0] ? select.options[0].textContent : "All years";
    var thisYear = new Date().getFullYear();

    var wrapper = document.createElement("div");
    wrapper.className = "year-picker";
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    select.classList.add("year-picker-native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.id = select.id + "-button";
    toggle.className = "year-picker-toggle";
    toggle.setAttribute("aria-haspopup", "dialog");
    toggle.setAttribute("aria-expanded", "false");
    wrapper.insertBefore(toggle, select);
    var label = document.querySelector('label[for="' + select.id + '"]');
    if (label) label.htmlFor = toggle.id;

    var panel = document.createElement("div");
    panel.className = "year-picker-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Choose a year");
    panel.hidden = true;
    panel.innerHTML =
      '<div class="year-picker-head">' +
      '<button type="button" class="year-picker-nav" data-step="-10" aria-label="Earlier years">&lsaquo;</button>' +
      '<span class="year-picker-range" aria-live="polite"></span>' +
      '<button type="button" class="year-picker-nav" data-step="10" aria-label="Later years">&rsaquo;</button>' +
      "</div>" +
      '<div class="year-picker-grid"></div>' +
      '<button type="button" class="year-picker-all"></button>';
    wrapper.appendChild(panel);
    var grid = panel.querySelector(".year-picker-grid");
    var range = panel.querySelector(".year-picker-range");
    var allButton = panel.querySelector(".year-picker-all");
    allButton.textContent = allLabel;

    function decadeOf(year) {
      return year - (year % 10);
    }
    var latest = Object.keys(available).map(Number).sort().pop();
    var decade = decadeOf(Number(select.value) || latest || thisYear);

    function showValue() {
      var chosen = select.value;
      toggle.innerHTML =
        '<span class="year-picker-value"></span>' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>';
      toggle.querySelector(".year-picker-value").textContent = chosen || allLabel;
      allButton.setAttribute("aria-pressed", String(!chosen));
    }

    function render() {
      range.textContent = decade + " – " + (decade + 9);
      grid.innerHTML = "";
      // Twelve cells: the ten years of the decade, with one year either side, like a month view.
      for (var year = decade - 1; year <= decade + 10; year++) {
        var cell = document.createElement("button");
        cell.type = "button";
        cell.className = "year-picker-year";
        cell.textContent = year;
        cell.dataset.year = String(year);
        if (year < decade || year > decade + 9) cell.classList.add("is-outside");
        if (year === thisYear) cell.classList.add("is-this-year");
        if (String(year) === select.value) {
          cell.classList.add("is-selected");
          cell.setAttribute("aria-pressed", "true");
        }
        if (!available[String(year)]) {
          cell.disabled = true;
          cell.title = "No projects in " + year;
        }
        grid.appendChild(cell);
      }
    }

    function open() {
      decade = decadeOf(Number(select.value) || latest || thisYear);
      render();
      panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      var target = grid.querySelector(".is-selected") || grid.querySelector(".year-picker-year:not([disabled])") || allButton;
      target.focus({ preventScroll: true });
    }

    function close(returnFocus) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      if (returnFocus) toggle.focus();
    }

    function choose(value) {
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      showValue();
      close(true);
    }

    toggle.addEventListener("click", function () {
      if (panel.hidden) open();
      else close(false);
    });

    panel.addEventListener("click", function (event) {
      var nav = event.target.closest(".year-picker-nav");
      if (nav) {
        decade += Number(nav.dataset.step);
        render();
        return;
      }
      var cell = event.target.closest(".year-picker-year");
      if (cell && !cell.disabled) choose(cell.dataset.year);
      if (event.target === allButton) choose("");
    });

    panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
        return;
      }
      var moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -4, ArrowDown: 4 };
      if (!(event.key in moves) || !event.target.classList.contains("year-picker-year")) return;
      event.preventDefault();
      var cells = Array.prototype.slice.call(grid.querySelectorAll(".year-picker-year"));
      var index = cells.indexOf(event.target) + moves[event.key];
      // Step over greyed years in the direction of travel.
      while (index >= 0 && index < cells.length && cells[index].disabled) index += moves[event.key] > 0 ? 1 : -1;
      if (index >= 0 && index < cells.length) cells[index].focus({ preventScroll: true });
    });

    document.addEventListener("click", function (event) {
      if (!panel.hidden && !wrapper.contains(event.target)) close(false);
    });

    showValue();
  });
})();
