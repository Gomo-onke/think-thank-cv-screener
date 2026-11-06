/* Inside the embedded frame the chat is always open. The close button only asks the host page to hide the frame. */
(function () {
  "use strict";
  var toggle = document.getElementById("chat-toggle");
  var panel = document.getElementById("chat-panel");
  if (!toggle || !panel) return;
  function reopen() { panel.hidden = false; toggle.setAttribute("aria-expanded", "true"); }
  toggle.click();                                    // opens the panel and shows the greeting
  document.getElementById("chat-close").addEventListener("click", function () { setTimeout(reopen, 0); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") setTimeout(reopen, 0); });
})();
