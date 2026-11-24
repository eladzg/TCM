// Practice management on the clinic server (server/practice.py, whatsapp.py, gcal.py, backup.py):
// the "היום" list, the week calendar (mirroring Google Calendar), the patient card (standing alerts,
// visits and series, visit notes, MYMOP, consent, WhatsApp, payments, timeline) and "ניהול" (statistics,
// WhatsApp, Google, prices, working days, backups).
// Like records.js it shows only when /api/health answers, so GitHub Pages stays a static prototype.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var cfg = null, records = [];
  var views = {}, tabs = {};
  var KIND_HE = {}, STATUS_HE = { booked: "נקבע", confirmed: "אושר", change_requested: "ביקש/ה שינוי", done: "התקיים", no_show: "לא הגיע/ה", cancelled: "בוטל" };
  var Q_HE = { pending: "ממתין", sent: "נשלח", failed: "נכשל", missed: "לא נשלח בזמן", cancelled: "בוטל", skipped_no_consent: "אין הסכמה", blocked: "נחסם (מילה קלינית)", dismissed: "הוסר", sent_by_hand: "נשלח ידנית" };
  var METHOD_HE = { cash: "מזומן", card: "אשראי", transfer: "העברה", bit: "ביט", check: "צ׳ק", other: "אחר" };
  var CONSENT_HE = { treatment: "הסכמה לטיפול", privacy: "שמירת מידע ופרטיות", whatsapp: "הודעות וואטסאפ" };
  var DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"];   // Python weekday order
  var DAYS_SUN = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];  // JS getDay order

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v);
    });
    (children || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) n.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c); });
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
  function local(s) {   // "2026-11-29T16:00" -> "ראשון 29.11 16:00"
    if (!s) return "";
    var d = new Date(s);
    return DAYS_SUN[d.getDay()] + " " + d.getDate() + "." + (d.getMonth() + 1) + " " + s.slice(11, 16);
  }
  function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
  function status(msg, bad) { return el("p", { class: bad ? "flag red" : "progress", role: "status", text: msg }); }
  function fail(box) { return function (e) { box.textContent = ""; box.appendChild(status("לא הצליח: " + e.message, true)); }; }
  function money(n) { return "₪" + Number(n || 0).toLocaleString("he-IL"); }
  function badge(text, kind) { return el("span", { class: "badge" + (kind ? " " + kind : ""), text: text }); }
  function name(r) { return (r && r.identity && r.identity.name) || ""; }
  function recName(rid) { var r = records.filter(function (x) { return x.record_id === rid; })[0]; return name(r) || rid; }
  function select(options, value, attrs) {
    return el("select", attrs || {}, options.map(function (o) { return el("option", { value: o[0], text: o[1], selected: String(o[0]) === String(value) ? "selected" : null }); }));
  }
  function field(label, input) { return el("label", { class: "field" }, [label, input]); }
  function input(type, attrs) { return el("input", Object.assign({ type: type, class: "note" }, attrs || {})); }
  function openLink(url) { var a = el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }); document.body.appendChild(a); a.click(); a.remove(); }
  function kindOptions() { return cfg.kinds.map(function (k) { return [k.kind, k.label + " · " + k.minutes + " דק׳"]; }); }
  function recordOptions(empty) {
    return [["", empty || "בחירת מטופל/ת"]].concat(records.map(function (r) { return [r.record_id, (name(r) || "ללא שם") + " · " + r.record_id]; }));
  }

  // ---- tabs ----
  function show(key, arg) {
    Object.keys(views).forEach(function (k) { views[k].hidden = k !== key; });
    ["view-patient", "view-clin", "view-records"].forEach(function (id) { var v = document.getElementById(id); if (v) v.hidden = true; });
    var bar = document.getElementById("record-bar"); if (bar) bar.hidden = true;
    document.querySelectorAll("nav.tabs button").forEach(function (b) { b.setAttribute("aria-selected", String(tabs[key] === b)); });
    try { history.replaceState(null, "", "#pm-" + key); } catch (e) { /* ignore */ }
    load(key, arg);
  }
  function load(key, arg) {
    var v = views[key];
    v.textContent = "";
    v.appendChild(status("טוען…"));
    Promise.all([call("GET", "/pm/config"), call("GET", "/records")]).then(function (r) {
      cfg = r[0]; records = r[1].records;
      cfg.kinds.forEach(function (k) { KIND_HE[k.kind] = k.label; });
      v.textContent = "";
      ({ today: renderToday, cal: renderCalendar, card: renderCard, admin: renderAdmin })[key](v, arg);
    }, function (e) {
      v.textContent = "";
      if (e.status === 401) {
        v.appendChild(el("div", { class: "panel" }, [el("h2", { text: "צריך להיכנס" }), el("p", { class: "hint", text: "הכניסה נעשית בלשונית תיקים." }),
          el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "לכניסה", onclick: function () { document.getElementById("tab-records").click(); } })])]));
      } else v.appendChild(status("השרת לא זמין: " + e.message, true));
    });
  }

  // ---- today ----
  function renderToday(v, day) {
    day = day || iso(new Date());
    call("GET", "/pm/today?day=" + day).then(function (t) {
      v.textContent = "";
      var d = new Date(day + "T12:00");
      v.appendChild(el("div", { class: "panel" }, [
        el("div", { class: "row", style: "justify-content:space-between" }, [
          el("h2", { text: "היום · " + DAYS_SUN[d.getDay()] + " " + d.toLocaleDateString("he-IL") }),
          el("span", { class: "mini-row" }, [
            el("button", { class: "mini", type: "button", text: "יום קודם", onclick: function () { load("today", iso(addDays(d, -1))); } }),
            el("button", { class: "mini", type: "button", text: "היום", onclick: function () { load("today"); } }),
            el("button", { class: "mini", type: "button", text: "יום הבא", onclick: function () { load("today", iso(addDays(d, 1))); } })])]),
        t.day_off ? el("p", { class: "flag info", text: "יום חופש: " + t.day_off }) : null,
        apptList(t.appointments, function () { load("today", day); })
      ]));
      var todo = [];
      if (t.replies.length) todo.push(section("תשובות של מטופלים בוואטסאפ", t.replies.map(function (r) {
        return el("li", {}, [r.name || "מספר לא מוכר", " · ", r.kind === "button" ? (r.payload === "confirm" ? "אישר/ה את התור" : r.payload === "change" ? "ביקש/ה לשנות את התור" : "לחץ/ה על כפתור") : "כתב/ה הודעה (בכרטיס)",
          " · " + when(r.at) + " ", r.record_id ? cardBtn(r.record_id) : null,
          el("button", { class: "mini", type: "button", text: "טופל", onclick: function () { call("POST", "/pm/replies/" + r.id + "/handled").then(function () { load("today", day); }); } })]);
      })));
      if (t.unsent_messages.length) todo.push(section("הודעות שלא יצאו", t.unsent_messages.map(function (m) {
        var box = el("span", {});
        return el("li", {}, [(m.name || m.record_id) + " · " + (templateLabel(m.template)) + " · " + (Q_HE[m.status] || m.status) + (m.last_error ? " (" + m.last_error + ")" : "") + " ",
          el("button", { class: "mini", type: "button", text: "שליחה ידנית ב־wa.me", onclick: function () {
            call("POST", "/pm/queue/" + m.id + "/manual").then(function (o) { if (o.link) { openLink(o.link); load("today", day); } else box.textContent = "נחסם: " + o.blocked.join(", "); }, fail(box));
          } }),
          el("button", { class: "mini ghost", type: "button", text: "לנסות שוב", onclick: function () { call("POST", "/pm/queue/" + m.id + "/retry").then(function () { load("today", day); }); } }),
          el("button", { class: "mini ghost", type: "button", text: "להסיר", onclick: function () { call("POST", "/pm/queue/" + m.id + "/dismiss").then(function () { load("today", day); }); } }), box]);
      })));
      if (t.intakes_waiting.length) todo.push(section("שאלונים שהתקבלו ומחכים לסקירה", t.intakes_waiting.map(function (r) {
        return el("li", {}, [(r.name || r.record_id) + " · " + when(r.at) + " ", el("button", { class: "mini", type: "button", text: "פתיחת הסיכום", onclick: function () { window.TCMRecords.open(r.record_id); } }), cardBtn(r.record_id)]);
      })));
      if (t.intake_before_first.length) todo.push(section("ביקור ראשון בקרוב, והשאלון עוד לא מולא", t.intake_before_first.map(function (r) {
        var box = el("span", {});
        return el("li", {}, [(r.name || r.record_id) + " · " + local(r.start) + " ", el("button", { class: "mini", type: "button", text: "קישור חדש בוואטסאפ", onclick: function () {
          call("POST", "/records/" + r.record_id + "/link").then(function (res) { return sendWa(r.record_id, "intake_link", { link_path: res.patient_path }, box); }, fail(box));
        } }), box]);
      })));
      if (t.series_ended.length) todo.push(section("סיימו סדרה ואין מפגש המשך", t.series_ended.map(function (r) {
        var box = el("span", {});
        return el("li", {}, [(r.name || r.record_id) + " ", el("button", { class: "mini", type: "button", text: "בדיקת שלומך בוואטסאפ", onclick: function () { sendWa(r.record_id, "followup_check", {}, box); } }), cardBtn(r.record_id), box]);
      })));
      if (t.repeat_no_show.length) todo.push(section("לא הגיעו פעמיים או יותר", t.repeat_no_show.map(function (r) { return el("li", {}, [(r.name || r.record_id) + " · " + r.n + " פעמים ", cardBtn(r.record_id)]); })));
      if (t.in_review.length) todo.push(section("תיקים בטיפול", t.in_review.map(function (r) { return el("li", {}, [(r.name || r.record_id) + " ", cardBtn(r.record_id)]); })));
      if (t.unlinked_events) todo.push(el("p", { class: "flag info" }, [t.unlinked_events + " אירועים מיומן גוגל לא מקושרים לתיק. ", el("button", { class: "mini", type: "button", text: "ליומן", onclick: function () { show("cal"); } })]));
      v.appendChild(el("div", { class: "panel" }, [el("h2", { text: "לטיפול" })].concat(todo.length ? todo : [el("p", { class: "empty", text: "אין משימות פתוחות." })])));
    }, fail(v));
  }
  function section(title, items) { return el("div", {}, [el("h3", { text: title + " (" + items.length + ")" }), el("ul", { class: "pm-list" }, items)]); }
  function cardBtn(rid) { return el("button", { class: "mini", type: "button", text: "כרטיס", onclick: function () { show("card", rid); } }); }
  function templateLabel(id) { var t = (cfg.whatsapp.templates || []).filter(function (x) { return x.id === id; })[0]; return t ? t.label : id; }
  function sendWa(rid, template, extra, box) {
    return call("POST", "/pm/records/" + rid + "/whatsapp", Object.assign({ template: template }, extra || {})).then(function (o) {
      if (o.link) { openLink(o.link); if (box) box.textContent = "נפתח בוואטסאפ."; }
      else if (box) box.textContent = "נחסם, יש בהודעה מילה קלינית: " + o.blocked.join(", ");
      return o;
    }, box ? fail(box) : null);
  }

  // A list of visits with quick status buttons.
  function apptList(appts, reload) {
    if (!appts.length) return el("p", { class: "empty", text: "אין תורים." });
    return el("ul", { class: "pm-appts" }, appts.map(function (a) {
      var box = el("span", {});
      var who = a.record_id ? (a.name || recName(a.record_id)) : (a.external_title || (a.source === "google" ? "אירוע מיומן גוגל" : "ללא תיק"));
      var flags = el("span", { class: "mini-row" });
      (a.alerts || []).forEach(function (c) { flags.appendChild(badge(cfg.alert_codes[c] || c, c === "PREGNANCY" || c === "ANTICOAGULANT" || c === "DEVICE" ? "red" : "amber")); });
      if (a.consent_missing && a.consent_missing.length) flags.appendChild(badge("חסרה הסכמה", "amber"));
      return el("li", { class: "pm-appt st-" + a.status }, [
        el("b", { class: "pm-time", text: a.start.slice(11, 16) }),
        el("span", {}, [who, el("span", { class: "hint", text: " · " + (KIND_HE[a.kind] || a.kind) + (a.series_no ? " · מפגש " + a.series_no : "") }), " ", badge(STATUS_HE[a.status] || a.status, a.status === "change_requested" ? "amber" : a.status === "no_show" ? "red" : ""), " ", flags]),
        el("span", { class: "mini-row" }, [
          a.record_id ? cardBtn(a.record_id) : null,
          el("button", { class: "mini", type: "button", text: "הגיע/ה", onclick: function () { call("PUT", "/pm/appointments/" + a.id, { status: "done" }).then(reload, fail(box)); } }),
          el("button", { class: "mini ghost", type: "button", text: "לא הגיע/ה", onclick: function () { call("PUT", "/pm/appointments/" + a.id, { status: "no_show" }).then(reload, fail(box)); } }),
          a.record_id ? el("button", { class: "mini ghost", type: "button", text: "תזכורת ידנית", onclick: function () { sendWa(a.record_id, "reminder", { appt_id: a.id }, box); } }) : null,
          box])
      ]);
    }));
  }

  // ---- the week calendar ----
  var calStart = null;
  function sunday(d) { return addDays(d, -d.getDay()); }
  function renderCalendar(v) {
    calStart = calStart || sunday(new Date());
    call("GET", "/pm/calendar?start=" + iso(calStart) + "&days=7").then(function (c) {
      v.textContent = "";
      var g = c.gcal;
      var syncBox = el("span", { class: "hint" });
      v.appendChild(el("div", { class: "panel" }, [
        el("div", { class: "row", style: "justify-content:space-between" }, [
          el("h2", { text: "יומן · " + calStart.toLocaleDateString("he-IL") + " עד " + addDays(calStart, 6).toLocaleDateString("he-IL") }),
          el("span", { class: "mini-row" }, [
            el("button", { class: "mini", type: "button", text: "שבוע קודם", onclick: function () { calStart = addDays(calStart, -7); load("cal"); } }),
            el("button", { class: "mini", type: "button", text: "השבוע", onclick: function () { calStart = sunday(new Date()); load("cal"); } }),
            el("button", { class: "mini", type: "button", text: "שבוע הבא", onclick: function () { calStart = addDays(calStart, 7); load("cal"); } })])]),
        el("p", { class: "hint" }, [g.connected ? "מסונכרן עם יומן גוגל" + (g.last_sync ? " · סנכרון אחרון " + local(g.last_sync) : "") + " · " : "יומן גוגל לא מחובר (בלשונית ניהול). ",
          g.connected ? el("button", { class: "mini", type: "button", text: "סנכרון עכשיו", onclick: function () { syncBox.textContent = "מסנכרן…"; call("POST", "/pm/gcal/sync").then(function () { load("cal"); }, fail(syncBox)); } }) : null, syncBox]),
        weekGrid(c),
        newAppt(function () { load("cal"); })
      ]));
    }, fail(v));
  }
  function weekGrid(c) {
    var grid = el("div", { class: "pm-week" });
    for (var i = 0; i < 7; i++) {
      var d = addDays(calStart, i), key = iso(d);
      var work = c.workdays.indexOf((d.getDay() + 6) % 7) !== -1;
      var items = c.appointments.filter(function (a) { return a.start.slice(0, 10) === key; });
      if (!work && !items.length) continue;
      var col = el("div", { class: "pm-day" + (c.days_off[key] ? " off" : "") + (key === iso(new Date()) ? " today" : "") }, [
        el("div", { class: "pm-dayhead" }, [el("b", { text: DAYS_SUN[d.getDay()] }), " " + d.getDate() + "." + (d.getMonth() + 1), c.days_off[key] ? el("span", { class: "hint", text: " · " + c.days_off[key] }) : null])
      ]);
      items.forEach(function (a) { col.appendChild(apptChip(a)); });
      if (!items.length) col.appendChild(el("p", { class: "empty", text: "פנוי" }));
      grid.appendChild(col);
    }
    return grid;
  }
  function apptChip(a) {
    var who = a.record_id ? (a.name || a.record_id) : (a.external_title || "אירוע");
    var det = el("details", { class: "pm-chip st-" + a.status + (a.record_id ? "" : " ext") }, [
      el("summary", {}, [el("b", { text: a.start.slice(11, 16) + " " }), who]),
    ]);
    var box = el("div", {});
    var rec = select(recordOptions("לא מקושר"), a.record_id || "", { "aria-label": "תיק" });
    var st = select(Object.keys(STATUS_HE).map(function (k) { return [k, STATUS_HE[k]]; }), a.status, { "aria-label": "מצב" });
    var at = input("datetime-local", { value: a.start });
    var kind = select(kindOptions(), a.kind, { "aria-label": "סוג" });
    det.appendChild(el("div", { class: "pm-chipbody" }, [
      el("span", { class: "hint", text: (KIND_HE[a.kind] || a.kind) + " · " + a.minutes + " דק׳" + (a.source === "google" ? " · מיומן גוגל" : "") + (a.series_no ? " · מפגש " + a.series_no + " בסדרה" : a.series_id ? " · מעקב אחרי סדרה" : "") }),
      field("תיק", rec), field("מצב", st), field("מועד", at), field("סוג", kind),
      el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "שמירה", onclick: function () {
        var d = {};
        if (rec.value !== (a.record_id || "")) d.record_id = rec.value || null;
        if (st.value !== a.status) d.status = st.value;
        if (at.value && at.value !== a.start) d.start = at.value;
        if (kind.value !== a.kind) d.kind = kind.value;
        call("PUT", "/pm/appointments/" + a.id, d).then(function () { load("cal"); }, fail(box));
      } }), a.record_id ? cardBtn(a.record_id) : null]),
      box
    ]));
    return det;
  }
  function newAppt(done, rid) {
    var box = el("div", {});
    var rec = select(recordOptions(), rid || "", { "aria-label": "תיק" });
    var at = input("datetime-local", { value: iso(addDays(new Date(), 1)) + "T16:00" });
    var kind = select(kindOptions(), "followup", { "aria-label": "סוג ביקור" });
    return el("details", { class: "pm-new" }, [el("summary", { text: "תור חדש" }), el("div", { class: "row" }, [
      rid ? null : field("מטופל/ת", rec), field("מועד", at), field("סוג", kind),
      el("button", { class: "btn", type: "button", text: "קביעה", onclick: function () {
        call("POST", "/pm/appointments", { record_id: rid || rec.value || null, start: at.value, kind: kind.value }).then(done, fail(box));
      } })]), el("p", { class: "hint", text: "התור נכתב ליומן \"קליניקה\" בגוגל בכותרת ניטרלית, ותזכורת וואטסאפ נקבעת ליום העבודה שלפניו (רק אם יש הסכמה)." }), box]);
  }

  // ---- the patient card ----
  function renderCard(v, rid) {
    if (!rid) { v.appendChild(pickRecord()); return; }
    call("GET", "/pm/records/" + rid).then(function (c) {
      v.textContent = "";
      var ident = c.identity || {};
      v.appendChild(el("div", { class: "panel pm-cardhead" }, [
        el("div", { class: "row", style: "justify-content:space-between" }, [
          el("h2", {}, [ident.name || "ללא שם", " ", el("span", { class: "id", text: c.record_id })]),
          el("span", { class: "mini-row" }, [ident.phone ? el("span", { class: "hint", text: ident.phone }) : null,
            c.record.status !== "awaiting_patient" ? el("button", { class: "mini", type: "button", text: "הסיכום הקליני", onclick: function () { window.TCMRecords.open(rid); } }) : null,
            el("button", { class: "mini ghost", type: "button", text: "תיק אחר", onclick: function () { show("card"); } })])]),
        el("nav", { class: "pm-rail" }, [["alerts", "התראות"], ["visits", "תורים וסדרות"], ["notes", "הערות ביקור"], ["mymop", "מדד MYMOP"], ["consent", "הסכמות"], ["wa", "וואטסאפ"], ["pay", "תשלומים"], ["timeline", "ציר זמן"]].map(function (x) {
          return el("a", { href: "#pm-c-" + x[0], text: x[1], onclick: function (e) { e.preventDefault(); var t = document.getElementById("pm-c-" + x[0]); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); } });
        }))
      ]));
      var reload = function () { load("card", rid); };
      [alertsPanel, visitsPanel, notesPanel, mymopPanel, consentPanel, waPanel, payPanel, timelinePanel].forEach(function (f) { v.appendChild(f(c, reload)); });
    }, fail(v));
  }
  function pickRecord() {
    var q = input("search", { placeholder: "חיפוש לפי שם או מספר תיק", "aria-label": "חיפוש" });
    var list = el("ul", { class: "pm-list" });
    function draw() {
      list.textContent = "";
      records.filter(function (r) { var s = q.value.trim(); return !s || (name(r) + " " + r.record_id).indexOf(s) !== -1; }).slice(0, 60).forEach(function (r) {
        list.appendChild(el("li", {}, [el("button", { class: "mini", type: "button", text: (name(r) || "ללא שם") + " · " + r.record_id, onclick: function () { show("card", r.record_id); } })]));
      });
    }
    q.addEventListener("input", draw); draw();
    return el("div", { class: "panel" }, [el("h2", { text: "כרטיס מטופל/ת" }), q, list]);
  }
  function panel(id, title, children) { return el("div", { class: "panel", id: "pm-c-" + id }, [el("h2", { text: title })].concat(children)); }

  function alertsPanel(c, reload) {
    var box = el("div", {});
    var code = select(Object.keys(cfg.alert_codes).map(function (k) { return [k, cfg.alert_codes[k]]; }), "ANTICOAGULANT", { "aria-label": "סוג" });
    var text = input("text", { placeholder: "פירוט (למשל שם התרופה)" });
    return panel("alerts", "התראות קבועות", [
      el("p", { class: "hint", text: "התראה פעילה נכנסת אוטומטית לבדיקת הבטיחות של תוכנית הטיפול כשפותחים את הסיכום הקליני. היריון מסמן את סטטוס ההיריון." }),
      c.alerts.length ? el("ul", { class: "pm-list" }, c.alerts.map(function (a) {
        return el("li", { class: a.active ? "" : "off" }, [badge(a.label, a.active ? (a.code === "PREGNANCY" || a.code === "ANTICOAGULANT" || a.code === "DEVICE" ? "red" : "amber") : ""), " " + (a.text || "") + " ",
          el("button", { class: "mini ghost", type: "button", text: a.active ? "כיבוי" : "הפעלה", onclick: function () {
            call("POST", "/pm/records/" + c.record_id + "/alerts", { alert_id: a.id, code: a.code, text: a.text, active: !a.active }).then(reload, fail(box));
          } })]);
      })) : el("p", { class: "empty", text: "אין התראות." }),
      el("div", { class: "row" }, [code, text, el("button", { class: "btn", type: "button", text: "הוספה", onclick: function () {
        call("POST", "/pm/records/" + c.record_id + "/alerts", { code: code.value, text: text.value }).then(reload, fail(box));
      } })]), box]);
  }

  function visitsPanel(c, reload) {
    var box = el("div", {});
    var now = new Date().toISOString().slice(0, 16);
    var upcoming = c.appointments.filter(function (a) { return a.start >= now.slice(0, 10); });
    var past = c.appointments.filter(function (a) { return a.start < now.slice(0, 10); });
    var start = input("date", { value: iso(addDays(new Date(), 1)) });
    var time = input("time", { value: "16:00" });
    var len = select([[7, "7 מפגשים"], [14, "14 מפגשים"], [5, "5"], [10, "10"]], 7, { "aria-label": "אורך" });
    var per = select([[1, "פעם בשבוע"], [2, "פעמיים בשבוע"]], 1, { "aria-label": "תדירות" });
    var first = el("input", { type: "checkbox" });
    var pkg = select([["", "בלי חבילה"]].concat(c.account.packages.map(function (p) { return [p.id, p.label + " (" + p.used + "/" + p.sessions + ")"]; })), "", { "aria-label": "חבילה" });
    var sendSched = el("input", { type: "checkbox" });
    var prev = el("div", {});
    function preview() {
      call("GET", "/pm/series/preview?start=" + start.value + "&time=" + time.value + "&length=" + len.value + "&per_week=" + per.value).then(function (p) {
        prev.textContent = "";
        prev.appendChild(el("div", { class: "pm-series" }, p.sessions.map(function (s, i) { return el("span", { class: "slot" + (i ? "" : " first") }, [el("b", { text: (i + 1) + "/" + p.sessions.length }), " " + local(s)]); })
          .concat([el("span", { class: "slot fu" }, [el("b", { text: "מעקב" }), " " + local(p.followup)])])));
        if (p.moved.length) prev.appendChild(el("p", { class: "hint", text: "הוזזו: " + p.moved.map(function (m) { return m.from + " (" + m.why + ") ← " + m.to; }).join(" · ") }));
      }, fail(prev));
    }
    [start, time, len, per].forEach(function (x) { x.addEventListener("change", preview); });
    var planV = window.TCMRecords && window.TCMRecords.planVersion ? window.TCMRecords.planVersion(c.record_id) : null;
    var series = el("details", { class: "pm-new" }, [el("summary", { text: "סדרת טיפולים חדשה" }),
      el("div", { class: "row" }, [field("מפגש ראשון", start), field("שעה", time), field("אורך", len), field("תדירות", per), field("חבילה", pkg)]),
      el("label", { class: "opt" }, [first, "המפגש הראשון הוא ביקור ראשון (90 דק׳)"]),
      el("label", { class: "opt" }, [sendSched, "לשלוח למטופל/ת את מועדי המפגשים בוואטסאפ (אוטומטי, רק עם הסכמה)"]),
      prev,
      el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "יצירת הסדרה ביומן", onclick: function () {
        call("POST", "/pm/records/" + c.record_id + "/series", { start: start.value, time: time.value, length: +len.value, per_week: +per.value,
          first_kind: first.checked ? "first" : null, package_id: pkg.value || null, send_schedule: sendSched.checked, plan_version: planV }).then(reload, fail(box));
      } })]), box]);
    series.addEventListener("toggle", function () { if (series.open) preview(); });
    return panel("visits", "תורים וסדרות", [
      c.series.length ? el("p", { class: "hint", text: c.series.map(function (s) { return "סדרה של " + s.length + ", " + (s.per_week === 1 ? "פעם בשבוע" : "פעמיים בשבוע") + ": התקיימו " + s.done; }).join(" · ") }) : null,
      el("h3", { text: "הבאים" }), apptList(upcoming, reload),
      past.length ? el("details", {}, [el("summary", { text: "קודמים (" + past.length + ")" }), apptList(past.slice().reverse(), reload)]) : null,
      newAppt(reload, c.record_id), series]);
  }

  var NOTE_FIELDS = [["complaint", "תלונה ומה השתנה"], ["findings", "מה נמצא"], ["tongue", "לשון"], ["pulse", "דופק"], ["done", "מה נעשה"], ["response", "תגובת המטופל/ת"], ["next", "מה הלאה"], ["tags", "תגיות"]];
  function noteForm(c, reload, note) {
    var box = el("div", {});
    var inputs = {};
    var draftKey = "tcm-note-draft-" + c.record_id + (note ? "-" + note.id : "");
    var saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(draftKey) || "{}"); } catch (e) { saved = {}; }
    var appts = c.appointments.filter(function (a) { return a.status !== "cancelled"; });
    var appt = select([["", "בלי קישור לתור"]].concat(appts.map(function (a) { return [a.id, local(a.start) + " · " + (KIND_HE[a.kind] || a.kind)]; })), note ? note.appt_id : (appts.filter(function (a) { return a.start.slice(0, 10) === iso(new Date()); })[0] || {}).id || "", { "aria-label": "תור" });
    var rows = NOTE_FIELDS.map(function (f) {
      var t = el(f[0] === "tongue" || f[0] === "pulse" || f[0] === "tags" ? "input" : "textarea", { class: "note", type: "text", "aria-label": f[1] });
      t.value = saved[f[0]] !== undefined ? saved[f[0]] : (note && note.data[f[0]]) || "";
      t.addEventListener("input", function () { var d = {}; Object.keys(inputs).forEach(function (k) { d[k] = inputs[k].value; }); try { sessionStorage.setItem(draftKey, JSON.stringify(d)); } catch (e) { /* ignore */ } });
      inputs[f[0]] = t;
      return field(f[1], t);
    });
    return el("div", { class: "pm-note-form" }, [note ? null : field("ביקור", appt), el("div", { class: "grid2" }, rows),
      el("p", { class: "hint", text: "הטיוטה נשמרת בדפדפן הזה עד השמירה. אחרי שמירה אין מחיקה: תיקון נשמר כגרסה חדשה עם תאריך." }),
      el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: note ? "שמירת תיקון (גרסה חדשה)" : "שמירת ההערה", onclick: function () {
        var d = { appt_id: appt.value || null };
        Object.keys(inputs).forEach(function (k) { if (inputs[k].value.trim()) d[k] = inputs[k].value.trim(); });
        call("POST", "/pm/records/" + c.record_id + "/notes", { note: d, note_id: note ? note.id : null }).then(function () {
          try { sessionStorage.removeItem(draftKey); } catch (e) { /* ignore */ }
          reload();
        }, fail(box));
      } })]), box]);
  }
  function notesPanel(c, reload) {
    var list = c.notes.map(function (n) {
      var body = el("div", {});
      NOTE_FIELDS.forEach(function (f) { if (n.data[f[0]]) body.appendChild(el("p", { class: "pm-notefield" }, [el("b", { text: f[1] + ": " }), n.data[f[0]]])); });
      var hist = el("div", {});
      return el("details", { class: "pm-note" }, [el("summary", {}, [when(n.first_at), n.versions > 1 ? el("span", { class: "hint", text: " · " + n.versions + " גרסאות, אחרונה " + when(n.created_at) }) : null, " · ", (n.data.complaint || "").slice(0, 60)]),
        body,
        el("div", { class: "answers" }, [
          el("button", { class: "mini", type: "button", text: "תיקון", onclick: function (e) { e.target.replaceWith(noteForm(c, reload, n)); } }),
          n.versions > 1 ? el("button", { class: "mini ghost", type: "button", text: "גרסאות קודמות", onclick: function () {
            call("GET", "/pm/records/" + c.record_id + "/notes/" + n.id).then(function (h) {
              hist.textContent = "";
              h.history.slice(0, -1).reverse().forEach(function (x) { hist.appendChild(el("div", { class: "src he" }, ["גרסה " + x.version + " · " + when(x.created_at) + ": " + NOTE_FIELDS.filter(function (f) { return x.data[f[0]]; }).map(function (f) { return f[1] + ": " + x.data[f[0]]; }).join(" | ")])); });
            });
          } }) : null]), hist]);
    });
    return panel("notes", "הערות ביקור", [el("details", { class: "pm-new", open: c.notes.length ? null : "" }, [el("summary", { text: "הערה חדשה" }), noteForm(c, reload)])].concat(list.length ? list : [el("p", { class: "empty", text: "עוד אין הערות." })]));
  }

  function chart(outs) {
    var W = 560, H = 190, P = 26;
    var series = [["s1", "בעיה 1", "var(--jade)"], ["s2", "בעיה 2", "var(--amber)"], ["activity", "פעילות", "var(--muted)"], ["wellbeing", "הרגשה כללית", "var(--cinnabar)"]];
    var n = outs.length, x = function (i) { return n < 2 ? W / 2 : P + i * (W - 2 * P) / (n - 1); }, y = function (v) { return H - 10 - v * (H - P - 4) / 6; };
    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" class="pm-chart" role="img" aria-label="מדד MYMOP לאורך הזמן">';
    for (var g = 0; g <= 6; g += 2) svg += '<line x1="' + P + '" x2="' + (W - P) + '" y1="' + y(g) + '" y2="' + y(g) + '" stroke="var(--line)"/><text x="4" y="' + (y(g) + 4) + '" font-size="11" fill="var(--muted)" text-anchor="start" direction="ltr">' + g + "</text>";
    series.forEach(function (s) {
      var pts = outs.map(function (o, i) { return o[s[0]] === null || o[s[0]] === undefined ? null : [x(i), y(o[s[0]])]; }).filter(Boolean);
      if (!pts.length) return;
      svg += '<polyline fill="none" stroke="' + s[2] + '" stroke-width="2.5" points="' + pts.map(function (p) { return p.join(","); }).join(" ") + '"/>';
      pts.forEach(function (p) { svg += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3.5" fill="' + s[2] + '"/>'; });
    });
    svg += "</svg>";
    var wrap = el("div", {});
    wrap.innerHTML = svg;
    wrap.appendChild(el("div", { class: "bm-legend" }, series.map(function (s) { return el("span", {}, [el("i", { style: "background:" + s[2] }), s[1]]); })));
    wrap.appendChild(el("p", { class: "hint", text: "0 = טוב ככל האפשר, 6 = גרוע ככל האפשר. ירידה = שיפור." }));
    return wrap;
  }
  function mymopPanel(c, reload) {
    var box = el("div", {});
    var labels = (c.outcomes.length && c.outcomes[c.outcomes.length - 1].labels) || {};
    var f = {};
    var scale = function (k) { f[k] = select([["", "—"]].concat([0, 1, 2, 3, 4, 5, 6].map(function (i) { return [i, String(i)]; })), "", { "aria-label": k }); return f[k]; };
    var s1n = input("text", { value: labels.symptom1 || "", placeholder: "בעיה 1" }), s2n = input("text", { value: labels.symptom2 || "", placeholder: "בעיה 2" }), an = input("text", { value: labels.activity_name || "", placeholder: "פעילות" });
    return panel("mymop", "מדד MYMOP", [
      c.outcomes.length ? chart(c.outcomes) : el("p", { class: "empty", text: "עוד אין מדידות." }),
      c.outcomes.length ? el("p", { class: "hint", text: [labels.symptom1, labels.symptom2, labels.activity_name].filter(Boolean).join(" · ") }) : null,
      el("details", { class: "pm-new" }, [el("summary", { text: "מילוי במרפאה" }),
        el("div", { class: "grid2" }, [field("בעיה 1", el("div", { class: "row" }, [s1n, scale("s1")])), field("בעיה 2", el("div", { class: "row" }, [s2n, scale("s2")])),
          field("פעילות", el("div", { class: "row" }, [an, scale("activity")])), field("הרגשה כללית", scale("wellbeing"))]),
        el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "שמירה", onclick: function () {
          var d = {};
          ["s1", "s2", "activity", "wellbeing"].forEach(function (k) { if (f[k].value !== "") d[k] = +f[k].value; });
          if (s1n.value) d.symptom1 = s1n.value; if (s2n.value) d.symptom2 = s2n.value; if (an.value) d.activity_name = an.value;
          call("POST", "/pm/records/" + c.record_id + "/outcomes", d).then(reload, fail(box));
        } })]), box]),
      formLinkButtons(c, ["mymop"], "קישור למטופל/ת למילוי בטלפון")]);
  }
  function formLinkButtons(c, tasks, label) {
    var box = el("div", {});
    return el("div", {}, [el("div", { class: "answers" }, [
      el("button", { class: "btn ghost", type: "button", text: label + " · וואטסאפ", onclick: function () {
        call("POST", "/pm/records/" + c.record_id + "/form-link", { tasks: tasks }).then(function (l) { return sendWa(c.record_id, "forms_link", { link_path: l.path }, box); }, fail(box));
      } }),
      el("button", { class: "btn ghost", type: "button", text: "העתקת קישור", onclick: function () {
        call("POST", "/pm/records/" + c.record_id + "/form-link", { tasks: tasks }).then(function (l) {
          var url = location.origin + l.path; box.textContent = "";
          box.appendChild(el("div", { class: "reclink", text: url }));
          try { navigator.clipboard.writeText(url); box.appendChild(el("span", { class: "hint", text: " הועתק." })); } catch (e) { /* select by hand */ }
        }, fail(box));
      } })]), box]);
  }

  function consentPanel(c, reload) {
    var rows = cfg.consent_kinds.map(function (k) {
      var signed = c.consents.filter(function (x) { return x.kind === k && !x.revoked_at; }).pop();
      var box = el("div", { style: "flex-basis:100%" });
      var parts = signed ? [
        "נחתם " + when(signed.signed_at) + (signed.signer ? " · " + signed.signer : "") + (signed.source === "patient_link" ? " · בקישור" : " · במרפאה") + " ",
        el("button", { class: "mini ghost", type: "button", text: "צפייה", onclick: function () { viewConsent(signed.id, box); } }),
        el("button", { class: "mini ghost", type: "button", text: "ביטול ההסכמה", onclick: function () { call("POST", "/pm/consents/" + signed.id + "/revoke").then(reload, fail(box)); } })
      ] : [badge("לא נחתם", "amber"), " ", el("button", { class: "mini", type: "button", text: "חתימה במרפאה", onclick: function () { signPad(c, k, reload, box); } })];
      return el("li", {}, [el("b", { text: CONSENT_HE[k] + ": " })].concat(parts, [box]));
    });
    return panel("consent", "הסכמות", [el("ul", { class: "pm-list" }, rows),
      el("p", { class: "hint", text: "בלי הסכמה לוואטסאפ לא יוצאות תזכורות אוטומטיות. נוסח הטפסים הוא טיוטה לבדיקתך." }),
      formLinkButtons(c, cfg.consent_kinds.filter(function (k) { return !c.consents.some(function (x) { return x.kind === k && !x.revoked_at; }); }).map(function (k) { return "consent:" + k; }).concat(["mymop"]), "קישור לחתימה ולמדד בטלפון")]);
  }
  function viewConsent(cid, box) {
    call("GET", "/pm/consents/" + cid).then(function (x) {
      box.textContent = "";
      box.appendChild(el("div", { class: "src he" }, [el("b", { text: x.title + " · גרסה " + x.form_version }), x.text ? el("ul", {}, x.text.map(function (t) { return el("li", { text: t }); })) : el("p", { text: "(נוסח קודם)" }),
        el("img", { src: x.signature, alt: "חתימה", style: "max-width:260px;background:#fff;border-radius:8px" })]));
    }, fail(box));
  }
  function signPad(c, kind, reload, box) {
    var form = cfg.forms[kind];
    var canvas = el("canvas", { width: 520, height: 180, class: "pm-pad", "aria-label": "חתימה" });
    var signer = input("text", { value: (c.identity && c.identity.name) || "", placeholder: "שם החותם/ת" });
    var ctx = canvas.getContext("2d"), drawing = false, inked = false;
    ctx.lineWidth = 2.5; ctx.lineCap = "round"; ctx.strokeStyle = "#1d2216";
    function pos(e) { var r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height]; }
    canvas.addEventListener("pointerdown", function (e) { drawing = true; canvas.setPointerCapture(e.pointerId); var p = pos(e); ctx.beginPath(); ctx.moveTo(p[0], p[1]); });
    canvas.addEventListener("pointermove", function (e) { if (!drawing) return; var p = pos(e); ctx.lineTo(p[0], p[1]); ctx.stroke(); inked = true; });
    canvas.addEventListener("pointerup", function () { drawing = false; });
    var msg = el("div", {});
    box.textContent = "";
    box.appendChild(el("div", { class: "panel pm-sign" }, [el("h3", { text: form.title }), el("ul", {}, form.text.map(function (t) { return el("li", { text: t }); })),
      field("שם", signer), canvas,
      el("div", { class: "answers" }, [
        el("button", { class: "btn", type: "button", text: "אני מסכים/ה וחותם/ת", onclick: function () {
          if (!inked) { msg.textContent = "צריך לחתום במסגרת."; return; }
          call("POST", "/pm/records/" + c.record_id + "/consents", { kind: kind, signer: signer.value, signature: canvas.toDataURL("image/png") }).then(reload, fail(msg));
        } }),
        el("button", { class: "btn no", type: "button", text: "ניקוי", onclick: function () { ctx.clearRect(0, 0, canvas.width, canvas.height); inked = false; } }),
        el("button", { class: "btn ghost", type: "button", text: "סגירה", onclick: function () { box.textContent = ""; } })]), msg]));
  }

  function waPanel(c, reload) {
    var box = el("div", {});
    var tpl = select(cfg.whatsapp.templates.filter(function (t) { return t.id !== "intake_link" && t.id !== "forms_link"; }).map(function (t) { return [t.id, t.label]; }), "reminder", { "aria-label": "תבנית" });
    var appts = c.appointments.filter(function (a) { return a.status !== "cancelled" && a.start >= iso(new Date()); });
    var appt = select(appts.map(function (a) { return [a.id, local(a.start)]; }), (appts[0] || {}).id, { "aria-label": "תור" });
    var waConsent = c.consents.some(function (x) { return x.kind === "whatsapp" && !x.revoked_at; });
    return panel("wa", "וואטסאפ", [
      el("p", { class: waConsent ? "hint" : "flag amber", text: waConsent ? "יש הסכמה להודעות. תזכורות אוטומטיות יוצאות ביום העבודה שלפני כל תור." : "אין הסכמה חתומה להודעות וואטסאפ, ולכן לא יוצאות הודעות אוטומטיות. שליחה ידנית אפשרית." }),
      (c.identity && c.identity.phone) ? null : el("p", { class: "flag amber", text: "אין מספר טלפון בתיק." }),
      el("div", { class: "row" }, [field("תבנית", tpl), field("תור", appt), el("button", { class: "btn", type: "button", text: "פתיחה בוואטסאפ", onclick: function () {
        var extra = { appt_id: appt.value || null };
        if (tpl.value === "series_schedule" && c.series.length) extra.series_id = c.series[c.series.length - 1].id;
        sendWa(c.record_id, tpl.value, extra, box);
      } })]), box,
      c.replies.length ? el("div", {}, [el("h3", { text: "תשובות" }), el("ul", { class: "pm-list" }, c.replies.map(function (r) {
        return el("li", {}, [when(r.at) + " · ", r.kind === "button" ? (r.payload === "confirm" ? "אישר/ה" : "ביקש/ה שינוי") : el("span", { class: "quote", text: r.text || "" }), r.handled ? "" : " · ",
          r.handled ? null : el("button", { class: "mini", type: "button", text: "טופל", onclick: function () { call("POST", "/pm/replies/" + r.id + "/handled").then(reload); } })]);
      })), el("p", { class: "hint", text: "תשובות בטקסט חופשי נשמרות מוצפנות ולא נכנסות להערות הקליניות. אם יש בהן משהו קליני, כדאי להעתיק להערת ביקור." })]) : null,
      c.queue.length ? el("details", {}, [el("summary", { text: "הודעות מתוזמנות ויוצאות (" + c.queue.length + ")" }), el("ul", { class: "pm-list" }, c.queue.map(function (q) {
        return el("li", { text: templateLabel(q.template) + " · " + local(q.due) + " · " + (Q_HE[q.status] || q.status) + (q.last_error ? " · " + q.last_error : "") });
      }))]) : null]);
  }

  function payPanel(c, reload) {
    var a = c.account, box = el("div", {});
    var amount = input("number", { min: 0, step: 1, placeholder: "סכום", "aria-label": "סכום", class: "gram" });
    var method = select(cfg.pay_methods.map(function (m) { return [m, METHOD_HE[m] || m]; }), "card", { "aria-label": "אמצעי" });
    var receipt = input("text", { placeholder: "מספר קבלה בתוכנה החיצונית", "aria-label": "מספר קבלה" });
    var day = input("date", { value: iso(new Date()) });
    var pkgLabel = input("text", { value: "סדרת 7 טיפולים", "aria-label": "שם החבילה" }), pkgN = input("number", { value: 7, min: 1, class: "gram", "aria-label": "מפגשים" }), pkgP = input("number", { min: 0, class: "gram", placeholder: "מחיר", "aria-label": "מחיר" });
    return panel("pay", "תשלומים", [
      el("div", { class: "ep" }, [el("span", { text: "חויב: " + money(a.charged) }), el("span", { text: "שולם: " + money(a.paid) }), el("span", { class: a.balance > 0 ? "pm-due" : "", text: (a.balance < 0 ? "יתרה לזכות: " + money(-a.balance) : "יתרה לתשלום: " + money(a.balance)) })]),
      a.packages.length ? el("p", { class: "hint", text: a.packages.map(function (p) { return p.label + ": נוצלו " + p.used + " מתוך " + p.sessions + " (" + money(p.price) + ")"; }).join(" · ") }) : null,
      el("div", { class: "row" }, [amount, method, field("תאריך", day), receipt, el("button", { class: "btn", type: "button", text: "רישום תשלום", onclick: function () {
        call("POST", "/pm/records/" + c.record_id + "/payments", { amount: +amount.value, method: method.value, receipt_no: receipt.value, day: day.value }).then(reload, fail(box));
      } })]),
      el("details", { class: "pm-new" }, [el("summary", { text: "חבילה חדשה" }), el("div", { class: "row" }, [pkgLabel, field("מפגשים", pkgN), field("מחיר", pkgP),
        el("button", { class: "btn", type: "button", text: "הוספה", onclick: function () { call("POST", "/pm/records/" + c.record_id + "/packages", { label: pkgLabel.value, sessions: +pkgN.value, price: +pkgP.value }).then(reload, fail(box)); } })])]),
      a.payments.length ? el("details", {}, [el("summary", { text: "תשלומים (" + a.payments.length + ")" }), el("ul", { class: "pm-list" }, a.payments.map(function (p) {
        return el("li", { text: p.day + " · " + money(p.amount) + " · " + (METHOD_HE[p.method] || p.method) + (p.receipt_no ? " · קבלה " + p.receipt_no : "") });
      }))]) : null,
      el("p", { class: "hint", text: "קבלות מפיקים בתוכנת החשבוניות. כאן נרשם רק הסטטוס ומספר הקבלה, ולתוכנה החיצונית לא עובר שום פרט קליני." }), box]);
  }

  var TL_HE = { record: "התיק נפתח", "doc:intake": "שאלון התקבל", "doc:review": "סיכום נשמר", "doc:report": "דוח אבחנתי נשמר", "doc:plan": "תוכנית טיפול נשמרה", appointment: "תור", note: "הערת ביקור", mymop: "מדד MYMOP", consent: "הסכמה נחתמה", consent_revoked: "הסכמה בוטלה", message: "הודעה", reply: "תשובה בוואטסאפ", payment: "תשלום", package: "חבילה" };
  function timelinePanel(c) {
    var list = el("ul", { class: "pm-timeline" });
    var filter = select([["", "הכול"], ["appointment", "תורים"], ["note", "הערות"], ["doc", "מסמכים"], ["mymop", "MYMOP"], ["message", "הודעות"], ["payment", "תשלומים"]], "", { "aria-label": "סינון" });
    var items = [];
    function draw() {
      list.textContent = "";
      items.filter(function (i) { return !filter.value || i.type.indexOf(filter.value) === 0 || (filter.value === "message" && i.type === "reply"); }).forEach(function (i) {
        var extra = i.type === "appointment" ? (KIND_HE[i.kind] || i.kind) + " · " + (STATUS_HE[i.status] || i.status) + (i.series_no ? " · מפגש " + i.series_no : "")
          : i.type === "mymop" ? "בעיה 1: " + i.s1 + (i.s2 !== null ? ", בעיה 2: " + i.s2 : "") + ", הרגשה: " + i.wellbeing
          : i.type === "message" ? templateLabel(i.template) + " · " + i.channel + " · " + (Q_HE[i.status] || i.status)
          : i.type === "payment" ? money(i.amount) : i.type.indexOf("consent") === 0 ? CONSENT_HE[i.kind] : i.type === "package" ? i.label
          : i.version ? "גרסה " + i.version : i.versions > 1 ? i.versions + " גרסאות" : "";
        list.appendChild(el("li", {}, [el("span", { class: "pm-time", text: local(i.when) }), el("b", { text: (TL_HE[i.type] || i.type) }), extra ? " · " + extra : ""]));
      });
    }
    filter.addEventListener("change", draw);
    call("GET", "/pm/records/" + c.record_id + "/timeline").then(function (t) { items = t.items; draw(); });
    return panel("timeline", "ציר זמן", [field("סינון", filter), list]);
  }

  // ---- management ----
  function renderAdmin(v) {
    v.appendChild(statsPanel());
    v.appendChild(waAdmin());
    v.appendChild(gcalAdmin());
    v.appendChild(pricesAdmin());
    v.appendChild(daysAdmin());
    v.appendChild(backupAdmin());
  }
  function statsPanel() {
    var p = panel("stats", "סטטיסטיקה של הקליניקה", [status("טוען…")]);
    call("GET", "/pm/stats").then(function (s) {
      p.textContent = "";
      p.appendChild(el("h2", { text: "סטטיסטיקה של הקליניקה" }));
      var max = Math.max.apply(null, s.months.map(function (m) { return m.visits + m.no_show; }).concat([1]));
      p.appendChild(el("div", { class: "ep" }, [
        el("span", { text: "ביקורים ב־12 חודשים: " + s.months.reduce(function (a, m) { return a + m.visits; }, 0) }),
        el("span", { text: "אי הגעה: " + (s.no_show_rate === null ? "—" : Math.round(s.no_show_rate * 100) + "%") }),
        el("span", { text: "סדרות: " + s.series.total + " (הושלמו " + s.series.completed + ")" }),
        el("span", { text: "MYMOP: " + s.mymop.patients + " מטופלים" + (s.mymop.mean_change_s1 !== null ? ", שיפור ממוצע בבעיה 1: " + s.mymop.mean_change_s1 : "") })]));
      p.appendChild(el("div", { class: "pm-bars" }, s.months.map(function (m) {
        return el("div", { class: "pm-bar" }, [el("span", { class: "pm-month", text: m.month.slice(5) + "/" + m.month.slice(2, 4) }),
          el("span", { class: "pm-track" }, [el("i", { style: "width:" + (100 * m.visits / max) + "%" }), el("i", { class: "ns", style: "width:" + (100 * m.no_show / max) + "%" })]),
          el("span", { class: "hint", text: m.visits + " ביקורים" + (m.no_show ? " · " + m.no_show + " לא הגיעו" : "") + (m.new_records ? " · " + m.new_records + " חדשים" : "") + (m.revenue ? " · " + money(m.revenue) : "") })]);
      })));
      p.appendChild(el("p", { class: "hint", text: "ספירות בלבד, בלי שמות ובלי טקסט חופשי." }));
    }, fail(p));
    return p;
  }
  function waAdmin() {
    var w = cfg.whatsapp, box = el("div", {});
    var a = input("time", { value: w.send_hours[0] }), b = input("time", { value: w.send_hours[1] }), rem = input("time", { value: w.reminder_time });
    var addr = input("text", { value: w.address, placeholder: "כתובת הקליניקה" });
    var names = {};
    var test = el("textarea", { "aria-label": "בדיקת הודעה", placeholder: "אפשר להדביק כאן טקסט ולבדוק אם יש בו מילה קלינית" });
    var res = el("p", { class: "hint" });
    test.addEventListener("input", function () { call("POST", "/pm/whatsapp/check", { text: test.value }).then(function (r) { res.textContent = r.hits.length ? "חסום: " + r.hits.join(", ") : "מותר: לוגיסטי בלבד"; res.className = r.hits.length ? "flag red" : "flag info"; }); });
    return panel("wa-admin", "וואטסאפ", [
      el("p", { class: w.cloud_api ? "flag info" : "flag amber", text: w.cloud_api ? "WhatsApp Cloud API מחובר: תזכורות יוצאות אוטומטית בשעות השליחה." : "WhatsApp Cloud API לא מוגדר (TCM_WA_TOKEN, TCM_WA_PHONE_ID). עד אז, הודעות שלא יצאו מופיעות במסך היום לשליחה ידנית." }),
      el("p", { class: w.webhook ? "hint" : "flag amber", text: w.webhook ? "קליטת תשובות מוגדרת (/api/wa/webhook)." : "קליטת תשובות לא מוגדרת (TCM_WA_VERIFY_TOKEN, TCM_WA_APP_SECRET). ראו מדריך ההקמה." }),
      w.cloud_api ? waConnection(w) : null,
      el("div", { class: "row" }, [field("שליחה מ־", a), field("עד", b), field("שעת תזכורת", rem), field("כתובת", addr)]),
      el("h3", { text: "תבניות" }),
      el("ul", { class: "pm-list" }, w.templates.map(function (t) {
        names[t.id] = input("text", { value: t.meta_name, "aria-label": "שם התבנית ב־Meta", class: "note" });
        return el("li", {}, [el("b", { text: t.label + " " }), t.check.length ? badge("מילה קלינית: " + t.check.join(", "), "red") : badge("לוגיסטי"), el("div", { class: "src he", text: t.body }),
          t.buttons.length ? el("span", { class: "hint", text: "כפתורים: " + t.buttons.map(function (x) { return x.text; }).join(" · ") + " " }) : null, field("שם ב־WhatsApp Manager", names[t.id])]);
      })),
      el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "שמירה", onclick: function () {
        var mn = {}; Object.keys(names).forEach(function (k) { mn[k] = names[k].value; });
        call("PUT", "/pm/whatsapp/config", { send_hours: [a.value, b.value], reminder_time: rem.value, address: addr.value, meta_names: mn }).then(function () { box.textContent = "נשמר."; }, fail(box));
      } })]), box,
      el("h3", { text: "בודק ההודעות" }), test, res]);
  }
  // The Cloud API, checked from here: Meta answers for the number, the templates' approval, and a test send.
  var TPL_HE = { APPROVED: "אושרה", PENDING: "ממתינה לאישור", REJECTED: "נדחתה", PAUSED: "מושהית", DISABLED: "מושבתת", IN_APPEAL: "בערעור" };
  function waConnection(w) {
    var box = el("div", {}), out = el("div", {});
    var phone = input("tel", { placeholder: "מספר שלך לבדיקה, למשל 0501234567", "aria-label": "מספר לבדיקה", inputmode: "tel" });
    function check() {
      out.textContent = "בודק מול Meta…";
      call("GET", "/pm/whatsapp/status").then(function (r) {
        out.textContent = "";
        if (!r.ok) { out.appendChild(el("p", { class: "flag red", text: "Meta לא אישרה את החיבור: " + r.error })); return; }
        out.appendChild(el("p", { class: "flag info", text: "מחובר: " + (r.number || "") + (r.name ? " · " + r.name : "") + (r.quality ? " · איכות " + r.quality : "") + (r.name_status && r.name_status !== "APPROVED" ? " · שם התצוגה: " + r.name_status : "") }));
        if (r.templates) {
          var mine = w.templates.map(function (t) { return t.meta_name; });
          out.appendChild(el("ul", { class: "pm-list" }, w.templates.map(function (t) {
            var m = r.templates.filter(function (x) { return x.name === t.meta_name; })[0];
            return el("li", {}, [t.label + " (" + t.meta_name + "): ", m ? badge((TPL_HE[m.status] || m.status) + (m.category && m.category !== "UTILITY" ? " · " + m.category : ""), m.status === "APPROVED" ? "" : m.status === "REJECTED" ? "red" : "amber")
              : badge("לא נמצאה ב־Meta", "amber"), m && m.rejected_reason && m.rejected_reason !== "NONE" ? el("span", { class: "hint", text: " " + m.rejected_reason }) : null]);
          })));
          if (mine.some(function (n) { return !r.templates.some(function (x) { return x.name === n; }); })) out.appendChild(el("button", { class: "mini", type: "button", text: "שליחת התבניות החסרות לאישור", onclick: submit }));
        } else out.appendChild(el("p", { class: "hint", text: r.templates_error ? "רשימת התבניות לא נטענה: " + r.templates_error : "כדי לראות כאן את אישור התבניות, צריך גם את TCM_WA_WABA_ID." }));
      }, fail(out));
    }
    function submit() {
      out.textContent = "שולח את התבניות ל־Meta…";
      call("POST", "/pm/whatsapp/templates").then(function (r) {
        out.textContent = "";
        out.appendChild(el("ul", { class: "pm-list" }, r.results.map(function (x) { return el("li", { text: x.name + ": " + (x.error || (TPL_HE[x.status] || x.status || "נשלחה")) }); })));
      }, fail(out));
    }
    return el("div", {}, [
      el("div", { class: "answers" }, [el("button", { class: "btn ghost", type: "button", text: "בדיקת החיבור ל־Meta", onclick: check })]),
      el("div", { class: "row" }, [phone, el("button", { class: "btn ghost", type: "button", text: "שליחת הודעת בדיקה", onclick: function () {
        box.textContent = "שולח…";
        call("POST", "/pm/whatsapp/test", { phone: phone.value }).then(function () { box.textContent = "נשלחה הודעת hello_world של Meta (באנגלית). אם היא הגיעה לטלפון, השליחה עובדת."; }, fail(box));
      } })]), box, out]);
  }
  function gcalAdmin() {
    var g = cfg.gcal, box = el("div", {});
    var cals = input("text", { value: g.read_calendars.join(", "), "aria-label": "יומנים לקריאה" });
    var mode = select([["fixed", "מילה קבועה"], ["initials", "ראשי תיבות של המטופל/ת"], ["record", "מספר התיק"]], g.title.mode, { "aria-label": "כותרת" });
    var text = input("text", { value: g.title.text, "aria-label": "המילה" });
    return panel("gcal", "יומן גוגל", [
      el("p", { class: g.connected ? "flag info" : "flag amber", text: !g.configured ? "לא מוגדר: צריך TCM_GOOGLE_CLIENT_ID ו־TCM_GOOGLE_CLIENT_SECRET (מדריך ההקמה)." : g.connected ? "מחובר. סנכרון אחרון: " + (g.last_sync ? local(g.last_sync) : "עוד לא") + (g.last_error ? " · שגיאה: " + g.last_error : "") : "מוגדר, עוד לא מחובר." }),
      el("div", { class: "answers" }, [
        g.configured && !g.connected ? el("button", { class: "btn", type: "button", text: "התחברות ליומן גוגל", onclick: function () { call("GET", "/pm/gcal/start").then(function (r) { location.href = r.url; }, fail(box)); } }) : null,
        g.connected ? el("button", { class: "btn ghost", type: "button", text: "סנכרון עכשיו", onclick: function () { box.textContent = "מסנכרן…"; call("POST", "/pm/gcal/sync").then(function (r) { box.textContent = "נקראו " + r.pulled + " אירועים, נכתבו " + r.pushed + "."; }, fail(box)); } }) : null,
        g.connected ? el("button", { class: "btn no", type: "button", text: "ניתוק", onclick: function () { call("POST", "/pm/gcal/disconnect").then(function () { load("admin"); }); } }) : null]),
      field("יומנים לקריאה (מזהים מופרדים בפסיק, primary = היומן הראשי)", cals),
      el("div", { class: "row" }, [field("כותרת לתורים שהמערכת כותבת", mode), field("המילה", text)]),
      el("p", { class: "hint", text: "תורים שהמערכת יוצרת נכתבים ליומן נפרד בשם \"קליניקה\". הכותרת לא כוללת סוג טיפול או מידע קליני, ומספר התיק נשמר בשדה פרטי של האירוע." }),
      el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "שמירה", onclick: function () {
        call("PUT", "/pm/gcal/config", { read_calendars: cals.value.split(",").map(function (x) { return x.trim(); }), title: { mode: mode.value, text: text.value } }).then(function () { box.textContent = "נשמר."; }, fail(box));
      } })]), box]);
  }
  function pricesAdmin() {
    var box = el("div", {});
    return panel("prices", "סוגי ביקור ומחירון", [el("ul", { class: "pm-list" }, cfg.kinds.map(function (k) {
      var label = input("text", { value: k.label, "aria-label": "שם" }), minutes = input("number", { value: k.minutes, class: "gram", "aria-label": "דקות" }), price = input("number", { value: k.price, class: "gram", "aria-label": "מחיר" });
      return el("li", { class: "row" }, [label, field("דקות", minutes), field("מחיר ₪", price), el("button", { class: "mini", type: "button", text: "שמירה", onclick: function () {
        call("PUT", "/pm/prices", { kind: k.kind, label: label.value, minutes: +minutes.value, price: +price.value }).then(function () { box.textContent = "נשמר: " + label.value; }, fail(box));
      } })]);
    })), el("p", { class: "hint", text: "המחיר נקבע לתור ברגע הקביעה. תור בתוך חבילה לא מחויב בנפרד." }), box]);
  }
  function daysAdmin() {
    var box = el("div", {});
    var checks = [6, 0, 1, 2, 3, 4, 5].map(function (d) { var c = el("input", { type: "checkbox", checked: cfg.workdays.indexOf(d) !== -1 ? "checked" : null }); c.dataset.d = d; return el("label", { class: "opt" }, [c, DAYS_HE[d]]); });
    var day = input("date", {}), label = input("text", { placeholder: "סיבה (חופשה, כנס)", "aria-label": "סיבה" });
    var off = Object.keys(cfg.days_off).sort().filter(function (d) { return d >= iso(new Date()); }).slice(0, 30);
    return panel("days", "ימי עבודה וחופשות", [el("div", { class: "checks" }, checks),
      el("button", { class: "mini", type: "button", text: "שמירת ימי העבודה", onclick: function () {
        call("PUT", "/pm/workdays", { days: checks.map(function (l) { var c = l.querySelector("input"); return c.checked ? +c.dataset.d : null; }).filter(function (x) { return x !== null; }) }).then(function () { box.textContent = "נשמר."; }, fail(box));
      } }),
      el("p", { class: "hint", text: "החגים מחושבים מקומית מלוח השנה העברי (ראש השנה, יום כיפור, סוכות, שמיני עצרת, פסח, שביעי של פסח, שבועות, יום העצמאות)." }),
      el("div", { class: "row" }, [day, label, el("button", { class: "mini", type: "button", text: "הוספת יום חופש", onclick: function () { call("PUT", "/pm/days-off", { day: day.value, label: label.value || "חופש" }).then(function () { load("admin"); }, fail(box)); } })]),
      el("p", { class: "hint", text: "הקרובים: " + off.map(function (d) { return d.slice(8) + "." + d.slice(5, 7) + " " + cfg.days_off[d]; }).join(" · ") }), box]);
  }
  function backupAdmin() {
    var b = cfg.backup, box = el("div", {});
    return panel("backup", "גיבוי", [
      el("p", { class: b.latest && b.age_hours < 30 ? "hint" : "flag amber", text: b.latest ? "גיבוי אחרון: " + b.latest + " (לפני " + Math.round(b.age_hours) + " שעות)" : "עוד אין גיבוי." }),
      b.error ? el("p", { class: "flag red", text: "שגיאת גיבוי: " + b.error }) : null,
      el("p", { class: "hint", text: "השרת מגבה פעם ביום כשהוא דולק, מוצפן במפתח גיבוי נפרד, ושומר 14 גיבויים. את תיקיית המפתחות צריך לשמור בנפרד (למשל דיסק און קי בכספת), אחרת אי אפשר לקרוא את הגיבוי." }),
      el("div", { class: "answers" }, [
        el("button", { class: "btn", type: "button", text: "גיבוי עכשיו", onclick: function () { box.textContent = "מגבה…"; call("POST", "/pm/backup").then(function (r) { box.textContent = "נשמר: " + r.file; }, fail(box)); } }),
        el("button", { class: "btn ghost", type: "button", text: "בדיקת שחזור של האחרון", onclick: function () { box.textContent = "בודק…"; call("POST", "/pm/backup/check").then(function (r) { box.textContent = "תקין (" + r.integrity + "): " + r.counts.records + " תיקים, " + r.documents_opened + " מסמכים נפתחו."; }, fail(box)); } })]),
      box]);
  }

  // ---- install ----
  var tries = 0;
  function install() {
    var nav = document.querySelector("nav.tabs");
    var recTab = document.getElementById("tab-records");
    if (!recTab && tries++ < 50) { setTimeout(install, 100); return; }   // records.js adds its tab first
    // The clinic's own tabs sit together, right after "תיקים".
    var after = recTab;
    [["today", "היום"], ["cal", "יומן"], ["admin", "ניהול"]].forEach(function (t) {
      tabs[t[0]] = el("button", { role: "tab", id: "tab-pm-" + t[0], "aria-selected": "false", type: "button", text: t[1], onclick: function () { show(t[0]); } });
      nav.insertBefore(tabs[t[0]], after ? after.nextSibling : null);
      after = tabs[t[0]];
    });
    ["today", "cal", "card", "admin"].forEach(function (k) {
      views[k] = el("section", { id: "view-pm-" + k, class: "pm-view", hidden: "" });
      document.querySelector(".wrap").appendChild(views[k]);
    });
    nav.addEventListener("click", function (e) {
      var b = e.target.closest("button[role=tab]");
      if (b && b.id.indexOf("tab-pm-") !== 0) Object.keys(views).forEach(function (k) { views[k].hidden = true; });
    });
    var css = document.createElement("style");
    css.textContent = [
      ".pm-view[hidden]{display:none}.pm-view{display:grid;gap:16px}",
      ".pm-list{list-style:none;margin:0;padding:0;display:grid;gap:8px}.pm-list li{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.pm-list li.off{opacity:.6}",
      ".pm-appts{list-style:none;margin:0;padding:0;display:grid;gap:8px}.pm-appt{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:6px 14px;align-items:center;padding:10px 14px;border-radius:18px;background:var(--glass);border:1px solid var(--edge)}",
      ".pm-appt.st-cancelled{opacity:.55;text-decoration:line-through}.pm-appt.st-done{border-color:var(--jade)}.pm-appt.st-change_requested{border-color:var(--amber)}",
      ".pm-time{font-variant-numeric:tabular-nums;white-space:nowrap}.pm-appt .pm-time{font-size:1.35rem;font-weight:300;letter-spacing:-.01em}",
      "@media(max-width:640px){.pm-appt{grid-template-columns:auto minmax(0,1fr)}.pm-appt>.mini-row{grid-column:1/-1;flex-wrap:wrap}}",
      ".pm-week{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.pm-day{background:var(--glass);border:1px solid var(--edge);border-radius:18px;padding:10px;display:grid;gap:6px;align-content:start;min-height:120px}",
      ".pm-day.off{background:color-mix(in srgb,var(--amber-soft) 50%,var(--glass))}.pm-day.today{border-color:color-mix(in srgb,var(--jade) 60%,transparent);box-shadow:0 0 0 4px color-mix(in srgb,var(--jade) 12%,transparent)}.pm-dayhead{font-size:.95rem}",
      ".pm-chip{background:var(--jade-soft);border-radius:12px;padding:4px 10px;font-size:.9rem}.pm-chip.ext{background:transparent;border:1px dashed var(--edge)}.pm-chip.st-cancelled{opacity:.5;text-decoration:line-through}.pm-chip.st-change_requested{box-shadow:inset 3px 0 0 var(--amber)}",
      ".pm-chip summary{color:var(--ink)}.pm-chipbody{display:grid;gap:6px;padding:6px 0}",
      ".pm-new{border:1px dashed var(--edge);border-radius:18px;padding:8px 12px}.pm-new[open]{border-style:solid;background:var(--glass)}.pm-new .row{align-items:end}",
      ".pm-rail{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}.pm-rail a{flex:none;text-decoration:none;color:var(--muted);font-size:.88rem;padding:6px 14px;border-radius:999px;border:1px solid var(--edge);background:var(--glass)}.pm-rail a:hover{color:var(--ink);border-color:color-mix(in srgb,var(--jade) 55%,transparent)}",
      ".pm-cardhead{position:sticky;top:64px;z-index:3;background:var(--glass);border-color:var(--edge);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}",
      ".pm-series{display:flex;flex-wrap:wrap;gap:6px}.pm-series .slot{background:var(--jade-soft);border-radius:10px;padding:4px 10px;font-size:.9rem}.pm-series .slot.first{background:var(--jade);color:var(--jade-ink)}.pm-series .slot.fu{background:var(--surface)}",
      ".pm-note{border:1px solid var(--edge);border-radius:18px;padding:8px 12px;background:var(--glass)}.pm-notefield{margin:4px 0}",
      ".pm-chart{width:100%;max-width:640px;height:auto}.pm-pad{width:100%;max-width:520px;height:auto;background:#fffdf8;border-radius:12px;touch-action:none;border:1px solid var(--line)}",
      ".pm-due{border-color:var(--amber)!important;color:var(--amber)}.pm-bars{display:grid;gap:6px}.pm-bar{display:grid;grid-template-columns:4em minmax(0,1fr);gap:2px 10px;align-items:center}.pm-bar .hint{grid-column:2}",
      ".pm-track{display:flex;height:10px;background:var(--surface-2);border-radius:5px;overflow:hidden}.pm-track i{display:block;background:var(--jade)}.pm-track i.ns{background:var(--cinnabar)}.pm-month{font-variant-numeric:tabular-nums;color:var(--muted)}",
      ".pm-timeline{list-style:none;margin:0;padding:0;display:grid;gap:4px}.pm-timeline li{display:flex;gap:10px;flex-wrap:wrap;padding:6px 0;border-bottom:1px solid var(--edge)}.pm-timeline .pm-time{color:var(--muted);min-width:9.5em}",
      ".badge{font-size:.78rem;border-radius:999px;padding:1px 8px;background:var(--jade-soft);color:var(--jade);white-space:nowrap}.badge.red{background:var(--cinnabar-soft);color:var(--cinnabar)}.badge.amber{background:var(--amber-soft);color:var(--amber)}",
      // Titles in the opening screen's language: thin, with a glowing ring like the figure's points.
      ".pm-view .panel>h2:first-child,.pm-view .panel>.row:first-child>h2{font-weight:300;font-size:clamp(1.3rem,2vw,1.6rem);letter-spacing:-.01em;margin:0}",
      ".pm-view .panel>h2:first-child::before,.pm-view .panel>.row:first-child>h2::before{content:'';display:inline-block;width:9px;height:9px;margin-inline-end:10px;vertical-align:.12em;border-radius:50%;border:1.5px solid var(--jade);box-shadow:0 0 0 3px color-mix(in srgb,var(--jade) 14%,transparent),0 0 10px color-mix(in srgb,var(--jade) 45%,transparent)}",
      ".pm-view .panel h3{font-weight:400;font-size:1.02rem;color:var(--muted);letter-spacing:.01em}",
      ".reclink{direction:ltr;unicode-bidi:isolate;font-family:var(--font-mono);font-size:.8rem;word-break:break-all}"
    ].join("");
    document.head.appendChild(css);
    var m = /^#pm-(today|cal|admin)$/.exec(location.hash || "");
    if (m) show(m[1]);
  }

  window.TCMPractice = { show: show, card: function (rid) { show("card", rid); } };
  if (location.protocol === "file:") return;
  fetch(API + "/health", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && j.service === "tcm-clinic-server") install(); }, function () { /* no server: static prototype */ });
})();
