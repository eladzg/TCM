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

  function linkBox(res) {
    var url = location.origin + res.patient_path;
    var copy = el("button", { class: "btn ghost", type: "button", text: "העתקת הקישור" });
    copy.addEventListener("click", function () {
      try { navigator.clipboard.writeText(url).then(function () { copy.textContent = "הועתק"; }); } catch (e) { /* select by hand */ }
    });
    return el("div", { class: "flag info" }, [
      el("b", { text: "קישור למטופל לתיק " + res.record_id + " " }),
      "(בתוקף עד " + when(res.expires_at) + ", לשימוש אחד). שלחו אותו למטופל/ת. אחרי השליחה הקישור נסגר, והמטופל/ת לא יכול/ה לראות את התשובות או את הסיכום.",
      el("div", { class: "reclink", text: url }),
      el("div", { class: "answers" }, [copy])
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
  function openRecord(rid) {
    call("GET", "/records/" + rid).then(function (rec) {
      var src = rec.review ? rec.review.data : rec.intake && rec.intake.data;
      if (!src) return;
      active = rec;
      view.hidden = true;
      tab.setAttribute("aria-selected", "false");
      window.TCMInterviewUI.loadRecord(rid, src.state, rec.review ? src.objective : null);
      renderBar("");
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
