/* reveal.js — drop-in scroll reveal for Theme Pack 24 (CERAMIC, restrained).
   Markup: <section data-reveal="theme" data-reveal-index="0">…</section>
     data-reveal        keyframe name, or "theme" to use the theme's --tp-reveal
     data-reveal-index  stagger position (index x --tp-stagger)
     data-reveal-dur    override --tp-dur-slow
   Put data-reveal-root on a scroll container to observe inside it instead of the viewport.
   Reveals fire once. Nav, tab bars and above-the-fold app chrome must never carry data-reveal.
   Loaded as a plain script (no bundler); it initialises itself once the document is parsed. */

(function () {
  "use strict";

  function initReveals(scope) {
    scope = scope || document;
    if (!window.IntersectionObserver) return function () {};

    var root = scope.documentElement || scope;
    var groups = new Map();

    scope.querySelectorAll("[data-reveal]").forEach(function (el) {
      el.style.animation = "none";
      el.style.opacity = "0";
      var scroller = el.closest("[data-reveal-root]") || null;
      if (!groups.has(scroller)) groups.set(scroller, []);
      groups.get(scroller).push(el);
    });

    var observers = [];

    groups.forEach(function (els, scroller) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            var el = entry.target;
            var cs = getComputedStyle(root);
            var name =
              el.dataset.reveal === "theme"
                ? cs.getPropertyValue("--tp-reveal").trim() || "tp-up"
                : el.dataset.reveal;
            var dur =
              el.dataset.revealDur || cs.getPropertyValue("--tp-dur-slow").trim() || "500ms";
            var ease = cs.getPropertyValue("--tp-ease").trim() || "ease";
            var stagger = parseFloat(cs.getPropertyValue("--tp-stagger")) || 60;
            var index = Number(el.dataset.revealIndex || 0);
            el.style.opacity = "";
            el.style.animation =
              name + " " + dur + " " + ease + " " + Math.round(index * stagger) + "ms both";
            observer.unobserve(el);
          });
        },
        { root: scroller, threshold: 0.2 }
      );
      els.forEach(function (el) {
        observer.observe(el);
      });
      observers.push(observer);
    });

    return function () {
      observers.forEach(function (o) {
        o.disconnect();
      });
    };
  }

  window.initReveals = initReveals;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initReveals(document);
    });
  } else {
    initReveals(document);
  }
})();
