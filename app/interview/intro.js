// The opening screen: the whole body as a cloud of dots, every channel on it, standing in a still
// three-quarter turn (a drag turns it; it comes back to this pose). The system's menu sits along the body:
// each option is a glass pill tied by a hairline to a glowing ring on an acupuncture point (the start at
// the crown, the summary at the chest, the plan at the middle, and so on down), all of them at once.
// It shows once per browser session; the brand in the header brings it back.
(function () {
  "use strict";
  var intro = document.getElementById("intro");
  if (!intro) return;
  var KEY = "tcm-intro-seen";
  var fmt = function (n) { return Number(n).toLocaleString("en-US"); };
  function set(id, n) { var e = document.getElementById(id); if (e && n) e.textContent = fmt(n); }
  set("st-points", window.TCM_POINTS3D ? Object.keys(window.TCM_POINTS3D).length : 0);
  set("st-patterns", window.TCM_KB && window.TCM_KB.syndromes ? window.TCM_KB.syndromes.length : 0);
  set("st-formulas", window.TCM_TX && window.TCM_TX.formulas ? window.TCM_TX.formulas.length : 0);
  set("st-safety", window.TCM_TX && window.TCM_TX.safety ? window.TCM_TX.safety.length : 0);

  var menu = document.getElementById("intro-menu");
  var items = Array.prototype.slice.call(menu.querySelectorAll(".im"));
  var ringsBox = document.getElementById("intro-rings");
  var lines = document.getElementById("intro-lines");
  var stick = document.getElementById("intro-stick");
  var SVG = "http://www.w3.org/2000/svg";
  items.forEach(function (b) {
    b._ring = document.createElement("i");
    ringsBox.appendChild(b._ring);
    b._line = document.createElementNS(SVG, "line");
    lines.appendChild(b._line);
    var on = function (v) { b.classList.toggle("on", v); b._ring.classList.toggle("on", v); b._line.classList.toggle("on", v); };
    b.addEventListener("pointerenter", function () { on(true); });
    b.addEventListener("pointerleave", function () { on(false); });
    b.addEventListener("focus", function () { on(true); });
    b.addEventListener("blur", function () { on(false); });
  });
  items[0]._ring.classList.add("on");

  // Place the pills beside their points. Wide screens: a column on each side of the body, at a steady
  // distance from it; phones: pinned to the screen's edges. Pills on one side never overlap.
  function place(v) {
    var W = stick.clientWidth, H = stick.clientHeight;
    if (!W || !H) return;
    var foot = intro.querySelector(".intro-foot"), fh = foot ? foot.offsetHeight : 60;
    var phone = W < 700, gap = phone ? 8 : 14, top = phone ? 92 : 110, bottom = H - fh - 8;
    lines.setAttribute("viewBox", "0 0 " + W + " " + H);
    var cols = { r: [], l: [] };
    items.forEach(function (b) {
      if (b.hidden) { b._ring.style.display = "none"; b._line.style.display = "none"; return; }
      var side = b.getAttribute("data-side") === "l" ? "l" : "r";
      var p = v.screen(b.getAttribute("data-at"), 1);
      if (b.getAttribute("data-mirror")) {
        var q = v.screen(b.getAttribute("data-at"), -1);
        if (q && p && ((side === "r") ? q.x > p.x : q.x < p.x)) p = q;
      }
      // Every option always shows; one whose point falls off the screen (a hand on a phone) keeps its
      // place in the column without a ring or a line.
      var seen = !!p && p.x > 0 && p.x < W && p.y > H * 0.1 && p.y < bottom - 10;
      b.classList.toggle("in", !!p);
      b._ring.classList.toggle("out", !seen); b._line.classList.toggle("out", !seen);
      if (!p) return;
      var at = seen ? p : { x: Math.max(0, Math.min(W, p.x)), y: Math.max(H * 0.1, Math.min(bottom - 10, p.y)) };
      cols[side].push({ b: b, p: at, h: b.offsetHeight, w: b.offsetWidth, seen: seen });
    });
    ["r", "l"].forEach(function (side) {
      var list = cols[side].sort(function (a, c) { return a.p.y - c.p.y; });
      var y = top;
      list.forEach(function (it) { it.y = Math.max(y, Math.min(it.p.y - it.h / 2, bottom - it.h)); y = it.y + it.h + gap; });
      // If the column ran off the bottom, push it back up.
      for (var i = list.length - 1, lim = bottom; i >= 0; i--) { var it = list[i]; if (it.y + it.h > lim) it.y = lim - it.h; lim = it.y - gap; }
      list.forEach(function (it) {
        var off = phone ? 0 : Math.max(150, Math.min(W * 0.2, 360));
        var x = side === "r"
          ? (phone ? W - 10 - it.w : Math.min(W - 18 - it.w, it.p.x + off))
          : (phone ? 10 : Math.max(18, it.p.x - off - it.w));
        it.b.style.transform = "translate(" + Math.round(x) + "px," + Math.round(it.y) + "px)";
        it.b.style.visibility = "visible";
        var ex = side === "r" ? x : x + it.w, ey = it.y + it.h / 2;
        it.b._ring.style.display = it.seen ? "" : "none"; it.b._line.style.display = it.seen ? "" : "none";
        it.b._ring.style.transform = "translate(" + it.p.x.toFixed(1) + "px," + it.p.y.toFixed(1) + "px)";
        var L = it.b._line;
        L.setAttribute("x1", it.p.x.toFixed(1)); L.setAttribute("y1", it.p.y.toFixed(1));
        L.setAttribute("x2", ex.toFixed(1)); L.setAttribute("y2", ey.toFixed(1));
      });
    });
  }

  // ---- one still pose: the whole body, turned three-quarters, every option on it at once ----
  var CENTRE = -0.075, TURN = 0.55;
  function frame(now) {
    if (!viewer || intro.hidden) return;
    var W = stick.clientWidth || 1, H = stick.clientHeight || 1, aspect = W / H;
    var full = aspect < 0.75 ? 0.38 + (0.75 - aspect) * 0.25 : 0.385;
    viewer.frame(CENTRE + 0.01, full, now, TURN);
  }
  window.addEventListener("resize", function () { frame(true); });

  var viewer = null, flatTimer = 0;
  function flat() { intro.classList.add("flat"); }
  function figure() {
    var B3 = window.TCMHero3D, host = document.getElementById("intro-fig");
    if (viewer || intro.hidden || !host) return;
    if (!B3) { if (!flatTimer) flatTimer = setTimeout(function () { if (!viewer) flat(); }, 6000); return; }
    if (!B3.available) return flat();
    viewer = B3.create(host, {
      height: function () { return stick.clientHeight; },
      onframe: place
    });
    frame(true);
  }

  function open() {
    intro.hidden = false;
    document.body.classList.add("intro-on");
    window.scrollTo(0, 0);
    figure();
    frame(true);
  }
  function close(then) {
    try { sessionStorage.setItem(KEY, "1"); } catch (e) { /* storage off */ }
    var done = function () {
      intro.hidden = true;
      intro.classList.remove("leaving");
      document.body.classList.remove("intro-on");
      window.scrollTo(0, 0);
      if (then) then();
    };
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return done();
    intro.classList.add("leaving");
    setTimeout(done, 380);
  }
  var click = function (id) { var b = document.getElementById(id); if (b) b.click(); };
  var themeLabel = document.getElementById("intro-theme");
  function syncTheme() { if (themeLabel) themeLabel.textContent = document.documentElement.getAttribute("data-theme") === "light" ? "מצב כהה" : "מצב בהיר"; }
  syncTheme();
  var go = {
    start: function () { close(function () { click("tab-patient"); }); },
    demo: function () { close(function () { click("demo"); }); },
    summary: function () { close(function () { click("tab-clin"); }); },
    plan: function () { close(function () { click("tab-clin"); var t = document.getElementById("tx"); if (t) setTimeout(function () { t.scrollIntoView({ block: "start" }); }, 60); }); },
    records: function () { close(function () { click("tab-records"); }); },
    approvals: function () { close(function () { click("tab-approvals"); }); },
    today: function () { close(function () { click("tab-pm-today"); }); },
    cal: function () { close(function () { click("tab-pm-cal"); }); },
    admin: function () { close(function () { click("tab-pm-admin"); }); },
    theme: function () { click("theme-toggle"); syncTheme(); }
  };
  items.forEach(function (b) { b.addEventListener("click", function () { var f = go[b.getAttribute("data-go")]; if (f) f(); }); });

  // Records and approvals exist only with the clinic server (their scripts add the tabs); show them then.
  var nav = document.querySelector("nav.tabs");
  function server() {
    items.forEach(function (b) {
      var g = b.getAttribute("data-go");
      if ((g === "records" || g === "approvals") && document.getElementById("tab-" + g)) b.hidden = false;
      if ((g === "today" || g === "cal" || g === "admin") && document.getElementById("tab-pm-" + g)) b.hidden = false;   // practice.js
    });
    if (viewer && viewer.ready) place(viewer);
  }
  if (nav) new MutationObserver(server).observe(nav, { childList: true });
  server();

  // The brand in the header goes back to the opening screen.
  var brand = document.querySelector("header.top .brand");
  if (brand) {
    brand.setAttribute("role", "button");
    brand.setAttribute("tabindex", "0");
    brand.setAttribute("title", "למסך הפתיחה");
    brand.addEventListener("click", open);
    brand.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  }
  window.addEventListener("tcm-hero3d-ready", figure);

  var seen = false;
  try { seen = sessionStorage.getItem(KEY) === "1"; } catch (e) { /* storage off */ }
  if (!seen && !location.hash) open();
})();
