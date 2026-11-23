// Page chrome for the "earth and moss" design: the light/dark switch (remembered in this browser) and the
// section rail of the clinician summary (a row of pills that follows the reader down the page).
// It only reads the page; the interview, the summary and the plan are drawn by app.js and treatment.js.
(function () {
  "use strict";
  var KEY = "tcm-theme";
  var root = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  function setTheme(t) {
    if (t === "light") root.setAttribute("data-theme", "light"); else root.removeAttribute("data-theme");
    if (btn) {
      btn.setAttribute("aria-pressed", String(t === "light"));
      btn.textContent = t === "light" ? "מצב כהה" : "מצב בהיר";
    }
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { /* storage off */ }
  setTheme(saved === "light" ? "light" : "dark");
  if (btn) btn.addEventListener("click", function () {
    var t = root.getAttribute("data-theme") === "light" ? "dark" : "light";
    setTheme(t);
    try { localStorage.setItem(KEY, t); } catch (e) { /* storage off */ }
  });

  // ---- the section rail of the clinician summary ----
  var clin = document.getElementById("view-clin");
  var nav = document.querySelector("nav.tabs");
  if (!clin || !nav) return;
  var rail = document.createElement("nav");
  rail.className = "rail";
  rail.setAttribute("aria-label", "חלקי הסיכום");
  rail.hidden = true;
  nav.parentNode.insertBefore(rail, nav.nextSibling);

  function short(text) {
    text = text.replace(/\(.*?\)/g, "").replace(/\s+/g, " ").trim();
    var words = text.split(" ");
    return words.length > 3 ? words.slice(0, 3).join(" ") : text;
  }
  // The sections: the summary's own blocks that carry a heading, then the blocks of the treatment plan.
  function sections() {
    var out = [];
    Array.prototype.forEach.call(clin.children, function (c) {
      if (c.classList.contains("dx") || c.tagName === "DETAILS") return;
      if (c.id === "tx") {
        out.push({ node: c, text: "תכנית טיפול" });
        Array.prototype.forEach.call(c.querySelectorAll(".panel > h3:first-child, .panel > .txhead h3, details > summary"), function (h) {
          var host = h.closest(".panel, details");
          if (host && host.parentNode && host.closest("#tx") === c && !host.parentNode.closest("details") && h.textContent.trim())
            out.push({ node: host, text: short(h.textContent) });
        });
        return;
      }
      var h = c.querySelector("h2, h3");
      if (c.classList.contains("grid2")) out.push({ node: c, text: "לשון ודופק" });
      else if (h && h.textContent.trim()) out.push({ node: c, text: short(h.textContent) });
    });
    var seen = {};
    return out.filter(function (s) { if (seen[s.text]) return false; seen[s.text] = 1; return true; }).slice(0, 14);
  }
  var links = [], ticking = false;
  // The pill of the last section whose top has passed the upper part of the screen.
  function mark() {
    ticking = false;
    if (rail.hidden || !links.length) return;
    var cur = links[0];
    links.forEach(function (l) { if (l.node.getBoundingClientRect().top < window.innerHeight * 0.35) cur = l; });
    links.forEach(function (l) { l.a.setAttribute("aria-current", String(l === cur)); });
    if (rail.scrollWidth > rail.clientWidth && cur !== mark.last) cur.a.scrollIntoView({ block: "nearest", inline: "center" });
    mark.last = cur;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(mark); } }, { passive: true });
  function build() {
    rail.textContent = "";
    var list = clin.hidden ? [] : sections();
    rail.hidden = list.length < 3;
    if (rail.hidden) return;
    links = list.map(function (s, i) {
      if (!s.node.id) s.node.id = "sec-" + i;
      var a = document.createElement("a");
      a.href = "#" + s.node.id;
      a.textContent = s.text;
      a.addEventListener("click", function (e) {
        e.preventDefault();
        s.node.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      });
      rail.appendChild(a);
      return { a: a, node: s.node };
    });
    mark();
  }
  var t = 0;
  function later() { clearTimeout(t); t = setTimeout(build, 120); }
  new MutationObserver(later).observe(clin, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  later();
})();
