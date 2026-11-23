// Patient side of the clinic server: the link the clinician sends carries a one-time token in the
// URL fragment (never sent to the server in the request line, so it stays out of access logs). The
// page runs the same interview as the prototype (app.js in patient mode) and, at the end or when a
// red flag stops it, sends the answers. The token can only send; nothing comes back to this page.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var KEY = "tcm_intake_token";
  var token = (location.hash || "").replace(/^#/, "");
  if (token) {
    try { sessionStorage.setItem(KEY, token); } catch (e) { /* private mode: keep it in memory */ }
    history.replaceState(null, "", location.pathname);   // out of the address bar and the history
  } else {
    try { token = sessionStorage.getItem(KEY) || ""; } catch (e) { token = ""; }
  }
  window.TCM_MODE = "patient";

  function closed(text) {
    var chat = document.getElementById("chat");
    chat.textContent = "";
    var m = document.createElement("div");
    m.className = "panel closed";
    m.textContent = text;
    chat.appendChild(m);
  }

  var NOT_OPEN = "הקישור הזה כבר לא פעיל: השאלון כבר נשלח, או שתוקף הקישור פג. אם צריך, בקשו מהמטפל/ת קישור חדש.";
  document.addEventListener("DOMContentLoaded", function () {
    if (!token) return closed("כדי למלא את השאלון צריך את הקישור האישי שקיבלת מהמטפל/ת.");
    fetch(API + "/patient/intake", { headers: { Authorization: "Bearer " + token } }).then(function (r) {
      if (!r.ok) closed(r.status === 410 || r.status === 401 ? NOT_OPEN : "השרת של הקליניקה לא זמין כרגע. נסו שוב מאוחר יותר.");
    }, function () { closed("השרת של הקליניקה לא זמין כרגע. נסו שוב מאוחר יותר."); });
  });

  function send(state) {
    return fetch(API + "/patient/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-TCM": "1", Authorization: "Bearer " + token },
      body: JSON.stringify({ state: state, created_at: new Date().toISOString() })
    }).then(function (r) { if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; } });
  }

  window.TCMPatient = {
    submit: function (state, ui) {
      var m = ui.say("שולח את התשובות למטפל/ת…");
      function attempt() {
        send(state).then(function () {
          m.textContent = "התשובות נשלחו למטפל/ת. תודה! אפשר לסגור את הדף.";
          try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
        }, function (e) {
          if (e.status === 410) { m.textContent = NOT_OPEN; return; }
          m.textContent = "השליחה לא הצליחה. התשובות עדיין בדף הזה.";
          var retry = ui.el("button", { class: "btn", type: "button", text: "לנסות שוב" });
          var p = ui.panel([retry]);
          retry.addEventListener("click", function () { p.remove(); m.textContent = "שולח שוב…"; attempt(); });
        });
      }
      attempt();
    }
  };
})();
