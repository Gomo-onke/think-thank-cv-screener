/*  Think Tank chat - add the chatbot to ANY website with one line, just before </body>:

      <script src="https://YOUR-PORTAL-ADDRESS/static/embed.js" async></script>

    Optional attributes on that tag:  data-label="Chat with us"   data-position="left"   data-color="#1D4ED8"
    The chat window is the portal's own /chat-widget page shown in a frame, so the answers always come from the
    questions you edit under Admin > Chatbot. The host page's scripts and styles cannot reach into it.            */
(function () {
  "use strict";
  var tag = document.currentScript;
  if (!tag || !tag.src || window.__ttChatLoaded) return;
  window.__ttChatLoaded = true;
  var origin;
  try { origin = new URL(tag.src).origin; } catch (e) { return; }
  var label = tag.getAttribute("data-label") || "Chat with us";
  var left = tag.getAttribute("data-position") === "left";
  var color = tag.getAttribute("data-color") || "#1D4ED8";
  if (!(window.CSS && CSS.supports && CSS.supports("color", color))) color = "#1D4ED8";

  var button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", "tt-chat-frame");
  var frame = document.createElement("iframe");
  frame.id = "tt-chat-frame";
  frame.title = "Chat assistant";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
  frame.hidden = true;
  frame.loading = "lazy";

  function put(el, css) { for (var k in css) el.style.setProperty(k, css[k], "important"); }
  var mobile = window.matchMedia ? window.matchMedia("(max-width: 480px)") : { matches: false };
  function layout() {
    var shown = button.style.getPropertyValue("display");
    button.removeAttribute("style"); frame.removeAttribute("style");          // start clean after a resize
    if (shown) button.style.setProperty("display", shown, "important");
    put(button, { position: "fixed", bottom: "20px", "z-index": "2147483000", border: "0", background: color, color: "#fff",
      font: "700 15px/1.2 system-ui, -apple-system, Segoe UI, Arial, sans-serif", padding: "14px 20px", "border-radius": "999px",
      cursor: "pointer", "box-shadow": "0 4px 14px rgba(0,0,0,.3)", left: left ? "20px" : "auto", right: left ? "auto" : "20px" });
    put(frame, mobile.matches
      ? { position: "fixed", inset: "0", width: "100%", height: "100%", border: "0", "border-radius": "0" }
      : { position: "fixed", bottom: "84px", width: "380px", "max-width": "calc(100vw - 24px)", height: "560px",
          "max-height": "calc(100vh - 110px)", border: "0", "border-radius": "14px", "box-shadow": "0 8px 30px rgba(0,0,0,.35)",
          background: "#fff", left: left ? "20px" : "auto", right: left ? "auto" : "20px" });
    put(frame, { "z-index": "2147483001", display: frame.hidden ? "none" : "block" });
  }
  function show(open) {
    frame.hidden = !open;
    if (open && !frame.src) frame.src = origin + "/chat-widget";
    button.setAttribute("aria-expanded", open ? "true" : "false");
    button.style.setProperty("display", open && mobile.matches ? "none" : "block", "important");
    layout();
  }
  button.addEventListener("click", function () { show(frame.hidden); });
  window.addEventListener("message", function (e) {       // only our own frame may close it
    if (e.origin === origin && e.data && e.data.type === "tt-chat-close") show(false);
  });
  if (mobile.addEventListener) mobile.addEventListener("change", function () { show(!frame.hidden); });
  function mount() { document.body.appendChild(frame); document.body.appendChild(button); layout(); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
