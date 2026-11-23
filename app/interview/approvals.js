// Clinical approval tab ("אישור קליני") of the clinic server (server/approvals.py).
// Every pattern, pattern-finding link and weight, lexicon wording, treatment suggestion and safety rule
// the builds derive is a DRAFT. Here the clinician approves, edits a weight, rejects or adds, item by
// item. Decisions collect locally until "חתימה ושמירה"; the server then appends them to a hash-chained
// log signed in the clinician's name. Nothing in kb/ is overwritten: the builds read the exported log
// (kb/approvals/decisions.json) and lay it over the draft. Safety rules cannot be switched off here,
// only approved or disputed with a note.
// Without a server (GitHub Pages, a file opened from disk) /api/health fails and nothing here shows.
(function () {
  "use strict";
  var API = window.TCM_API || "/api";
  var KB = window.TCM_KB, TX = window.TCM_TX, I = window.TCMI18n;
  if (!KB || !TX || !I) return;
  var DEFAULT_W = KB.defaults.weight;
  var PAGE = 60;
  var KIND_HE = { method: "שיטת טיפול (WHO)", point: "נקודות", herb: "צמחים", formula: "מרשמים" };
  var TX_LIST = { method: "m", point: "p", herb: "h", formula: "fm" };
  var STATE_HE = { draft: "טיוטה", approved: "אושר", edited: "משקל עודכן", rejected: "נדחה", added: "נוסף", disputed: "במחלוקת" };

  var featById = {}, synById = {};
  KB.features.forEach(function (f) { featById[f.id] = f; });
  KB.syndromes.forEach(function (s) { synById[s.id] = s; });
  var built = KB.approvals || { applied: 0, changed: [], orphans: [], head_seq: 0 };
  var changedSince = {};
  (built.changed || []).forEach(function (k) { changedSince[k] = true; });

  var server = {};     // key -> latest saved row (from the server)
  var pending = {};    // key -> decision not yet signed
  var me = "", maxSeq = 0, chain = { ok: true, msg: "" };
  var view, tab, body, saveBar, sub = "patterns";
  var list = { q: "", set: "who", status: "all", shown: PAGE, sid: null };

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) n.setAttribute(k, attrs[k]);
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

  function zh(text) { return el("span", { class: "zh", lang: "zh", text: text }); }
  function srcLink(ref, quote) {
    var s = I.source(ref, quote);
    return s ? el("a", { href: s.url, target: "_blank", rel: "noopener noreferrer", class: "srclink", text: s.he }) : null;
  }

  // ---- keys and the state of each item ----
  function pKey(sid) { return "pattern:" + sid; }
  function lKey(sid, fid) { return "link:" + sid + "|" + fid; }
  function tKey(sid, kind, id) { return "tx:" + sid + "|" + kind + "|" + id; }

  function decisionOf(key) { return pending[key] || server[key] || null; }
  function stateOf(key) {
    var d = decisionOf(key);
    if (!d || d.action === "reset") return "draft";
    return { approve: "approved", edit: "edited", reject: "rejected", add: "added", dispute: "disputed" }[d.action] || "draft";
  }

  function decide(key, action, extra) {
    var d = { key: key, action: action };
    Object.keys(extra || {}).forEach(function (k) { d[k] = extra[k]; });
    if (action === "reset") {
      if (!server[key]) { delete pending[key]; return refreshAfterChange(); }
    }
    pending[key] = d;
    refreshAfterChange();
  }

  function refreshAfterChange() { renderSaveBar(); render(); }

  function chip(key) {
    var st = stateOf(key), d = decisionOf(key);
    var cls = "kb-chip " + st + (pending[key] ? " pending" : "");
    var title = pending[key] ? "לא נשמר עדיין" : d ? (d.actor || "").replace(/^clinician:/, "") + " · " + when(d.at) + (d.note ? " · " + d.note : "") : "";
    return el("span", { class: cls, title: title, text: (pending[key] ? "✎ " : "") + STATE_HE[st] + (changedSince[key] && !pending[key] ? " · המקור השתנה" : "") });
  }

  function actions(key, opts) {
    opts = opts || {};
    var st = stateOf(key);
    var out = el("span", { class: "mini-row kb-act" });
    if (opts.approve !== false) out.appendChild(el("button", { class: "mini" + (st === "approved" ? " on" : ""), type: "button", title: "אישור", "aria-label": "אישור", text: "✓", onclick: function () { decide(key, "approve", { draft: opts.draft || null }); } }));
    if (opts.reject !== false) out.appendChild(el("button", { class: "mini no" + (st === "rejected" ? " on" : ""), type: "button", title: opts.rejectTitle || "דחייה", "aria-label": "דחייה", text: "✗", onclick: function () {
      var note = opts.askNote ? window.prompt(opts.askNote, "") : "";
      if (note === null) return;
      decide(key, "reject", { draft: opts.draft || null, note: note || "" });
    } }));
    if (st !== "draft" || pending[key]) out.appendChild(el("button", { class: "mini ghost", type: "button", title: "החזרה לטיוטה", "aria-label": "החזרה לטיוטה", text: "↺", onclick: function () { decide(key, "reset"); } }));
    return out;
  }

  // ---- install the tab ----
  function install() {
    var nav = document.querySelector("nav.tabs");
    tab = el("button", { role: "tab", id: "tab-approvals", "aria-selected": "false", type: "button", text: "אישור קליני", onclick: show });
    nav.appendChild(tab);
    nav.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (b && b !== tab) hide();
    });
    view = el("section", { id: "view-approvals", hidden: "" });
    body = el("div", { class: "kb-body" });
    saveBar = el("div", { class: "panel kb-save", hidden: "" });
    view.appendChild(body);
    view.appendChild(saveBar);
    var anchor = document.getElementById("view-clin");
    anchor.parentNode.insertBefore(view, anchor.nextSibling);
    var css = document.createElement("style");
    css.textContent = [
      "#view-approvals[hidden],.kb-save[hidden]{display:none}",
      ".wrap.kb-wide{max-width:1180px}",
      ".kb-body{display:grid;gap:14px}",
      ".kb-sub{display:flex;flex-wrap:wrap;gap:6px}",
      ".kb-sub button{font:inherit;font-size:.9rem;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:3px 12px;cursor:pointer}",
      ".kb-sub button[aria-pressed=true]{border-color:var(--jade);background:var(--jade-soft);color:var(--jade);font-weight:600}",
      ".kb-cols{display:grid;grid-template-columns:minmax(240px,320px) 1fr;gap:14px;align-items:start}",
      "@media (max-width:820px){.kb-cols{grid-template-columns:1fr}}",
      ".kb-list{max-height:70vh;overflow:auto;display:grid;gap:2px;padding:6px}",
      ".kb-list button{font:inherit;font-size:.88rem;text-align:start;background:none;border:0;border-radius:6px;padding:5px 8px;cursor:pointer;color:var(--ink);display:grid;gap:1px}",
      ".kb-list button[aria-current=true]{background:var(--jade-soft)}",
      ".kb-list button:hover{background:color-mix(in srgb,var(--jade-soft) 50%,transparent)}",
      ".kb-list .meta{font-size:.75rem;color:var(--muted)}",
      ".kb-bar{height:4px;border-radius:2px;background:var(--line);overflow:hidden}.kb-bar i{display:block;height:100%;background:var(--jade)}",
      "table.kb{border-collapse:collapse;width:100%;font-size:.88rem}",
      "table.kb th{text-align:start;color:var(--muted);font-weight:600;font-size:.78rem;border-bottom:1px solid var(--line);padding:4px 6px;white-space:nowrap}",
      "table.kb td{border-bottom:1px solid var(--line);padding:5px 6px;vertical-align:top}",
      "table.kb tr.kb-st-rejected td{opacity:.55}table.kb tr.kb-st-rejected td:last-child,table.kb tr.kb-st-rejected td:nth-last-child(2){opacity:1}",
      "table.kb .ev{font-size:.8rem;color:var(--muted);max-width:34em}",
      "table.kb input[type=number]{width:5.2em;padding:3px 6px}",
      "table.kb input[type=text]{width:100%;font:inherit;font-size:.85rem;padding:3px 6px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink)}",
      ".kb-chip{font-size:.74rem;border-radius:999px;padding:1px 8px;white-space:nowrap;background:var(--paper);color:var(--muted);border:1px solid var(--line)}",
      ".kb-chip.approved,.kb-chip.edited,.kb-chip.added{background:var(--jade-soft);color:var(--jade);border-color:transparent}",
      ".kb-chip.rejected{background:var(--cinnabar-soft);color:var(--cinnabar);border-color:transparent}",
      ".kb-chip.disputed{background:var(--amber-soft);color:var(--amber);border-color:transparent}",
      ".kb-chip.pending{border:1px dashed currentColor}",
      ".kb-src{font-size:.72rem;border-radius:4px;padding:0 5px;background:var(--paper);border:1px solid var(--line);margin-inline-end:3px;white-space:nowrap}",
      ".kb-act .mini{min-width:2em}.kb-act .mini.on{background:var(--jade);color:var(--surface);border-color:var(--jade)}",
      ".kb-act .mini.no.on{background:var(--cinnabar);border-color:var(--cinnabar)}",
      ".kb-save{position:sticky;bottom:8px;z-index:4;border-color:var(--jade);box-shadow:0 4px 16px rgba(0,0,0,.12)}",
      ".kb-text{font-size:.88rem;white-space:pre-wrap;max-height:9em;overflow:auto;border-inline-start:3px solid var(--line);padding-inline-start:8px}",
      ".kb-filters{display:flex;flex-wrap:wrap;gap:6px;align-items:center}",
      ".kb-filters input[type=search]{font:inherit;font-size:.9rem;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink);min-width:12em;flex:1}",
      ".kb-hash{font-family:var(--font-mono);font-size:.72rem;color:var(--muted)}"
    ].join("");
    document.head.appendChild(css);
    window.addEventListener("beforeunload", function (e) {
      if (Object.keys(pending).length) { e.preventDefault(); e.returnValue = ""; }
    });
  }

  function show() {
    document.querySelectorAll("nav.tabs button").forEach(function (b) { b.setAttribute("aria-selected", b === tab); });
    ["view-patient", "view-clin", "view-records"].forEach(function (id) { var n = document.getElementById(id); if (n) n.hidden = true; });
    var bar = document.getElementById("record-bar"); if (bar) bar.hidden = true;
    document.querySelector(".wrap").classList.add("kb-wide");
    view.hidden = false;
    load();
  }

  function hide() {
    if (!view || view.hidden) return;
    view.hidden = true;
    tab.setAttribute("aria-selected", "false");
    document.querySelector(".wrap").classList.remove("kb-wide");
  }

  function load() {
    Promise.all([call("GET", "/me"), call("GET", "/kb/decisions")]).then(function (r) {
      me = r[0].username;
      server = {};
      maxSeq = 0;
      r[1].decisions.forEach(function (d) { server[d.key] = d; });
      chain = { ok: r[1].chain_ok, msg: r[1].chain };
      maxSeq = r[1].total_rows ? Math.max.apply(null, r[1].decisions.map(function (d) { return d.seq; }).concat([0])) : 0;
      lastRows = r[1].total_rows;
      render();
      renderSaveBar();
    }, function (e) {
      body.textContent = "";
      if (e.status === 401) {
        body.appendChild(el("div", { class: "panel" }, [
          el("h2", { text: "אישור קליני" }),
          el("p", { text: "צריך להתחבר כמטפל/ת כדי לאשר את מאגר הידע. ההחלטות נחתמות בשם המשתמש שלך." }),
          el("div", { class: "answers" }, [el("button", { class: "btn", type: "button", text: "לכניסה (לשונית תיקים)", onclick: function () { var t = document.getElementById("tab-records"); if (t) t.click(); } })])
        ]));
      } else body.appendChild(el("p", { class: "flag red", text: "השרת לא זמין: " + e.message }));
    });
  }
  var lastRows = 0;

  // ---- the page ----
  function render() {
    if (!body) return;
    var scrollY = window.scrollY;
    var oldList = body.querySelector(".kb-list"), listTop = oldList ? oldList.scrollTop : 0;
    body.textContent = "";
    body.appendChild(header());
    if (sub === "patterns") body.appendChild(patternsView());
    else if (sub === "features") body.appendChild(featuresView());
    else if (sub === "safety") body.appendChild(safetyView());
    else body.appendChild(logView());
    var newList = body.querySelector(".kb-list");
    if (newList) newList.scrollTop = listTop;
    window.scrollTo(0, scrollY);
  }

  function header() {
    var decided = Object.keys(server).length;
    var notBuilt = lastRows > (built.head_seq || 0);
    var head = el("div", { class: "panel" }, [
      el("div", { class: "row", style: "justify-content:space-between" }, [
        el("h2", { text: "אישור קליני של מאגר הידע" }),
        el("span", { class: "hint" }, ["מחובר/ת: " + me])
      ]),
      el("p", { class: "hint", text: "כל תבנית, קשר בין תבנית לממצא ומשקלו, נוסח שאלה, הצעת טיפול וכלל בטיחות נבנו אוטומטית ממקורות, והם טיוטה. כאן מאשרים, משנים משקל, דוחים או מוסיפים. ההחלטות נאספות עד \"חתימה ושמירה\", ואז נרשמות ביומן חתום בשמך שאי אפשר לשנות בדיעבד. קובצי המקור לא משתנים: הבנייה הבאה של ההתאמה ותכנית הטיפול קוראת את ההחלטות ומחילה אותן." }),
      el("div", { class: "row" }, [
        el("span", { class: "progress", text: decided + " פריטים עם החלטה · " + lastRows + " רשומות ביומן" }),
        el("span", { class: chain.ok ? "approved" : "badge red", text: chain.ok ? "היומן תקין" : "היומן נפגע: " + chain.msg }),
        el("a", { class: "btn ghost", href: API + "/kb/export", download: "decisions.json", text: "הורדת קובץ ההחלטות" })
      ])
    ]);
    if (notBuilt) head.appendChild(el("div", { class: "flag amber" }, [
      "יש " + (lastRows - (built.head_seq || 0)) + " רשומות ביומן שעוד לא נכנסו להתאמה ולתכנית הטיפול. כדי להחיל אותן, בשרת: ",
      el("code", { dir: "ltr", text: "python -m server.manage kb-export && python3 tools/interview/build_interview.py && python3 tools/treatment/build_treatment.py" })
    ]));
    if ((built.changed || []).length) head.appendChild(el("div", { class: "flag info", text: built.changed.length + " קשרים השתנו במקור מאז שהוחלט עליהם (מסומנים \"המקור השתנה\"). ההחלטה שלך עדיין חלה; כדאי לעבור עליהם." }));
    var tabs = el("div", { class: "kb-sub", role: "group", "aria-label": "מה לאשר" });
    [["patterns", "תבניות, ממצאים וטיפול"], ["features", "מילון הממצאים"], ["safety", "כללי בטיחות"], ["log", "יומן ההחלטות"]].forEach(function (t) {
      tabs.appendChild(el("button", { type: "button", "aria-pressed": String(sub === t[0]), text: t[1], onclick: function () { sub = t[0]; render(); } }));
    });
    head.appendChild(tabs);
    return head;
  }

  // ---- patterns ----
  function patternName(s) { return s.he || I.he(s.zh) || s.en || s.zh; }

  function linkProgress() {
    var per = {};
    function add(key) {
      if (key.indexOf("link:") !== 0) return;
      var sid = key.slice(5).split("|")[0];
      per[sid] = (per[sid] || 0) + 1;
    }
    Object.keys(server).forEach(add);
    Object.keys(pending).forEach(function (k) { if (!server[k]) add(k); });
    return per;
  }

  function filteredPatterns() {
    var q = list.q.trim().toLowerCase();
    var per = linkProgress();
    return KB.syndromes.filter(function (s) {
      if (list.set === "who" && s.prior !== undefined) return false;
      if (list.set === "gb" && s.prior === undefined) return false;
      var st = stateOf(pKey(s.id)), n = per[s.id] || 0;
      if (list.status === "todo" && (st !== "draft" || n)) return false;
      if (list.status === "partial" && !(st === "draft" && n)) return false;
      if (list.status === "approved" && st !== "approved") return false;
      if (list.status === "rejected" && st !== "rejected") return false;
      if (!q) return true;
      return [s.id, s.en, s.zh, s.py, patternName(s), s.gb || ""].join(" ").toLowerCase().indexOf(q) !== -1;
    }).map(function (s) { return { s: s, n: per[s.id] || 0 }; });
  }

  function patternsView() {
    var items = filteredPatterns();
    if (!list.sid || !synById[list.sid]) list.sid = items.length ? items[0].s.id : null;
    var search = el("input", { type: "search", placeholder: "חיפוש: עברית, 中文, English, מזהה", value: list.q, "aria-label": "חיפוש תבנית" });
    search.addEventListener("input", function () { list.q = search.value; list.shown = PAGE; var pos = search.selectionStart; render(); var s2 = view.querySelector(".kb-filters input[type=search]"); s2.focus(); s2.setSelectionRange(pos, pos); });
    function sel(name, value, opts) {
      return el("select", { "aria-label": name, onchange: function (e) { list[value] = e.target.value; list.shown = PAGE; render(); } },
        opts.map(function (o) { return el("option", { value: o[0], text: o[1], selected: list[value] === o[0] ? "selected" : null }); }));
    }
    var listBox = el("div", { class: "panel kb-list", role: "list" });
    items.slice(0, list.shown).forEach(function (it) {
      var s = it.s, total = s.links.length + (s.rej || []).length;
      var pct = total ? Math.min(100, Math.round(100 * it.n / total)) : 0;
      listBox.appendChild(el("button", { type: "button", role: "listitem", "aria-current": String(s.id === list.sid), onclick: function () { list.sid = s.id; render(); } }, [
        el("span", {}, [el("b", { text: patternName(s) }), " ", zh(s.zh)]),
        el("span", { class: "meta" }, [s.prior !== undefined ? "GB · " : "WHO · ", it.n + "/" + total + " ממצאים · ", chip(pKey(s.id))]),
        el("span", { class: "kb-bar", "aria-hidden": "true" }, [el("i", { style: "width:" + pct + "%" })])
      ]));
    });
    if (items.length > list.shown) listBox.appendChild(el("button", { type: "button", class: "mini", text: "עוד " + Math.min(PAGE, items.length - list.shown) + " מתוך " + (items.length - list.shown), onclick: function () { list.shown += PAGE; render(); } }));
    if (!items.length) listBox.appendChild(el("p", { class: "empty", text: "אין תבניות שמתאימות לסינון." }));
    var left = el("div", { style: "display:grid;gap:8px" }, [
      el("div", { class: "kb-filters" }, [search,
        sel("מקור", "set", [["who", "WHO 2022 (" + KB.syndromes.filter(function (s) { return s.prior === undefined; }).length + ")"], ["gb", "GB/T בלבד"], ["all", "הכול"]]),
        sel("מצב", "status", [["all", "כל המצבים"], ["todo", "טרם נבדקה"], ["partial", "בתהליך"], ["approved", "אושרה"], ["rejected", "נדחתה"]])
      ]),
      el("span", { class: "progress", text: items.length + " תבניות" }),
      listBox
    ]);
    return el("div", { class: "kb-cols" }, [left, list.sid ? patternDetail(synById[list.sid]) : el("div", {})]);
  }

  function srcChips(l) {
    var names = { WHO: "WHO", GB: "GB/T", "TCM-SD": "TCM-SD", clinician: "מטפל/ת" };
    return el("span", {}, l.src.map(function (x) { return el("span", { class: "kb-src", text: names[x] || x }); })
      .concat(l.sd ? [el("span", { class: "kb-src", title: "רשומות TCM-SD של התבנית שמדווחות על הממצא", text: l.sd })] : []));
  }

  function draftW(l) {
    if (l.src.length === 1 && l.src[0] === "clinician") return null;
    return l.dw !== undefined ? l.dw : l.w !== undefined ? l.w : DEFAULT_W;
  }

  function linkDraft(l) {
    var w = draftW(l);
    return w === null ? null : { w: w, src: l.src.slice().sort() };
  }

  function linkRow(s, l) {
    var key = lKey(s.id, l.f), st = stateOf(key), d = decisionOf(key), f = featById[l.f] || { label_he: l.f };
    var dw = draftW(l);
    var w = d && d.action === "edit" ? d.value.w : dw;
    var input = el("input", { type: "number", min: "0.1", max: "5", step: "0.1", value: w === null ? "" : w, "aria-label": "משקל " + f.label_he });
    input.addEventListener("change", function () {
      var v = parseFloat(input.value);
      if (!(v >= 0.1 && v <= 5)) { input.value = w; return; }
      if (dw !== null && v === dw && (!server[key] || server[key].action !== "edit")) decide(key, "approve", { draft: linkDraft(l) });
      else decide(key, "edit", { value: { w: Math.round(v * 100) / 100 }, draft: linkDraft(l) });
    });
    return el("tr", { class: "kb-st-" + st }, [
      el("td", {}, [el("b", { text: f.label_he }), el("div", { class: "kb-hash", text: l.f })]),
      el("td", {}, [srcChips(l)]),
      el("td", { class: "ev" }, [l.ev || "", l.ev_zh ? el("div", {}, [zh(l.ev_zh)]) : null]),
      el("td", { class: "score", text: dw === null ? "—" : String(dw) }),
      el("td", {}, [input]),
      el("td", {}, [chip(key)]),
      el("td", {}, [actions(key, { draft: linkDraft(l), approve: dw !== null })])
    ]);
  }

  function patternDetail(s) {
    var key = pKey(s.id);
    var box = el("div", { style: "display:grid;gap:14px;min-width:0" });
    var srcRef = I.source(s.src);
    box.appendChild(el("div", { class: "panel" }, [
      el("div", { class: "row", style: "justify-content:space-between" }, [
        el("div", {}, [el("h2", { style: "margin:0" }, [patternName(s), " ", zh(s.zh + " " + (s.py || ""))]), el("div", { class: "en", text: s.en || "" })]),
        el("span", { class: "row" }, [chip(key), actions(key, { rejectTitle: "דחיית התבנית: היא לא תוצע כמועמדת", askNote: "דחיית התבנית: היא לא תדורג בהתאמה. סיבה (לא חובה):" })])
      ]),
      el("div", { class: "hint" }, [el("span", { class: "kb-hash", text: s.id }), " · " + (s.cat || ""), s.gb ? " · GB/T " + s.gb : "", " · ",
        srcRef ? el("a", { href: srcRef.url, target: "_blank", rel: "noopener noreferrer", text: srcRef.he + (s.src ? " (" + s.src.replace(/^\S+ /, "") + ")" : "") }) : (s.src || "")]),
      s.text ? el("div", { class: "kb-text", lang: "en", dir: "ltr", text: s.text }) : null,
      s.tongue || s.pulse ? el("div", { class: "hint", dir: "ltr", lang: "en", text: [s.tongue && "Tongue: " + s.tongue, s.pulse && "Pulse: " + s.pulse].filter(Boolean).join(" · ") }) : null,
      s.gbtext ? el("div", { class: "kb-text", lang: "zh", text: s.gbtext }) : null
    ]));

    // findings
    var links = s.links.concat(s.rej || []);
    var seen = {};
    links.forEach(function (l) { seen[l.f] = true; });
    // links the clinician added but that are not in the built data yet
    Object.keys(pending).concat(Object.keys(server)).forEach(function (k) {
      var pre = "link:" + s.id + "|";
      if (k.indexOf(pre) === 0) {
        var fid = k.slice(pre.length);
        if (!seen[fid] && featById[fid]) { seen[fid] = true; links.push({ f: fid, ev: "נוסף על ידי המטפל/ת", src: ["clinician"] }); }
      }
    });
    var table = el("table", { class: "kb" }, [el("tr", {}, ["ממצא", "מקור", "ראיה", "טיוטה", "משקל", "מצב", ""].map(function (h) { return el("th", { text: h }); }))]);
    links.forEach(function (l) { table.appendChild(linkRow(s, l)); });
    var undecided = links.filter(function (l) { return stateOf(lKey(s.id, l.f)) === "draft" && draftW(l) !== null; });
    var addSel = el("select", { "aria-label": "ממצא להוספה" }, [el("option", { value: "", text: "הוספת ממצא לתבנית…" })].concat(
      KB.features.filter(function (f) { return !seen[f.id]; }).map(function (f) { return el("option", { value: f.id, text: f.label_he + " (" + f.id + ")" }); })));
    var addW = el("input", { type: "number", min: "0.1", max: "5", step: "0.1", value: String(DEFAULT_W), "aria-label": "משקל הממצא החדש", style: "width:5em" });
    box.appendChild(el("div", { class: "panel" }, [
      el("div", { class: "row", style: "justify-content:space-between" }, [
        el("h3", { text: "ממצאים ומשקלים (" + links.length + ")" }),
        undecided.length ? el("button", { class: "btn ghost", type: "button", text: "אישור " + undecided.length + " הממצאים שטרם נבדקו במשקל הטיוטה", onclick: function () {
          undecided.forEach(function (l) { pending[lKey(s.id, l.f)] = { key: lKey(s.id, l.f), action: "approve", draft: linkDraft(l) }; });
          refreshAfterChange();
        } }) : null
      ]),
      el("p", { class: "hint", text: "משקל: כמה הממצא מעיד על התבנית. 1 = ממצא רגיל, 2 = חשוב, 3 ומעלה = מרכזי/מאפיין, פחות מ-1 = משני. ממצא לא רלוונטי דוחים (✗). טיוטה = המשקל שחושב אוטומטית (1.0 אחיד, או לפי רשומות TCM-SD)." }),
      el("div", { class: "scroll" }, [table]),
      el("div", { class: "row" }, [addSel, el("label", { class: "row" }, ["משקל ", addW]), el("button", { class: "mini", type: "button", text: "הוספה", onclick: function () {
        var v = parseFloat(addW.value);
        if (!addSel.value || !(v >= 0.1 && v <= 5)) return;
        decide(lKey(s.id, addSel.value), "edit", { value: { w: Math.round(v * 100) / 100 }, draft: null });
      } })])
    ]));

    box.appendChild(treatmentPanel(s));
    return box;
  }

  // ---- treatment suggestions of a pattern ----
  function txName(kind, id) {
    if (kind === "method") {
      var m = TX.methods.filter(function (x) { return String(x.no) === String(id); })[0];
      return m ? [el("b", { text: I.heOr(m.zh) }), " ", zh(m.zh), " ", el("span", { class: "en", text: m.en })] : [id];
    }
    var row = (kind === "point" ? TX.points : kind === "herb" ? TX.herbs : TX.formulas)[id];
    if (!row) return [el("b", { text: id })];
    return [kind === "point" ? el("b", { text: id + " " }) : null, el("b", { text: I.he(row.zh) || row.py || "" }), " ", zh(row.zh + " " + (row.py || ""))];
  }

  function txWhy(kind, item) {
    if (kind === "method") { var m = TX.methods[item.i]; return m ? m.def : ""; }
    if (kind === "point") {
      var pt = TX.points[item.id];
      var acts = pt ? item.a.map(function (i) { return pt.act[i]; }) : [];
      return acts.join("; ") + (item.f && item.f.length ? (acts.length ? " · " : "") + "ממצאים בהתוויות: " + item.f.map(function (f) { return (featById[f] || {}).label_he || f; }).join(", ") : "");
    }
    if (kind === "herb") { var h = TX.herbs[item.id]; return h ? item.a.map(function (i) { return h.act[i]; }).join("，") : ""; }
    var parts = [];
    if (item.h && item.h.length) parts.push("צמחים נושאים: " + item.h.map(function (x) { var h = TX.herbs[x]; return h ? I.heOr(h.zh) : x; }).join(", "));
    if (item.q) parts.push(item.q.ev);
    return parts.join(" · ");
  }

  function treatmentPanel(s) {
    var l = TX.links[s.id] || { m: [], p: [], h: [], fm: [] };
    var panel = el("div", { class: "panel" }, [el("h3", { text: "הצעות טיפול לתבנית" }),
      el("p", { class: "hint", text: "הצעה שאושרה נשארת גם אם החישוב האוטומטי ישתנה ומסומנת \"מאושר\" בתכנית הטיפול. הצעה שנדחתה לא תוצע לתבנית הזו. מה שמוסיפים כאן מוצע ראשון. מינון בגרם לא נקבע כאן: הוא נקבע בתכנית של כל מטופל." })]);
    ["method", "point", "herb", "formula"].forEach(function (kind) {
      var items = (l[TX_LIST[kind]] || []).map(function (x) { return { id: kind === "method" ? String(TX.methods[x.i].no) : x.id, item: x }; });
      var seen = {};
      items.forEach(function (x) { seen[x.id] = true; });
      (l.x || []).forEach(function (x) { if (x.t === kind && !seen[x.id]) { seen[x.id] = true; items.push({ id: x.id, item: null }); } });
      Object.keys(pending).concat(Object.keys(server)).forEach(function (k) {
        var pre = "tx:" + s.id + "|" + kind + "|";
        if (k.indexOf(pre) === 0 && !seen[k.slice(pre.length)]) { seen[k.slice(pre.length)] = true; items.push({ id: k.slice(pre.length), item: null }); }
      });
      var table = el("table", { class: "kb" }, [el("tr", {}, [KIND_HE[kind], "למה הוצע", "ציון", "מצב", ""].map(function (h) { return el("th", { text: h }); }))]);
      items.forEach(function (x) {
        var key = tKey(s.id, kind, x.id);
        var srcRef = kind === "method" ? "WHO-ISTTCM-2022" : kind === "point" ? (TX.points[x.id] || {}).src : kind === "herb" ? (TX.herbs[x.id] || {}).src : (TX.formulas[x.id] || {}).src;
        table.appendChild(el("tr", { class: "kb-st-" + stateOf(key) }, [
          el("td", {}, txName(kind, x.id)),
          el("td", { class: "ev" }, [x.item ? txWhy(kind, x.item) : "", " ", srcRef ? srcLink(srcRef) : null]),
          el("td", { class: "score", text: x.item && x.item.s !== undefined && !x.item.add ? String(x.item.s) : "—" }),
          el("td", {}, [chip(key)]),
          el("td", {}, [actions(key, { draft: x.item ? { s: x.item.s } : null })])
        ]));
      });
      var det = el("details", { open: kind === "point" || kind === "formula" ? "" : null }, [el("summary", { text: KIND_HE[kind] + " (" + items.length + ")" })]);
      if (items.length) det.appendChild(el("div", { class: "scroll" }, [table]));
      else det.appendChild(el("p", { class: "empty", text: "אין הצעות." }));
      if (kind !== "method") det.appendChild(addTx(s, kind, seen));
      panel.appendChild(det);
    });
    return panel;
  }

  function addTx(s, kind, seen) {
    var src = kind === "point" ? TX.points : kind === "herb" ? TX.herbs : TX.formulas;
    var dl = "kb-dl-" + kind;
    if (!document.getElementById(dl)) {
      var list = el("datalist", { id: dl });
      Object.keys(src).forEach(function (id) { var r = src[id]; list.appendChild(el("option", { value: id, label: [I.he(r.zh), r.zh, r.py].filter(Boolean).join(" · ") })); });
      document.body.appendChild(list);
    }
    var input = el("input", { type: "text", list: dl, placeholder: kind === "point" ? "מזהה נקודה, למשל LR3" : "מזהה או שם", "aria-label": "הוספת " + KIND_HE[kind], style: "max-width:18em;font:inherit;font-size:.88rem;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink)" });
    var msg = el("span", { class: "progress" });
    return el("div", { class: "row" }, [input, el("button", { class: "mini", type: "button", text: "הוספה לתבנית", onclick: function () {
      var v = input.value.trim(), id = src[v] ? v : null;
      if (!id) {   // a name: Chinese, pinyin or Hebrew
        Object.keys(src).some(function (k) { var r = src[k]; if (r.zh === v || r.py === v || I.he(r.zh) === v) { id = k; return true; } return false; });
      }
      if (!id) { msg.textContent = "לא נמצא במאגר."; return; }
      if (seen[id]) { msg.textContent = "כבר ברשימה: אפשר לאשר אותו."; return; }
      decide(tKey(s.id, kind, id), "add", { draft: null });
    } }), msg]);
  }

  // ---- lexicon ----
  function featuresView() {
    var counts = {};
    KB.syndromes.forEach(function (s) { s.links.forEach(function (l) { counts[l.f] = (counts[l.f] || 0) + 1; }); });
    var table = el("table", { class: "kb" }, [el("tr", {}, ["ממצא", "שאלה למטופל", "תווית לסיכום", "מילים בטקסט חופשי", "תבניות", "מצב", ""].map(function (h) { return el("th", { text: h }); }))]);
    KB.features.forEach(function (f) {
      var key = "feature:" + f.id, d = decisionOf(key);
      var draft = f.draft_he ? Object.assign({ q_he: f.q_he, label_he: f.label_he }, f.draft_he) : { q_he: f.q_he || "", label_he: f.label_he || "" };
      var cur = d && d.action === "edit" ? Object.assign({}, draft, d.value) : draft;
      function field(name) {
        if (name === "q_he" && !f.q_he && !(d && d.value && d.value.q_he)) return el("span", { class: "hint", text: "(נקבע על ידי המטפל, ללא שאלה)" });
        var inp = el("input", { type: "text", value: cur[name] || "", "aria-label": name + " " + f.id });
        inp.addEventListener("change", function () {
          var val = {};
          val.q_he = name === "q_he" ? inp.value.trim() : cur.q_he;
          val.label_he = name === "label_he" ? inp.value.trim() : cur.label_he;
          var out = {};
          if (val.q_he && val.q_he !== draft.q_he) out.q_he = val.q_he;
          if (val.label_he && val.label_he !== draft.label_he) out.label_he = val.label_he;
          if (Object.keys(out).length) decide(key, "edit", { value: out, draft: { q_he: draft.q_he, label_he: draft.label_he } });
          else decide(key, "approve", { draft: { q_he: draft.q_he, label_he: draft.label_he } });
        });
        return inp;
      }
      table.appendChild(el("tr", { class: "kb-st-" + stateOf(key) }, [
        el("td", {}, [el("span", { class: "kb-hash", text: f.id }), el("div", { class: "hint", text: f.group || "" })]),
        el("td", {}, [field("q_he")]),
        el("td", {}, [field("label_he")]),
        el("td", { class: "ev", text: (f.syn_he || []).join(", ") }),
        el("td", { class: "score", text: String(counts[f.id] || 0) }),
        el("td", {}, [chip(key)]),
        el("td", {}, [actions(key, { reject: false, draft: { q_he: draft.q_he, label_he: draft.label_he } })])
      ]));
    });
    return el("div", { class: "panel" }, [
      el("h3", { text: "מילון הממצאים (" + KB.features.length + ")" }),
      el("p", { class: "hint", text: "הנוסח של כל שאלה ותווית. שינוי נוסח נשמר כהחלטה ומחליף את הטיוטה בבנייה הבאה; הנוסח המקורי נשמר לצידו. המילים לזיהוי בטקסט חופשי נערכות בקובץ המילון." }),
      el("div", { class: "scroll" }, [table])
    ]);
  }

  // ---- safety rules ----
  function safetyView() {
    var COND = { pregnancy: "הריון", other: "שילוב אסור", drug: "תרופות" };
    var SEV = { contraindicated: "אסור", caution: "זהירות" };
    var table = el("table", { class: "kb" }, [el("tr", {}, ["כלל", "רכיבים", "חומרה", "מקור", "מצב", ""].map(function (h) { return el("th", { text: h }); }))]);
    TX.safety.forEach(function (r) {
      var key = "safety:" + r.id;
      var names = r.ids.map(function (id) { var h = TX.herbs[id] || TX.points[id] || TX.formulas[id]; return h ? (I.he(h.zh) || h.zh) : id; }).join(" + ");
      var st = stateOf(key), d = decisionOf(key);
      var act = el("span", { class: "mini-row kb-act" }, [
        el("button", { class: "mini" + (st === "approved" ? " on" : ""), type: "button", title: "אישור הכלל", text: "✓", onclick: function () { decide(key, "approve"); } }),
        el("button", { class: "mini ghost", type: "button", title: "מחלוקת: הכלל ממשיך לפעול, עם ההערה שלך", text: "מחלוקת", onclick: function () {
          var note = window.prompt("הכלל ימשיך להתריע. מה לא מדויק בו? (חובה)", d && d.note || "");
          if (note && note.trim()) decide(key, "dispute", { note: note.trim() });
        } }),
        st !== "draft" || pending[key] ? el("button", { class: "mini ghost", type: "button", title: "החזרה לטיוטה", text: "↺", onclick: function () { decide(key, "reset"); } }) : null
      ]);
      table.appendChild(el("tr", { class: "kb-st-" + st }, [
        el("td", {}, [el("b", { text: I.he(r.note) || r.note }), el("div", { class: "kb-hash", text: r.id }), d && d.action === "dispute" ? el("div", { class: "flag amber", text: "מחלוקת: " + d.note }) : null]),
        el("td", { text: names }),
        el("td", {}, [el("span", { class: "badge" + (r.sev === "contraindicated" ? " red" : " amber"), text: (SEV[r.sev] || r.sev) + " · " + (COND[r.cond] || r.cond) })]),
        el("td", { class: "ev" }, [srcLink(r.src) || r.src]),
        el("td", {}, [chip(key)]),
        el("td", {}, [act])
      ]));
    });
    return el("div", { class: "panel" }, [
      el("h3", { text: "כללי בטיחות (" + TX.safety.length + ")" }),
      el("p", { class: "flag info", text: "כללי בטיחות לא מכבים מכאן. אישור מסמן שהכלל נבדק. \"מחלוקת\" מוסיפה את ההערה שלך, והכלל ממשיך להתריע בבדיקת הבטיחות, כי אזהרה מודרנית קודמת לשיקול הדעת בסקירה." }),
      el("div", { class: "scroll" }, [table])
    ]);
  }

  // ---- the log ----
  var logFilter = "";
  function logView() {
    var box = el("div", { class: "panel" }, [el("h3", { text: "יומן ההחלטות" }), el("p", { class: "progress", text: "טוען…" })]);
    call("GET", "/kb/log?limit=1000").then(function (r) {
      box.textContent = "";
      var search = el("input", { type: "search", placeholder: "סינון לפי מזהה, פעולה או משתמש", value: logFilter, "aria-label": "סינון היומן" });
      var table = el("table", { class: "kb" });
      function fill() {
        table.textContent = "";
        table.appendChild(el("tr", {}, ["#", "מתי", "מי", "פריט", "פעולה", "ערך", "הערה", "חותם"].map(function (h) { return el("th", { text: h }); })));
        var q = logFilter.toLowerCase();
        r.rows.filter(function (x) { return !q || [x.key, x.action, x.actor, x.note].join(" ").toLowerCase().indexOf(q) !== -1; }).slice(0, 400).forEach(function (x) {
          table.appendChild(el("tr", {}, [
            el("td", { class: "score", text: String(x.seq) }),
            el("td", { text: when(x.at) }),
            el("td", { text: x.actor.replace(/^clinician:/, "") }),
            el("td", { class: "kb-hash", dir: "ltr", text: x.key }),
            el("td", { text: { approve: "אישור", edit: "עריכה", reject: "דחייה", add: "הוספה", dispute: "מחלוקת", reset: "החזרה לטיוטה" }[x.action] || x.action }),
            el("td", { class: "ev", dir: "ltr", text: x.value ? JSON.stringify(x.value) : "" }),
            el("td", { class: "ev", text: x.note || "" }),
            el("td", { class: "kb-hash", title: x.hash, text: x.hash.slice(0, 10) })
          ]));
        });
      }
      search.addEventListener("input", function () { logFilter = search.value; fill(); });
      fill();
      box.appendChild(el("h3", { text: "יומן ההחלטות (" + r.total_rows + ")" }));
      box.appendChild(el("p", { class: "hint", text: "כל שורה נחתמת בשרת ומקושרת בגיבוב לשורה שלפניה, כך ששינוי או מחיקה של שורה נחשפים בבדיקה. " + (chain.ok ? "הבדיקה האחרונה: היומן תקין." : "הבדיקה האחרונה: " + chain.msg) }));
      box.appendChild(el("div", { class: "kb-filters" }, [search]));
      box.appendChild(el("div", { class: "scroll" }, [table]));
    }, function (e) { box.appendChild(el("p", { class: "flag red", text: "טעינת היומן נכשלה: " + e.message })); });
    return box;
  }

  // ---- sign and save ----
  function renderSaveBar() {
    var keys = Object.keys(pending);
    saveBar.textContent = "";
    saveBar.hidden = !keys.length;
    if (!keys.length) return;
    var note = el("input", { type: "text", class: "note", placeholder: "הערה לכל ההחלטות (לא חובה)", "aria-label": "הערה", style: "flex:1;min-width:12em" });
    var status = el("span", { class: "progress", role: "status" });
    var save = el("button", { class: "btn", type: "button", text: "חתימה ושמירה בשם " + me });
    save.addEventListener("click", function () {
      save.disabled = true;
      status.textContent = "שומר…";
      var batch = keys.map(function (k) { var d = Object.assign({}, pending[k]); if (!d.note && note.value.trim()) d.note = note.value.trim(); return d; });
      var chunks = [];
      for (var i = 0; i < batch.length; i += 500) chunks.push(batch.slice(i, i + 500));
      chunks.reduce(function (p, chunk) {
        return p.then(function () {
          return call("POST", "/kb/decisions", { decisions: chunk }).then(function (r) {
            r.saved.forEach(function (row) {
              delete pending[row.key];
              if (row.action === "reset") delete server[row.key]; else server[row.key] = row;
              maxSeq = Math.max(maxSeq, row.seq);
              lastRows += 1;
            });
          });
        });
      }, Promise.resolve()).then(function () { render(); renderSaveBar(); }, function (e) {
        save.disabled = false;
        status.textContent = (e.status === 401 ? "פג תוקף הכניסה. התחברו שוב בלשונית תיקים; ההחלטות שלא נשמרו נשארות כאן." : "השמירה נכשלה: " + e.message);
        render();
      });
    });
    saveBar.appendChild(el("div", { class: "row", style: "justify-content:space-between" }, [
      el("b", { text: keys.length + " החלטות ממתינות לחתימה" }),
      el("span", { class: "mini-row" }, [save, el("button", { class: "btn ghost", type: "button", text: "ביטול השינויים", onclick: function () {
        if (!window.confirm("לבטל " + keys.length + " החלטות שלא נשמרו?")) return;
        pending = {}; render(); renderSaveBar();
      } })])
    ]));
    saveBar.appendChild(el("div", { class: "row" }, [note]));
    saveBar.appendChild(el("p", { class: "hint", text: "ההחלטות נרשמות ביומן בשמך, עם התאריך והטיוטה שראית. אי אפשר למחוק רשומה; כדי לחזור בך מחליטים שוב (↺ מחזיר לטיוטה)." }));
    saveBar.appendChild(status);
  }

  window.TCMApprovals = { pendingCount: function () { return Object.keys(pending).length; } };

  if (location.protocol === "file:") return;
  fetch(API + "/health", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { if (j && j.service === "tcm-clinic-server") install(); }, function () { /* no server: static prototype */ });
})();
