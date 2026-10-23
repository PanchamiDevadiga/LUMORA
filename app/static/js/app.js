/* LUMORA front-end behaviour (Phase 3). Vanilla JS, no dependencies. */
(function () {
  "use strict";

  // Mobile navigation drawer -------------------------------------------------
  var body = document.body;
  var toggles = document.querySelectorAll("[data-nav-toggle]");

  function setNav(open) {
    body.classList.toggle("nav-open", open);
    toggles.forEach(function (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  toggles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setNav(!body.classList.contains("nav-open"));
    });
  });
  document.querySelectorAll("[data-nav-close]").forEach(function (el) {
    el.addEventListener("click", function () { setNav(false); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && body.classList.contains("nav-open")) {
      setNav(false);
      if (toggles[0]) { toggles[0].focus(); }
    }
  });

  // Show / hide password ------------------------------------------------------
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    var input = document.querySelector(btn.getAttribute("data-toggle-password"));
    if (!input) { return; }
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });

  // Dismissible flash messages -----------------------------------------------
  document.querySelectorAll("[data-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = btn.closest(".flash");
      if (target) { target.remove(); }
    });
  });

  // Loading state on submit (prevents accidental double submission) ----------
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector("[type=submit]");
      if (!btn || form.dataset.submitted === "1") { return; }
      form.dataset.submitted = "1";
      // Defer so the browser still includes the button in the submission.
      setTimeout(function () { btn.classList.add("is-loading"); btn.setAttribute("aria-busy", "true"); }, 0);
    });
  });
  // Restore buttons when the page is shown again via the back button.
  window.addEventListener("pageshow", function () {
    document.querySelectorAll("form[data-loading]").forEach(function (form) {
      form.dataset.submitted = "0";
      var btn = form.querySelector("[type=submit]");
      if (btn) { btn.classList.remove("is-loading"); btn.removeAttribute("aria-busy"); }
    });
  });
})();
