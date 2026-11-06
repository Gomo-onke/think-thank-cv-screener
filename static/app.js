/* Small progressive enhancements. Every page still works without JavaScript. */
(function () {
  "use strict";

  // Confirm dialogs: <form data-confirm="Are you sure?">
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
    // Stop double submits (slow screening + notifications).
    var btn = e.target.querySelector("button[data-busy]");
    if (btn && !e.defaultPrevented) {
      setTimeout(function () { btn.disabled = true; btn.textContent = btn.getAttribute("data-busy"); }, 0);
    }
  });

  // Hiring stage: "Selected" / "Not selected" can email the candidate, so show the tick box and ask before sending.
  var stageForm = document.querySelector("[data-stage-form]");
  if (stageForm) {
    var stageSelect = stageForm.querySelector("select[name=stage]");
    var emailBox = document.getElementById("stage-email-box");
    var emailKind = document.getElementById("stage-email-kind");
    var tick = emailBox.querySelector("input");
    var kind = function () { return stageSelect.options[stageSelect.selectedIndex].getAttribute("data-email") || ""; };
    var showEmail = function () { var k = kind(); emailBox.hidden = !k; emailKind.textContent = k; };
    stageSelect.addEventListener("change", showEmail);
    showEmail();
    stageForm.addEventListener("submit", function (e) {
      if (kind() && tick.checked && !window.confirm("This will email the candidate a '" + kind() + "' message now. Send it?")) {
        e.preventDefault();
      }
    });
  }

  // Intern-only fields follow the chosen position.
  var position = document.getElementById("position");
  var internBox = document.getElementById("intern-fields");
  if (position && internBox) {
    var internName = position.getAttribute("data-intern");
    var sync = function () { internBox.hidden = position.value !== internName; };
    position.addEventListener("change", sync);
    sync();
  }

  // CV: upload / paste tabs.
  var tabs = document.querySelectorAll("[data-tab]");
  if (tabs.length) {
    var show = function (name) {
      tabs.forEach(function (t) { t.setAttribute("aria-selected", String(t.getAttribute("data-tab") === name)); });
      document.querySelectorAll("[data-panel]").forEach(function (p) { p.hidden = p.getAttribute("data-panel") !== name; });
    };
    tabs.forEach(function (t) { t.addEventListener("click", function () { show(t.getAttribute("data-tab")); }); });
    show("upload");
  }

  // Show the chosen file name + warn about oversize files before uploading.
  var file = document.getElementById("cv_file");
  if (file) {
    file.addEventListener("change", function () {
      var max = parseInt(file.getAttribute("data-max-mb") || "10", 10) * 1024 * 1024;
      var out = document.getElementById("cv_file_info");
      if (file.files[0] && file.files[0].size > max) {
        file.value = "";
        if (out) out.textContent = "That file is too large. Please choose a smaller one.";
      } else if (out) {
        out.textContent = file.files[0] ? "Selected: " + file.files[0].name : "";
      }
    });
  }

  // Copy buttons: <button data-copy="#id">
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var el = document.querySelector(b.getAttribute("data-copy"));
      if (!el) return;
      var text = el.value || el.textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(function () {
        var old = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = old; }, 1500);
      }).catch(function () { el.select && el.select(); });
    });
  });
})();
