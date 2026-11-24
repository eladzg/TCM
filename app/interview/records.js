// Clinician side of the clinic server (server/app.py): sign-in, the record list, new patient links,
// and saving the review, the diagnostic report and the treatment plan to an encrypted record.
// Without a server (GitHub Pages, a file opened from disk) /api/health fails and nothing here shows.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var STATUS_HE = { awaiting_patient: "ממתין למטופל", submitted: "התקבל, טרם נפתח", in_review: "בטיפול", closed: "סגור" };
  var active = null;     // {record_id, identity, ...} of the record open in the clinician view
  var view, bar, tab;

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function call(method, path, data) {
    var opts = { method: method, credentials: "same-origin", headers: { "X-TCM": "1" } };
    if (data !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(data); }
    return fetch(API + path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.detail || ("HTTP " + r.status)); e.status = r.status; throw e; }
        return j;
      });
    });
  }

  function when(ts) {
    if (!ts) return "";
    var d = new Date(ts * 1000);
    return d.toLocaleDateString("he-IL") + " " + d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  }

  // ---- tabs ----
  function showRecords() {
    document.querySelectorAll("nav.tabs button").forEach(function (b) { b.setAttribute("aria-selected", b === tab); });
    document.getElementById("view-patient").hidden = true;
    document.getElementById("view-clin").hidden = true;
    view.hidden = false;
    refresh();
  }

  function install() {
    var nav = document.querySelector("nav.tabs");
    tab = el("button", { role: "tab", id: "tab-records", "aria-selected": "false", type: "button", text: "תיקים", onclick: showRecords });
    nav.insertBefore(tab, nav.firstChild);
    ["tab-patient", "tab-clin"].forEach(function (id) {
      document.getElementById(id).addEventListener("click", function () { view.hidden = true; tab.setAttribute("aria-selected", "false"); });
    });
    view = el("section", { id: "view-records", hidden: "" });
    bar = el("div", { class: "panel recbar", id: "record-bar", hidden: "" });
    nav.parentNode.insertBefore(bar, nav.nextSibling);
    nav.parentNode.insertBefore(view, bar.nextSibling);
    window.addEventListener("tcm:record-closed", function () { active = null; bar.hidden = true; });
    var css = document.createElement("style");
    css.textContent = ".recbar[hidden],#view-records[hidden]{display:none}.recbar{position:sticky;top:0;z-index:3;border-color:var(--jade)}" +
      ".recbar .row{justify-content:space-between}.reclink{direction:ltr;unicode-bidi:isolate;font-family:var(--font-mono);font-size:.8rem;word-break:break-all}" +
      "table.records{border-collapse:collapse;width:100%;font-size:.92rem}table.records th{text-align:start;color:var(--muted);font-weight:600;font-size:.8rem;border-bottom:1px solid var(--line);padding:4px 6px}" +
      "table.records td{border-bottom:1px solid var(--line);padding:6px;vertical-align:middle}.badge{font-size:.78rem;border-radius:999px;padding:1px 8px;background:var(--jade-soft);color:var(--jade);white-space:nowrap}" +
      ".badge.red{background:var(--cinnabar-soft);color:var(--cinnabar)}.badge.amber{background:var(--amber-soft);color:var(--amber)}";
    document.head.appendChild(css);
    showRecords();
  }

  // ---- sign-in ----
  function loginForm(msg) {
    view.textContent = "";
    var user = el("input", { type: "text", class: "note", id: "login-user", autocomplete: "username" });
    var pass = el("input", { type: "password", class: "note", id: "login-pass", autocomplete: "current-password" });
    var status = el("span", { class: "progress", role: "status", text: msg || "" });
    var form = el("form", { class: "panel" }, [
      el("h2", { text: "כניסת מטפל/ת" }),
      el("p", { class: "hint", text: "התיקים נשמרים בשרת של הקליניקה, מוצפנים. רק מטפלים עם שם משתמש וסיסמה רואים אותם." }),
      el("label", { class: "field" }, ["שם משתמש", user]),
      el("label", { class: "field" }, ["סיסמה", pass]),
      el("div", { class: "answers" }, [el("button", { class: "btn", type: "submit", text: "כניסה" })]),
      status
    ]);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      status.textContent = "";
      call("POST", "/login", { username: user.value.trim(), password: pass.value }).then(function () { pass.value = ""; refresh(); },
        function (err) { status.textContent = err.status === 429 ? "יותר מדי ניסיונות. נסו שוב בעוד כמה דקות." : "שם משתמש או סיסמה שגויים."; });
    });
    view.appendChild(form);
    user.focus();
  }

  // ---- record list ----
  function refresh() {
    Promise.all([call("GET", "/me"), call("GET", "/records")]).then(function (r) { renderList(r[0].username, r[1].records); }, function (e) {
      if (e.status === 401) loginForm(); else { view.textContent = ""; view.appendChild(el("p", { class: "flag red", text: "השרת לא זמין: " + e.message })); }
    });
  }

  // What a "send in WhatsApp" answer means, shown in box. Connected to the Cloud API, the system sends it
  // itself; Meta's refusal comes back with the reason and a button for sending by hand. Not connected,
  // WhatsApp opens with the message ready (wa.me), as before.
  function openLink(url) { var a = el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }); document.body.appendChild(a); a.click(); a.remove(); }
  function waReason(msg) {
    msg = String(msg || "");
    if (/131047/.test(msg)) return "עברו יותר מ־24 שעות מאז שהנמען כתב למספר הבדיקה של Meta, ולכן Meta לא מעבירה הודעה חופשית. כדי לפתוח חלון של 24 שעות, שלחו מהטלפון של הנמען הודעה כלשהי למספר הבדיקה ונסו שוב.";
    if (/131030/.test(msg)) return "המספר לא ברשימת הנמענים של מספר הבדיקה. מוסיפים אותו ב־Meta, ב־API Setup, בשדה To.";
    if (/code 190|\b190\b|האסימון/.test(msg)) return "האסימון פג או שגוי. צריך להפיק אסימון זמני חדש ולחבר מחדש בלשונית ניהול הקליניקה.";
    if (/^invented/.test(msg)) return "זה מטופל/ת בדוי/ה (050-00000xx), וההדגמה לא שולחת אליו. כדי לנסות, צרו תיק חדש עם המספר שלכם, מספר שנמצא ברשימת הנמענים של מספר הבדיקה.";
    if (/no usable phone/.test(msg)) return "אין בתיק מספר טלפון שאפשר לשלוח אליו.";
    return msg;
  }
  function waResult(o, box) {
    box.textContent = "";
    if (o.blocked && o.blocked.length) { box.textContent = "נחסם, יש בהודעה מילה קלינית: " + o.blocked.join(", "); return o; }
    if (o.sent) {
      box.textContent = "נשלח בוואטסאפ דרך Meta." + (o.test_mode ? " במספר הבדיקה, ההודעה מגיעה רק אם הנמען כתב למספר הבדיקה ב־24 השעות האחרונות. אם לא הגיעה תוך דקה, שלחו מהטלפון שלו הודעה כלשהי למספר הבדיקה ונסו שוב." : "");
      return o;
    }
    if (o.sent === false) {
      box.appendChild(document.createTextNode("לא נשלח: " + waReason(o.error) + " "));
      if (o.link) box.appendChild(el("button", { class: "mini", type: "button", text: "שליחה ידנית בוואטסאפ", onclick: function () { openLink(o.link); } }));
      return o;
    }
    if (o.link) { openLink(o.link); box.textContent = "נפתח בוואטסאפ (המערכת לא מחוברת ל־Cloud API)."; }
    return o;
  }
  // The patient page next to this one: /app/patient.html on the clinic server; on GitHub Pages the
  // demo hands back a full address under the site's own folder (patient_url).
  function patientUrl(res) { return res.patient_url || (location.origin + res.patient_path); }

  function linkBox(res) {
    var url = patientUrl(res);
    var copy = el("button", { class: "btn ghost", type: "button", text: "העתקת הקישור" });
    copy.addEventListener("click", function () {
      try { navigator.clipboard.writeText(url).then(function () { copy.textContent = "הועתק"; }); } catch (e) { /* select by hand */ }
    });
    var wa = el("button", { class: "btn ghost", type: "button", text: "שליחה בוואטסאפ" });
    var waMsg = el("span", { class: "hint", role: "status" });
    wa.addEventListener("click", function () {
      call("POST", "/pm/records/" + res.record_id + "/whatsapp", { template: "intake_link", link: url }).then(function (o) {
        waResult(o, waMsg);
      }, function (e) { waMsg.textContent = e.status === 422 ? "אין מספר טלפון בתיק." : waReason(e.message); });
    });
    return el("div", { class: "flag info" }, [
      el("b", { text: "קישור למטופל לתיק " + res.record_id + " " }),
      "(בתוקף עד " + when(res.expires_at) + ", לשימוש אחד). שלחו אותו למטופל/ת. אחרי השליחה הקישור נסגר, והמטופל/ת לא יכול/ה לראות את התשובות או את הסיכום.",
      el("div", { class: "reclink", text: url }),
      el("div", { class: "answers" }, [copy, wa, waMsg])
    ]);
  }

  function renderList(username, records) {
    view.textContent = "";
    var name = el("input", { type: "text", class: "note", id: "new-name", placeholder: "לא חובה" });
    var phone = el("input", { type: "text", class: "note", id: "new-phone", placeholder: "לא חובה", inputmode: "tel" });
    var out = el("div", {});
    var create = el("button", { class: "btn", type: "button", text: "יצירת תיק וקישור למטופל" });
    create.addEventListener("click", function () {
      var ident = {};
      if (name.value.trim()) ident.name = name.value.trim();
      if (phone.value.trim()) ident.phone = phone.value.trim();
      call("POST", "/records", { identity: Object.keys(ident).length ? ident : null }).then(function (res) {
        name.value = ""; phone.value = "";
        refresh();
        setTimeout(function () { var o = document.getElementById("new-link"); if (o) { o.textContent = ""; o.appendChild(linkBox(res)); } }, 150);
      }, function (e) { out.textContent = "יצירת התיק נכשלה: " + e.message; });
    });
    view.appendChild(el("div", { class: "panel" }, [
      el("div", { class: "row", style: "justify-content:space-between" }, [
        el("h2", { text: "תיק חדש" }),
        el("span", { class: "hint" }, ["מחובר/ת: " + username + " · ",
          el("button", { class: "mini", type: "button", text: "יציאה", onclick: function () { call("POST", "/logout").then(function () { closeRecord(); loginForm(); }); } })])
      ]),
      el("p", { class: "hint", text: "לכל תיק יש מזהה אקראי, והתיק הקליני לא מכיל שם. שם וטלפון, אם תמלאו, נשמרים מוצפנים במפתח נפרד, ולא יוצאים בייצוא הנתונים." }),
      el("div", { class: "row" }, [el("label", { class: "row" }, ["שם: ", name]), el("label", { class: "row" }, ["טלפון: ", phone])]),
      el("div", { class: "answers" }, [create]),
      el("div", { id: "new-link" }, [out])
    ]));
    var table = el("table", { class: "records" }, [el("tr", {}, ["תיק", "שם", "גיל / מין", "מצב", "עודכן", ""].map(function (h) { return el("th", { text: h }); }))]);
    records.forEach(function (r) {
      var actions = el("span", { class: "mini-row" });
      if (r.documents.intake) actions.appendChild(el("button", { class: "mini", type: "button", text: "פתיחה", onclick: function () { openRecord(r.record_id); } }));
      if (window.TCMPractice) actions.appendChild(el("button", { class: "mini", type: "button", text: "כרטיס", onclick: function () { view.hidden = true; window.TCMPractice.card(r.record_id); } }));
      if (r.status === "awaiting_patient") actions.appendChild(el("button", { class: "mini", type: "button", text: "קישור חדש", onclick: function () {
        call("POST", "/records/" + r.record_id + "/link").then(function (res) { var o = document.getElementById("new-link"); o.textContent = ""; o.appendChild(linkBox(res)); o.scrollIntoView({ block: "nearest" }); });
      } }));
      actions.appendChild(el("button", { class: "mini ghost", type: "button", text: "מחיקה", onclick: function () {
        var typed = window.prompt("מחיקה סופית של התיק וכל הגרסאות שלו. להקליד את מזהה התיק לאישור:", "");
        if (typed !== r.record_id) return;
        call("DELETE", "/records/" + r.record_id, { confirm: r.record_id }).then(function () { if (active && active.record_id === r.record_id) closeRecord(); refresh(); });
      } }));
      var badges = el("span", {}, [el("span", { class: "badge" + (r.status === "awaiting_patient" ? " amber" : ""), text: STATUS_HE[r.status] || r.status })]);
      if (r.halted) badges.appendChild(el("span", { class: "badge red", text: " סימן אזהרה" }));
      var sex = r.sex === "F" ? "אישה" : r.sex === "M" ? "גבר" : "";
      table.appendChild(el("tr", {}, [
        el("td", {}, [el("span", { class: "id", text: r.record_id })]),
        el("td", { text: (r.identity && r.identity.name) || "" }),
        el("td", { text: [r.age, sex].filter(Boolean).join(" · ") }),
        el("td", {}, [badges]),
        el("td", { text: when(r.updated_at) }),
        el("td", {}, [actions])
      ]));
    });
    view.appendChild(el("div", { class: "panel" }, [
      el("h2", { text: "תיקים (" + records.length + ")" }),
      records.length ? el("div", { class: "scroll" }, [table]) : el("p", { class: "empty", text: "עוד אין תיקים." })
    ]));
  }

  // ---- an open record ----
  // Standing alerts from the patient card (practice.js) join the record's safety flags: a category C flag
  // per alert, as if the patient had named the medication, and "PREGNANCY" sets the pregnancy status.
  function withAlerts(state, alerts) {
    state = JSON.parse(JSON.stringify(state || {}));
    state.patient = state.patient || {};
    state.flags = (state.flags || []).filter(function (f) { return f.source !== "standing_alert"; });
    (alerts || []).forEach(function (a) {
      if (a.code === "PREGNANCY") { state.patient.pregnancy = "yes"; return; }
      if (a.code === "NEEDLE" || a.code === "OTHER") return;
      state.flags.push({ category: "C", type: a.code.toLowerCase(), gloss_en: a.label, verbatim_he: "התראה קבועה בכרטיס: " + a.label + (a.text ? " · " + a.text : ""),
                         status: "current", source: "standing_alert" });
    });
    return state;
  }

  function openRecord(rid) {
    Promise.all([call("GET", "/records/" + rid), call("GET", "/pm/records/" + rid + "/alerts").catch(function () { return { alerts: [] }; })]).then(function (r) {
      var rec = r[0];
      var src = rec.review ? rec.review.data : rec.intake && rec.intake.data;
      if (!src) return;
      active = rec;
      view.hidden = true;
      tab.setAttribute("aria-selected", "false");
      document.querySelectorAll(".pm-view").forEach(function (v) { v.hidden = true; });
      window.TCMInterviewUI.loadRecord(rid, withAlerts(src.state, r[1].alerts), rec.review ? src.objective : null);
      renderBar(r[1].alerts.length ? "בתיק יש " + r[1].alerts.length + " התראות קבועות, והן נכנסו לבדיקת הבטיחות." : "");
    });
  }

  function closeRecord() {
    active = null;
    bar.hidden = true;
    if (window.TCMInterviewUI.recordId()) window.TCMInterviewUI.closeRecord();
  }

  function renderBar(msg) {
    var rec = active;
    bar.textContent = "";
    bar.hidden = false;
    var status = el("span", { class: "progress", role: "status", text: msg });
    var select = el("select", { "aria-label": "מצב התיק", onchange: function (e) {
      call("PUT", "/records/" + rec.record_id + "/status", { status: e.target.value }).then(function () { rec.status = e.target.value; status.textContent = "המצב עודכן."; });
    } }, Object.keys(STATUS_HE).filter(function (k) { return k !== "awaiting_patient"; }).map(function (k) {
      return el("option", { value: k, text: STATUS_HE[k], selected: rec.status === k ? "selected" : null });
    }));
    var last = rec.plan ? "תכנית טיפול אחרונה: גרסה " + rec.plan.version + " מ-" + when(rec.plan.created_at) : "אין עדיין תכנית שמורה";
    bar.appendChild(el("div", { class: "row" }, [
      el("span", {}, [el("b", { text: "תיק " }), el("span", { class: "id", text: rec.record_id }), (rec.identity && rec.identity.name) ? " · " + rec.identity.name : "",
        el("span", { class: "hint", text: " · " + last })]),
      el("span", { class: "mini-row" }, [
        select,
        el("button", { class: "btn", type: "button", text: "שמירת הסיכום לתיק", onclick: function () {
          status.textContent = "שומר…";
          saveReview().then(function (v) { renderBar("הסיכום נשמר (גרסה " + v + ")."); }, function (e) { status.textContent = "השמירה נכשלה: " + e.message; });
        } }),
        el("button", { class: "btn ghost", type: "button", text: "סגירת התיק", onclick: closeRecord })
      ])
    ]));
    bar.appendChild(status);
  }

  function saveReview() {
    var rid = active.record_id;
    var snap = window.TCMInterviewUI.snapshot();
    return call("POST", "/records/" + rid + "/review", { document: { schema_version: "review.v1", state: snap.state, objective: snap.objective } })
      .then(function () { return call("POST", "/records/" + rid + "/report", { document: snap.report }); })
      .then(function (r) { if (active.status === "submitted") active.status = "in_review"; return r.version; });
  }

  window.TCMRecords = {
    waResult: waResult, waReason: waReason, patientUrl: patientUrl,
    open: openRecord,
    active: function () { return !!active && window.TCMInterviewUI.recordId() === active.record_id; },
    savePlan: function (plan) {
      var rid = active.record_id;
      plan.record_id = rid;
      return saveReview().then(function () { return call("POST", "/records/" + rid + "/plan", { document: plan }); }).then(function (r) {
        active.plan = { version: r.version, created_at: Date.now() / 1000 };
        renderBar("התכנית נשמרה בתיק (גרסה " + r.version + ").");
        return "נשמר בתיק " + rid + ", מוצפן (גרסה " + r.version + "). גרסאות קודמות נשמרות.";
      });
    }
  };

  if (location.protocol === "file:") return;
  fetch(API + "/health", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && j.service === "tcm-clinic-server") install(); }, function () { /* no server: static prototype */ });
})();
