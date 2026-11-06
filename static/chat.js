/* FAQ chatbot widget. Talks to /api/chat and /api/chat/suggestions. */
(function () {
  "use strict";
  var toggle = document.getElementById("chat-toggle");
  var panel = document.getElementById("chat-panel");
  if (!toggle || !panel) return;
  var log = document.getElementById("chat-log");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var started = false;
  var humanForm = document.getElementById("human-form");
  var humanOpen = document.getElementById("human-open");
  var lastQuestion = "";
  function showHuman(prefill) {
    humanForm.hidden = false; form.hidden = true;
    var m = document.getElementById("human-message");
    if (prefill && !m.value) m.value = prefill;
    document.getElementById("human-name").focus();
  }
  function hideHuman() { humanForm.hidden = true; form.hidden = false; document.getElementById("human-error").textContent = ""; }
  humanOpen.addEventListener("click", function () { showHuman(lastQuestion); });
  document.getElementById("human-cancel").addEventListener("click", hideHuman);
  humanForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var err = document.getElementById("human-error"); err.textContent = "";
    fetch("/api/escalate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      name: document.getElementById("human-name").value, email: document.getElementById("human-email").value,
      message: document.getElementById("human-message").value }) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.ok) { hideHuman(); humanForm.reset(); add(d.message, "bot"); }
        else { err.textContent = d.error || "Sorry, that did not work. Please try again."; }
      }).catch(function () { err.textContent = "Could not reach the server. Please try again."; });
  });

  function add(text, who) {
    var d = document.createElement("div");
    d.className = "msg " + who;
    d.textContent = text;               // textContent: never interpret answers as HTML
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }
  function chips(list) {
    var old = log.querySelector(".chips");
    if (old) old.remove();
    if (!list || !list.length) return;
    var wrap = document.createElement("div");
    wrap.className = "chips";
    list.forEach(function (q) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "chip"; b.textContent = q;
      b.addEventListener("click", function () { ask(q); });
      wrap.appendChild(b);
    });
    log.appendChild(wrap);
    log.scrollTop = log.scrollHeight;
  }
  function ask(text) {
    text = (text || "").trim();
    if (!text) return;
    lastQuestion = text;
    add(text, "user");
    var old = log.querySelector(".chips"); if (old) old.remove();
    fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    }).then(function (r) { return r.json(); })
      .then(function (d) {
        add(d.answer, "bot"); chips(d.suggestions);
        if (d.escalate) { var b = document.createElement("button"); b.type = "button"; b.className = "btn primary sm";
          b.textContent = "Talk to a recruiter"; b.addEventListener("click", function () { showHuman(text); });
          var w = document.createElement("div"); w.className = "chips"; w.appendChild(b); log.appendChild(w); log.scrollTop = log.scrollHeight; }
      })
      .catch(function () { add("Sorry, I could not reach the server. Please try again.", "bot"); });
  }
  function open() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    if (!started) {
      started = true;
      fetch("/api/chat/suggestions").then(function (r) { return r.json(); }).then(function (d) {
        add("Hi! I'm the " + d.org + " assistant. Ask me about applying, interviews, working here or internships.", "bot");
        chips(d.suggestions);
      }).catch(function () { add("Hi! Ask me a question about working here.", "bot"); });
    }
    setTimeout(function () { input.focus(); }, 50);
  }
  function close() {
    panel.hidden = true; toggle.setAttribute("aria-expanded", "false"); toggle.focus();
    try { if (window.parent !== window) window.parent.postMessage({ type: "tt-chat-close" }, "*"); } catch (e) { /* not framed */ }
  }

  toggle.addEventListener("click", function () { panel.hidden ? open() : close(); });
  document.getElementById("chat-close").addEventListener("click", close);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(); });
  form.addEventListener("submit", function (e) { e.preventDefault(); var v = input.value; input.value = ""; ask(v); });
})();
