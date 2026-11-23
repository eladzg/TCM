// Patient side of the practice forms: the clinician's link carries a one-time token in the URL fragment
// (never in the request line, so it stays out of access logs). It opens the consent forms and the MYMOP
// questionnaire the clinician chose, and sends them once. Nothing clinical comes back to this page except
// the patient's own MYMOP problem names from last time, so the follow-up form keeps them.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var KEY = "tcm_forms_token";
  var token = (location.hash || "").replace(/^#/, "");
  if (token) {
    try { sessionStorage.setItem(KEY, token); } catch (e) { /* keep it in memory */ }
    history.replaceState(null, "", location.pathname);
  } else {
    try { token = sessionStorage.getItem(KEY) || ""; } catch (e) { token = ""; }
  }
  var root = document.getElementById("forms");

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c !== null && c !== undefined) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function closed(text) { root.textContent = ""; root.appendChild(el("div", { class: "panel closed", text: text })); }
  var NOT_OPEN = "הקישור הזה כבר לא פעיל: הטפסים כבר נשלחו, או שתוקף הקישור פג. אם צריך, בקשו מהמטפל/ת קישור חדש.";

  function pad() {
    var c = el("canvas", { class: "pad", width: 600, height: 200, "aria-label": "מקום לחתימה" });
    var ctx = c.getContext("2d"), down = false;
    c.inked = false;
    ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.strokeStyle = "#1d2216";
    function p(e) { var r = c.getBoundingClientRect(); return [(e.clientX - r.left) * c.width / r.width, (e.clientY - r.top) * c.height / r.height]; }
    c.addEventListener("pointerdown", function (e) { down = true; c.setPointerCapture(e.pointerId); var q = p(e); ctx.beginPath(); ctx.moveTo(q[0], q[1]); });
    c.addEventListener("pointermove", function (e) { if (!down) return; var q = p(e); ctx.lineTo(q[0], q[1]); ctx.stroke(); c.inked = true; });
    c.addEventListener("pointerup", function () { down = false; });
    c.clear = function () { ctx.clearRect(0, 0, c.width, c.height); c.inked = false; };
    return c;
  }

  function scale(name, label) {
    var opts = [0, 1, 2, 3, 4, 5, 6].map(function (i) {
      return el("label", { class: "opt" }, [el("input", { type: "radio", name: name, value: String(i) }), String(i)]);
    });
    return el("fieldset", { class: "field", style: "border:0;padding:0;margin:0" }, [el("legend", { text: label }), el("div", { class: "scale" }, opts),
      el("div", { class: "ends" }, [el("span", { text: "0 · טוב ככל האפשר" }), el("span", { text: "6 · גרוע ככל האפשר" })])]);
  }
  function val(name) { var x = root.querySelector('input[name="' + name + '"]:checked'); return x ? +x.value : null; }

  function render(info) {
    root.textContent = "";
    var signers = {}, pads = {}, agree = {};
    Object.keys(info.forms).forEach(function (k) {
      var f = info.forms[k];
      agree[k] = el("input", { type: "checkbox" });
      signers[k] = el("input", { type: "text", autocomplete: "name", "aria-label": "שם מלא" });
      pads[k] = pad();
      root.appendChild(el("section", { class: "panel" }, [el("h2", { text: f.title }), el("ul", {}, f.text.map(function (t) { return el("li", { text: t }); })),
        el("label", { class: "opt" }, [agree[k], "קראתי ואני מסכים/ה"]),
        el("label", { class: "field" }, ["שם מלא", signers[k]]),
        el("div", { class: "field" }, [el("span", { text: "חתימה (באצבע או בעכבר)" }), pads[k],
          el("div", {}, [el("button", { class: "btn no", type: "button", text: "ניקוי החתימה", onclick: function () { pads[k].clear(); } })])])]));
    });
    var names = {};
    if (info.mymop) {
      var m = info.mymop, l = info.mymop_labels || {};
      names.symptom1 = el("input", { type: "text", value: l.symptom1 || "", "aria-label": "הבעיה הראשונה" });
      names.symptom2 = el("input", { type: "text", value: l.symptom2 || "", "aria-label": "הבעיה השנייה" });
      names.activity_name = el("input", { type: "text", value: l.activity_name || "", "aria-label": "הפעילות" });
      root.appendChild(el("section", { class: "panel" }, [el("h2", { text: "איך היה השבוע האחרון" }), el("p", { class: "note", text: "שאלון MYMOP קצר. התשובות עוזרות למטפל/ת לראות מה משתנה לאורך הטיפול." }),
        el("label", { class: "field" }, [m.s1, names.symptom1]), scale("s1", "כמה קשה הייתה הבעיה הראשונה?"),
        el("label", { class: "field" }, [m.s2, names.symptom2]), scale("s2", "כמה קשה הייתה הבעיה השנייה?"),
        el("label", { class: "field" }, [m.activity, names.activity_name]), scale("activity", "כמה קשה היה לבצע אותה?"),
        scale("wellbeing", m.wellbeing)]));
    }
    var msg = el("p", { class: "note", role: "status" });
    var send = el("button", { class: "btn", type: "button", text: "שליחה למטפל/ת" });
    send.addEventListener("click", function () {
      var body = { consents: {} };
      var missing = [];
      Object.keys(info.forms).forEach(function (k) {
        if (!agree[k].checked) return;
        if (!pads[k].inked || !signers[k].value.trim()) { missing.push(info.forms[k].title); return; }
        body.consents[k] = { agree: true, signer: signers[k].value.trim(), signature: pads[k].toDataURL("image/png") };
      });
      if (missing.length) { msg.className = "note error"; msg.textContent = "חסרים שם או חתימה ב: " + missing.join(", "); return; }
      if (info.mymop) {
        var d = {};
        ["s1", "s2", "activity", "wellbeing"].forEach(function (k) { var v = val(k); if (v !== null) d[k] = v; });
        Object.keys(names).forEach(function (k) { if (names[k].value.trim()) d[k] = names[k].value.trim(); });
        if (d.s1 === undefined || d.wellbeing === undefined) { msg.className = "note error"; msg.textContent = "בשאלון צריך לסמן לפחות את הבעיה הראשונה ואת ההרגשה הכללית."; return; }
        body.mymop = d;
      }
      send.disabled = true;
      msg.className = "note"; msg.textContent = "שולח…";
      fetch(API + "/forms", { method: "POST", headers: { "Content-Type": "application/json", "X-TCM": "1", Authorization: "Bearer " + token }, body: JSON.stringify(body) })
        .then(function (r) {
          if (r.status === 410) return closed(NOT_OPEN);
          if (!r.ok) throw new Error("HTTP " + r.status);
          try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
          closed("הטפסים נשלחו. תודה! אפשר לסגור את הדף.");
        }).catch(function () { send.disabled = false; msg.className = "note error"; msg.textContent = "השליחה לא הצליחה. הטפסים עדיין כאן, אפשר לנסות שוב."; });
    });
    root.appendChild(el("div", { class: "panel" }, [el("p", { class: "note", text: "טופס שלא סימנת בו \"מסכים/ה\" לא יישלח, ואפשר לחתום עליו בקליניקה." }), el("div", {}, [send]), msg]));
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!token) return closed("כדי למלא את הטפסים צריך את הקישור האישי שקיבלת מהמטפל/ת.");
    fetch(API + "/forms", { headers: { Authorization: "Bearer " + token } }).then(function (r) {
      if (!r.ok) return closed(r.status === 410 || r.status === 401 ? NOT_OPEN : "השרת של הקליניקה לא זמין כרגע. נסו שוב מאוחר יותר.");
      return r.json().then(render);
    }, function () { closed("השרת של הקליניקה לא זמין כרגע. נסו שוב מאוחר יותר."); });
  });
})();
