// The figure that stays with the reader through the whole system: the same cloud of dots as the opening
// screen, living in the page itself: on wide screens it stands in the open space beside the content and
// fades into it, on narrow ones it is a faint backdrop. It follows the
// page as it scrolls (head at the top, legs further down) and answers what is on the page: on the
// clinician summary the points of the treatment plan pulse on it and their channels lead, with their
// codes beside them. The treatment plan asks for this through TCMCompanion.focus().
(function () {
  "use strict";
  var aside = document.getElementById("companion");
  if (!aside) return;
  var fig = aside.querySelector(".comp-fig"), tags = aside.querySelector(".comp-tags"), cap = aside.querySelector(".comp-cap b");
  var wide = window.matchMedia ? matchMedia("(min-width: 1100px)") : { matches: false };
  var clin = document.getElementById("view-clin");
  var viewer = null, want = null, wantTitle = "", CENTRE = -0.075;

  function smooth(a) { return a * a * (3 - 2 * a); }
  function frame(now) {
    if (!viewer) return;
    var room = document.documentElement.scrollHeight - window.innerHeight;
    var t = room > 0 ? Math.max(0, Math.min(1, window.scrollY / room)) : 0;
    var aspect = (fig.clientWidth || 1) / (fig.clientHeight || 1);
    var full = aspect < 0.75 ? 0.38 + (0.75 - aspect) * 0.25 : 0.385;
    viewer.frame(-0.035 - smooth(t) * 0.085, full * 0.72, now, 0);
  }
  // Where the figure stands: the middle of the open space left of the content (the content leans right on
  // wide screens); never closer to the edge than a fifth of the screen.
  var page = document.querySelector(".wrap");
  function stand() {
    if (!viewer) return;
    var W = window.innerWidth, x = null;
    if (wide.matches && page) {
      var left = page.getBoundingClientRect().left;
      x = Math.round(Math.max(W * 0.2, Math.min(W * 0.5, left * 0.5)));
    }
    viewer.shift(x);
    aside.style.setProperty("--fig-x", x === null ? "50%" : x + "px");
  }
  if (page && window.ResizeObserver) new ResizeObserver(stand).observe(page);
  window.addEventListener("resize", stand);
  var ticking = false;
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(function () { ticking = false; frame(false); }); } }, { passive: true });

  // Codes of the focused points beside them (the patient's right side and the midline).
  var tagEls = {};
  function place(v) {
    if (!wide.matches || !want) { tags.hidden = true; return; }
    tags.hidden = false;
    var W = fig.clientWidth, H = fig.clientHeight;
    Object.keys(tagEls).forEach(function (id) {
      var p = v.screen(id, 1), e = tagEls[id];
      if (!p || p.x < 0 || p.x > W || p.y < 0 || p.y > H) { e.style.visibility = "hidden"; return; }
      e.style.visibility = "visible";
      e.style.transform = "translate(" + Math.round(p.x + 8) + "px," + Math.round(p.y - 9) + "px)";
    });
  }
  function apply() {
    var on = want && clin && !clin.hidden;
    if (viewer) viewer.focus(on ? want : null);
    tags.textContent = ""; tagEls = {};
    if (on) (want.acu || []).concat(want.shiatsu || []).forEach(function (id) {
      if (tagEls[id]) return;
      var e = document.createElement("span");
      e.textContent = id;
      if ((want.warn || []).indexOf(id) >= 0) e.className = "warn";
      tags.appendChild(e); tagEls[id] = e;
    });
    if (cap) {
      var n = on ? Object.keys(tagEls).length : 0;
      cap.textContent = n ? (wantTitle || "נקודות התכנית") + ": " + n + " נקודות, הערוצים שלהן מודגשים" : "14 מרידיאנים · 361 נקודות";
    }
  }
  if (clin) new MutationObserver(apply).observe(clin, { attributes: true, attributeFilter: ["hidden"] });

  function start() {
    var H = window.TCMHero3D;
    if (viewer || !H) return;
    if (!H.available) { aside.hidden = true; return; }
    viewer = H.create(fig, { height: function () { return fig.clientHeight; }, onframe: place });
    frame(true);
    stand();
    apply();
  }
  window.addEventListener("tcm-hero3d-ready", start);
  start();

  window.TCMCompanion = {
    // True when the figure has its own column (wide screens), so a block can lean on it instead of
    // drawing a figure of its own.
    column: function () { return wide.matches && !!window.TCMHero3D && window.TCMHero3D.available; },
    focus: function (sel, title) { want = sel && ((sel.acu || []).length || (sel.shiatsu || []).length) ? sel : null; wantTitle = title || ""; apply(); }
  };
})();
