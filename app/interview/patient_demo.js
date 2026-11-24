// Patient pages on GitHub Pages, for the demo: there is no clinic server there, so a demo link (token
// "demo-…", made by demo_server.js) is answered here, in the browser. Nothing is sent or kept anywhere,
// and the page says so. A real token is never touched: it goes to the clinic server as usual.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var FLAG = "tcm-patient-demo";
  var hash = (location.hash || "").replace(/^#/, "");
  var demo = hash ? hash.indexOf("demo-") === 0 : (function () { try { return sessionStorage.getItem(FLAG) === "1"; } catch (e) { return false; } })();
  try { if (hash) sessionStorage.setItem(FLAG, demo ? "1" : "0"); } catch (e) { /* ignore */ }
  if (!demo) return;
  var realFetch = window.fetch.bind(window);
  var D = window.TCM_DEMO_FORMS || null;
  function reply(status, body) { return Promise.resolve(new Response(JSON.stringify(body), { status: status, headers: { "Content-Type": "application/json" } })); }
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var rel = url.indexOf(location.origin) === 0 ? url.slice(location.origin.length) : url;
    var method = ((init && init.method) || "GET").toUpperCase();
    if (rel === API + "/patient/intake") return reply(200, method === "GET" ? { open: true } : { received: true });
    if (rel === API + "/forms") {
      if (method !== "GET") return reply(200, { received: true });
      if (!D) return reply(503, { detail: "no demo forms" });
      return reply(200, { tasks: ["consent:treatment", "consent:privacy", "consent:whatsapp", "mymop"], expires_at: Math.floor(Date.now() / 1000) + 7 * 86400,
                          forms: D.forms, mymop: D.mymop, mymop_labels: {} });
    }
    return realFetch(input, init);
  };
  document.addEventListener("DOMContentLoaded", function () {
    var wrap = document.querySelector(".wrap") || document.body;
    var b = document.createElement("div");
    b.setAttribute("role", "note");
    b.style.cssText = "padding:10px 14px;border-radius:12px;border:1px dashed var(--amber,#b80);background:var(--amber-soft,#fff4d6);font-size:.9rem";
    b.textContent = "הדגמה: זה דף המטופל/ת כפי שייראה בקליניקה. התשובות לא נשלחות לשום מקום ולא נשמרות.";
    wrap.insertBefore(b, wrap.firstChild);
  });
})();
