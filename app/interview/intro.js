// The opening screen: the glass body with every channel, the work's six stations, the numbers in the
// knowledge base, and the way in (start an interview, a sample case, or the records when the clinic
// server answers). It shows once per browser session; the brand in the header brings it back.
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

  var viewer = null;
  function figure() {
    var B3 = window.TCMBody3D, host = document.getElementById("intro-fig");
    if (viewer || !B3 || !B3.available || !host || intro.hidden) return;
    var T = window.TCMTreatment;
    viewer = B3.create(host, {
      hero: true,
      label: T && T.label ? T.label : null,
      height: function (w) { return w < 700 ? Math.max(340, Math.min(window.innerHeight * 0.55, 520)) : Math.max(380, Math.min(window.innerHeight * 0.72, 760)); }
    });
    viewer.show({ acu: [], shiatsu: [], warn: [] });
  }

  function open() {
    intro.hidden = false;
    document.body.classList.add("intro-on");
    window.scrollTo(0, 0);
    figure();
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
  document.getElementById("intro-start").addEventListener("click", function () { close(function () { click("tab-patient"); }); });
  document.getElementById("intro-demo").addEventListener("click", function () { close(function () { click("demo"); }); });
  var rec = document.getElementById("intro-records");
  rec.addEventListener("click", function () { close(function () { click("tab-records"); }); });
  // The records tab exists only with the clinic server (records.js adds it); show the shortcut then.
  var watch = new MutationObserver(function () { if (document.getElementById("tab-records")) { rec.hidden = false; watch.disconnect(); } });
  watch.observe(document.querySelector("nav.tabs"), { childList: true });

  // The brand in the header goes back to the opening screen.
  var brand = document.querySelector("header.top .brand");
  if (brand) {
    brand.setAttribute("role", "button");
    brand.setAttribute("tabindex", "0");
    brand.setAttribute("title", "למסך הפתיחה");
    brand.addEventListener("click", open);
    brand.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
  }
  window.addEventListener("tcm-body3d-ready", figure);

  var seen = false;
  try { seen = sessionStorage.getItem(KEY) === "1"; } catch (e) { /* storage off */ }
  if (!seen && !location.hash) open();
})();
