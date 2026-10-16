// Treatment step of the interview prototype: draft suggestions per pattern, the safety check, and the
// clinician's plan editor. Suggestions come from app/interview/treatment_kb.js (built by
// tools/treatment/build_treatment.py); every one names its source and is a draft for the clinician.
// No gram dose is ever suggested: dose fields start empty and only the clinician fills them.
// The logic (suggest, checkSafety, newPlan) runs in Node too, so tests can drive it.
(function (root) {
  "use strict";

  var PATIENT_POINT_BONUS = 0.6;     // per patient finding a point's indications list
  var PATIENT_FORMULA_BONUS = 0.4;   // per patient finding a formula's clauses describe
  var SECOND_PATTERN_SHARE = 0.6;    // a second selected pattern counts this much
  var DEFAULT_POINTS = 6, DEFAULT_SHIATSU = 5;
  var BLOOD_MOVING = /活血|破血|破宿血|逐瘀|散瘀|祛瘀|去瘀|化瘀|行血|破瘀|通经/;   // DRAFT heuristic, no source: checked against anticoagulants
  var NO_PRESSURE = /orbit|eyeball|canthus|nipple|umbilicus/i; // not offered for shiatsu pressure

  function createTreatment(tx) {
    var rulesByEntity = {};
    tx.safety.forEach(function (r) {
      r.ids.forEach(function (id) { (rulesByEntity[id] = rulesByEntity[id] || []).push(r); });
    });

    function addScore(map, id, score, extra) {
      var cur = map[id];
      if (!cur) { cur = map[id] = { id: id, score: 0, from: [] }; }
      cur.score += score;
      if (extra) cur.from.push(extra);
      return cur;
    }

    // Suggestions for the selected patterns, re-ranked by the patient's own present findings.
    function suggest(patternIds, presentFindings) {
      var present = {};
      (presentFindings || []).forEach(function (f) { present[f] = true; });
      var methods = [], points = {}, herbs = {}, formulas = {};
      patternIds.forEach(function (sid, n) {
        var l = tx.links[sid];
        if (!l) return;
        var share = n === 0 ? 1 : SECOND_PATTERN_SHARE;
        l.m.forEach(function (m) {
          if (!methods.some(function (x) { return x.i === m.i; })) {
            methods.push({ i: m.i, s: m.s, sid: sid, method: tx.methods[m.i] });
          }
        });
        l.p.forEach(function (p) {
          var pt = tx.points[p.id];
          addScore(points, p.id, p.s * share, { sid: sid, actions: p.a.map(function (i) { return pt.act[i]; }), findings: p.f });
        });
        l.h.forEach(function (h) {
          var herb = tx.herbs[h.id];
          addScore(herbs, h.id, h.s * share, { sid: sid, actions: h.a.map(function (i) { return herb.act[i]; }) });
        });
        l.fm.forEach(function (f) {
          addScore(formulas, f.id, f.s * share, { sid: sid, herbs: f.h, findings: f.f });
        });
      });
      Object.keys(points).forEach(function (id) {
        var hits = tx.points[id].find.filter(function (x) { return present[x.f]; });
        points[id].patient = hits;
        points[id].score += PATIENT_POINT_BONUS * hits.length;
      });
      Object.keys(formulas).forEach(function (id) {
        var hits = tx.formulas[id].find.filter(function (x) { return present[x.f]; });
        formulas[id].patient = hits;
        formulas[id].score += PATIENT_FORMULA_BONUS * hits.length;
      });
      function ranked(map) {
        return Object.keys(map).map(function (k) { return map[k]; })
          .sort(function (a, b) { return b.score - a.score || (a.id < b.id ? -1 : 1); });
      }
      return { methods: methods, points: ranked(points), herbs: ranked(herbs), formulas: ranked(formulas) };
    }

    function pregnancyRisk(id) {
      return (rulesByEntity[id] || []).filter(function (r) { return r.cond === "pregnancy"; });
    }

    function shiatsuAllowed(id) {
      return !NO_PRESSURE.test(tx.points[id].loc || "");
    }

    // A first plan from the suggestions. With a reported pregnancy every item a pregnancy rule names
    // starts unselected; with an unconfirmed status, the contraindicated ones. The clinician can add them back.
    function newPlan(patternIds, sugg, patient) {
      var pregnancy = patient && patient.pregnancy;
      function blocked(id) {
        return pregnancyRisk(id).some(function (r) {
          return pregnancy === "yes" || (pregnancy === "unknown" && r.sev === "contraindicated");
        });
      }
      var formula = sugg.formulas[0] ? sugg.formulas[0].id : null;
      var plan = {
        patterns: patternIds.slice(),
        principle_he: "",
        methods: sugg.methods.map(function (m) { return m.i; }),
        points: [], shiatsu: [], formula_id: formula, herbs: [],
        followup: { interval: "week", sessions: "", notes_he: "" },
        decisions: {}, clinician_note: "", dirty: false
      };
      sugg.points.filter(function (p) { return !blocked(p.id); }).slice(0, DEFAULT_POINTS).forEach(function (p) {
        plan.points.push({ id: p.id, technique: "even", moxa: false, note: "", origin: "suggested" });
      });
      sugg.points.filter(function (p) { return !blocked(p.id) && shiatsuAllowed(p.id); }).slice(0, DEFAULT_SHIATSU).forEach(function (p) {
        plan.shiatsu.push({ id: p.id, note: "", origin: "suggested" });
      });
      if (formula) setFormula(plan, formula);
      return plan;
    }

    function setFormula(plan, formulaId) {
      plan.formula_id = formulaId;
      plan.herbs = plan.herbs.filter(function (h) { return h.origin === "added"; });
      if (!formulaId) return;
      tx.formulas[formulaId].comp.forEach(function (c) {
        if (!c.h || plan.herbs.some(function (h) { return h.id === c.h; })) return;
        plan.herbs.push({ id: c.h, dose_original: c.d, dose_g: "", note: "", origin: "formula" });
      });
    }

    // Safety check of a plan. Each issue: {sev: red|amber|info, he, ids, rule, src}.
    function checkSafety(plan, patient, constraints) {
      var out = [];
      var pregnancy = (patient && patient.pregnancy) || "na";
      var herbIds = plan.herbs.map(function (h) { return h.id; });
      var pointIds = plan.points.map(function (p) { return p.id; });
      var pressIds = plan.shiatsu.map(function (p) { return p.id; });
      var all = herbIds.concat(pointIds, pressIds);
      var seen = {};
      function push(issue) {
        var key = issue.rule + "|" + issue.ids.join(",");
        if (seen[key]) return;
        seen[key] = true;
        out.push(issue);
      }
      if (pregnancy === "yes" || pregnancy === "unknown") {
        all.forEach(function (id) {
          pregnancyRisk(id).forEach(function (r) {
            var sev = r.sev === "contraindicated" ? "red" : "amber";
            if (pregnancy === "unknown") sev = "amber";
            push({ sev: sev, ids: [id], rule: r.id, src: r.src, note: r.note,
                   he: (pregnancy === "yes" ? "היריון: " : "סטטוס היריון לא אושר: ") + label(id) +
                       (r.sev === "contraindicated" ? " אסור בהיריון לפי המקור" : " דורש זהירות בהיריון לפי המקור") });
          });
        });
      }
      herbIds.forEach(function (id) {
        (rulesByEntity[id] || []).forEach(function (r) {
          if (r.cond !== "other") return;
          if (r.ids.length > 1) {
            if (r.ids.every(function (x) { return herbIds.indexOf(x) !== -1; })) {
              push({ sev: r.sev === "contraindicated" ? "red" : "amber", ids: r.ids, rule: r.id, src: r.src, note: r.note,
                     he: "שילוב אסור במרשם: " + r.ids.map(label).join(" + ") });
            }
          } else if (/毒/.test(r.note)) {
            push({ sev: "amber", ids: [id], rule: r.id, src: r.src, note: r.note, he: "צמח רעיל לפי המקור: " + label(id) });
          }
        });
      });
      plan.points.forEach(function (p) {
        (rulesByEntity[p.id] || []).forEach(function (r) {
          if (/NO_NEEDLE/.test(r.id)) {
            push({ sev: "amber", ids: [p.id], rule: r.id, src: r.src, note: r.note, he: "דיקור אסור בנקודה לפי 针灸大成: " + label(p.id) });
          } else if (/NO_MOXA/.test(r.id) && p.moxa) {
            push({ sev: "amber", ids: [p.id], rule: r.id, src: r.src, note: r.note, he: "מוקסה אסורה בנקודה לפי 针灸大成: " + label(p.id) });
          }
        });
        var caution = tx.points[p.id].caution;
        if (caution) {
          push({ sev: "info", ids: [p.id], rule: "ACUATLAS.CAUTION." + p.id, src: tx.points[p.id].src, note: caution,
                 he: "אזהרת דיקור: " + label(p.id) });
        }
      });
      (constraints || []).forEach(function (c) {
        if (c === "anticoagulant") {
          var moving = herbIds.filter(function (id) { return BLOOD_MOVING.test(tx.herbs[id].act.join("，")); });
          if (moving.length) {
            push({ sev: "red", ids: moving, rule: "DRAFT.ANTICOAGULANT.BLOOD_MOVING", src: "",
                   note: "Draft rule without a source: blood-moving herbs with anticoagulant or antiplatelet drugs.",
                   he: "נוגדי קרישה ברשימת התרופות, וצמחים שמניעים דם לפי המקור: " + moving.map(label).join(", ") + ". כלל טיוטה ללא מקור, לאישור המטפל" });
          }
          if (pointIds.length) {
            push({ sev: "amber", ids: [], rule: "DRAFT.ANTICOAGULANT.NEEDLING", src: "",
                   note: "Draft rule without a source: bleeding risk when needling patients on anticoagulants.",
                   he: "נוגדי קרישה: סיכון מוגבר לדימום בדיקור. כלל טיוטה ללא מקור, לאישור המטפל" });
          }
        } else if (c === "device" && pointIds.length) {
          push({ sev: "amber", ids: [], rule: "DRAFT.DEVICE.ELECTRO", src: "",
                 note: "Draft rule without a source: no electro-acupuncture with an implanted device.",
                 he: "קוצב או מכשיר מושתל: לא לחבר אלקטרו-דיקור. כלל טיוטה ללא מקור, לאישור המטפל" });
        } else if (c === "organ" && herbIds.length) {
          push({ sev: "amber", ids: [], rule: "DRAFT.ORGAN.HERBS", src: "",
                 note: "Draft rule without a source: herbs with liver or kidney disease.",
                 he: "מחלת כבד או כליות ברקע: לבדוק כל צמח במרשם. כלל טיוטה ללא מקור, לאישור המטפל" });
        } else if (c === "allergy" && herbIds.length) {
          push({ sev: "amber", ids: [], rule: "DRAFT.ALLERGY", src: "", note: "Allergy reported.",
                 he: "דווחה אלרגיה: לבדוק את הרכב המרשם מול האלרגיה" });
        }
      });
      plan.herbs.forEach(function (h) {
        if (h.dose_g === "" || h.dose_g === null || h.dose_g === undefined) {
          push({ sev: "info", ids: [h.id], rule: "DOSE.MISSING." + h.id, src: "", note: "",
                 he: "לא נקבע מינון בגרם: " + label(h.id) });
        }
      });
      var order = { red: 0, amber: 1, info: 2 };
      out.sort(function (a, b) { return order[a.sev] - order[b.sev]; });
      return out;
    }

    function label(id) {
      if (tx.points[id]) return id + " " + tx.points[id].zh;
      if (tx.herbs[id]) return tx.herbs[id].zh + " " + tx.herbs[id].py;
      return id;
    }

    return { suggest: suggest, newPlan: newPlan, setFormula: setFormula, checkSafety: checkSafety,
             pregnancyRisk: pregnancyRisk, shiatsuAllowed: shiatsuAllowed, label: label, tx: tx };
  }

  var api = { createTreatment: createTreatment };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TCMTreatment = api;

  // ---------------- browser UI ----------------
  var T = createTreatment(root.TCM_TX);
  var tx = root.TCM_TX;
  var plan = null;          // the plan being edited
  var userPicked = false;   // the clinician chose the patterns, so a re-ranking does not move them
  var ctx = null;           // {report, state, featById, rerender}
  var host = null;
  var STORE = "tcm_treatment_plans.v1";

  var TECH = { even: "ניטרלי", tonify: "חיזוק (補)", reduce: "פיזור (瀉)" };
  var INTERVAL = { week: "בעוד שבוע", two_weeks: "בעוד שבועיים", month: "בעוד חודש", custom: "אחר (בהערות)" };

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === undefined || v === null || v === false) return;
      if (k === "text") n.textContent = v;
      else if (k === "class") n.className = v;
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
      else if (k === "value") n.value = v;
      else if (k === "checked") n.checked = !!v;
      else n.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }

  function presentFindings() {
    return ctx.report.findings.filter(function (f) { return f.value === "present"; }).map(function (f) { return f.feature_id; });
  }
  function constraints() {
    return (ctx.state.flags || []).filter(function (f) { return f.category === "C"; }).map(function (f) { return f.type; });
  }
  function patternName(sid) {
    var d = ctx.report.differential.filter(function (x) { return x.syndrome_id === sid; })[0];
    if (d) return d.names.en + " " + d.names.zh;
    var l = (root.TCM_KB.syndromes || []).filter(function (s) { return s.id === sid; })[0];
    return l ? l.en + " " + l.zh : sid;
  }

  function render(container, context) {
    host = container;
    ctx = context;
    var diff = ctx.report.differential;
    host.textContent = "";
    host.appendChild(el("h2", {}, ["תכנית טיפול ", el("span", { class: "draft", text: "טיוטה · כל קישור לאישור המטפל" })]));
    if (!diff.length) {
      host.appendChild(el("p", { class: "empty", text: "תכנית הטיפול תופיע אחרי שתהיה תבנית מובילה." }));
      return;
    }
    var ids = diff.map(function (d) { return d.syndrome_id; });
    if (!plan || !userPicked && !plan.dirty && plan.patterns[0] !== ids[0]) {
      build([ids[0]]);
    } else {
      plan.sugg = T.suggest(plan.patterns, presentFindings());   // the patient's findings may have changed
    }
    if (plan.patterns.some(function (sid) { return ids.indexOf(sid) === -1; }) || (!userPicked && plan.patterns[0] !== ids[0])) {
      host.appendChild(el("div", { class: "flag amber" }, [
        "הדירוג השתנה מאז שהתכנית נבנתה. ",
        el("button", { class: "mini", type: "button", text: "בנייה מחדש לפי התבנית המובילה",
                       onclick: function () { userPicked = false; build([ids[0]]); draw(); } })
      ]));
    }
    var body = el("div", { class: "tx", id: "tx-body" });
    host.appendChild(body);
    draw();
  }

  function build(patternIds) {
    var sugg = T.suggest(patternIds, presentFindings());
    plan = T.newPlan(patternIds, sugg, ctx.state.patient);
    plan.sugg = sugg;
  }

  function touch() { plan.dirty = true; draw(); }

  function decisionButtons(kind, id) {
    var key = plan.patterns[0] + "|" + kind + "|" + id;
    var cur = plan.decisions[key];
    function set(v) { if (cur === v) delete plan.decisions[key]; else plan.decisions[key] = v; touch(); }
    return el("span", { class: "mini-row", title: "החלטה על הקישור בין התבנית להצעה, לשמירה במאגר" }, [
      el("button", { class: "mini" + (cur === "approved" ? " on" : ""), type: "button", text: "אישור קישור", onclick: function () { set("approved"); } }),
      el("button", { class: "mini" + (cur === "rejected" ? " on no" : ""), type: "button", text: "דחייה", onclick: function () { set("rejected"); } })
    ]);
  }

  function findingNames(list) {
    return list.map(function (f) { var x = ctx.featById[f.f || f]; return x ? x.label_he : f.f || f; }).join(", ");
  }

  function draw() {
    var body = document.getElementById("tx-body");
    if (!body) return;
    body.textContent = "";
    var sugg = plan.sugg;
    var issues = T.checkSafety(plan, ctx.state.patient, constraints());

    // 1. patterns
    var diff = ctx.report.differential;
    body.appendChild(el("div", { class: "panel" }, [
      el("h3", { text: "התבניות שהתכנית מטפלת בהן" }),
      el("p", { class: "hint", text: "ברירת המחדל היא התבנית המובילה. אפשר לסמן תבנית נוספת, והצעות שלה ייכנסו במשקל נמוך יותר." }),
      el("div", { class: "checks" }, diff.map(function (d) {
        var on = plan.patterns.indexOf(d.syndrome_id) !== -1;
        return el("label", { class: "opt" }, [
          el("input", { type: "checkbox", checked: on, onchange: function (e) {
            var next = plan.patterns.filter(function (x) { return x !== d.syndrome_id; });
            if (e.target.checked) next.push(d.syndrome_id);
            if (!next.length) { e.target.checked = true; return; }
            next.sort(function (a, b) { return diff.findIndex(function (x) { return x.syndrome_id === a; }) - diff.findIndex(function (x) { return x.syndrome_id === b; }); });
            userPicked = true;
            build(next);
            draw();
          } }),
          d.rank + ". " + d.names.en + " ", el("span", { class: "zh", text: d.names.zh })
        ]);
      }))
    ]));

    // 2. principle
    var prin = el("div", { class: "panel" }, [el("h3", { text: "עקרון טיפול" })]);
    if (sugg.methods.length) {
      prin.appendChild(el("ul", { class: "ev" }, sugg.methods.map(function (m) {
        var on = plan.methods.indexOf(m.i) !== -1;
        return el("li", {}, [
          el("label", {}, [el("input", { type: "checkbox", checked: on, onchange: function (e) {
            plan.methods = plan.methods.filter(function (x) { return x !== m.i; });
            if (e.target.checked) plan.methods.push(m.i);
            touch();
          } }), " ", el("b", { text: m.method.zh }), " ", el("span", { class: "en", text: m.method.en })]),
          " ", el("span", { class: "id", text: "WHO 2022 #" + m.method.no + " · התאמה " + m.s }),
          " ", decisionButtons("method", "WHO" + m.method.no),
          el("div", { class: "src", text: m.method.def })
        ]);
      })));
    } else {
      prin.appendChild(el("p", { class: "empty", text: "לא נמצאה במונחי WHO 2022 שיטת טיפול שמוגדרת במפורש לתבנית הזו. נסחו את העיקרון בשדה למטה." }));
    }
    prin.appendChild(el("label", { class: "field" }, ["עקרון הטיפול במילים שלך",
      el("textarea", { value: plan.principle_he, placeholder: "למשל: להרגיע את הכבד ולהוריד את היאנג", oninput: function (e) { plan.principle_he = e.target.value; plan.dirty = true; } })]));
    body.appendChild(prin);

    // 3. safety (live)
    body.appendChild(safetyPanel(issues));

    // 4. acupuncture
    body.appendChild(pointsPanel(issues));

    // 5. herbs
    body.appendChild(herbsPanel(issues));

    // 6. shiatsu
    body.appendChild(shiatsuPanel(issues));

    // 7. follow-up and save
    body.appendChild(followupPanel(issues));
  }

  function sevOf(issues, id) {
    var s = issues.filter(function (i) { return i.ids.indexOf(id) !== -1 && i.sev !== "info"; }).map(function (i) { return i.sev; });
    return s.indexOf("red") !== -1 ? "red" : s.indexOf("amber") !== -1 ? "amber" : "";
  }

  function safetyPanel(issues) {
    var p = el("div", { class: "panel", id: "tx-safety" }, [el("h3", { text: "בדיקת בטיחות" })]);
    var shown = issues.filter(function (i) { return i.sev !== "info" || !/^DOSE|^ACUATLAS/.test(i.rule); });
    var cautions = issues.filter(function (i) { return /^ACUATLAS/.test(i.rule); });
    var doses = issues.filter(function (i) { return /^DOSE/.test(i.rule); });
    var preg = ctx.state.patient.pregnancy;
    p.appendChild(el("p", { class: "hint", text: "נבדק מול " + tx.safety.length + " כללי הבטיחות שבמאגר (היריון, 十八反/十九畏, צמחים רעילים, נקודות אסורות לדיקור או למוקסה), מול רשימת התרופות ומול אזהרות הדיקור של AcuAtlas." +
      (preg === "yes" ? " המטופלת דיווחה על היריון אפשרי." : preg === "unknown" ? " סטטוס ההיריון לא אושר, ולכן כל פריט שאסור בהיריון מסומן." : "") }));
    if (!shown.length) p.appendChild(el("div", { class: "flag info", text: "לא נמצאה התנגשות עם כללי הבטיחות שבמאגר." }));
    shown.forEach(function (i) {
      p.appendChild(el("div", { class: "flag " + i.sev, title: i.rule }, [i.he,
        i.note ? el("span", { class: "en", text: " · " + i.note }) : null,
        i.src ? el("span", { class: "id", text: " · " + i.src }) : null]));
    });
    if (doses.length) p.appendChild(el("div", { class: "flag info", text: "לא נקבע מינון בגרם ל-" + doses.length + " צמחים. המינון הוא החלטה של המטפל, והמערכת לא מציעה אותו." }));
    if (cautions.length) {
      p.appendChild(el("details", {}, [el("summary", { text: "אזהרות דיקור לנקודות שנבחרו (" + cautions.length + ")" })].concat(
        cautions.map(function (i) { return el("div", { class: "src" }, [el("b", { text: i.ids[0] + ": " }), i.note]); }))));
    }
    return p;
  }

  function pointRow(s, list, kind, issues) {
    var pt = tx.points[s.id];
    var item = list.filter(function (x) { return x.id === s.id; })[0];
    var sev = sevOf(issues, s.id);
    var from = s.from || [];
    var actions = [].concat.apply([], from.map(function (f) { return f.actions; }));
    var finds = [].concat.apply([], from.map(function (f) { return f.findings; }));
    var why = [];
    if (actions.length) why.push(el("div", {}, ["פעולה (AcuAtlas): ", el("span", { class: "en", text: actions.filter(function (x, i) { return actions.indexOf(x) === i; }).join("; ") })]));
    if (finds.length) why.push(el("div", {}, ["ממצאי התבנית בהתוויות: " + findingNames(finds.filter(function (x, i) { return finds.indexOf(x) === i; }))]));
    if (s.patient && s.patient.length) {
      var quotes = s.patient.map(function (h) { return (h.src === "WS-ZJDC" ? "针灸大成 “" : "AcuAtlas “") + h.ev.replace(/^[;\s]+/, "") + "”"; })
        .filter(function (q, i, a) { return a.indexOf(q) === i; });
      why.push(el("div", {}, [el("b", { text: "ממצאי המטופל בהתוויות: " }), findingNames(s.patient)]));
      why.push(el("div", { class: "quote" }, [quotes.join(" · ")]));
    }
    var row = el("li", { class: "txrow" + (item ? " on" : "") + (sev ? " risk-" + sev : "") });
    row.appendChild(el("div", { class: "txhead" }, [
      el("label", { class: "txname" }, [
        el("input", { type: "checkbox", checked: !!item, onchange: function (e) {
          if (e.target.checked) list.push(kind === "points" ? { id: s.id, technique: "even", moxa: false, note: "", origin: s.from ? "suggested" : "added" } : { id: s.id, note: "", origin: s.from ? "suggested" : "added" });
          else list.splice(list.indexOf(item), 1);
          touch();
        } }),
        " ", el("b", { text: s.id }), " ", pt.zh + " " + pt.py, " ", el("span", { class: "en", text: pt.en })
      ]),
      el("span", { class: "row" }, [
        s.score !== undefined ? el("span", { class: "id", text: "ציון " + s.score.toFixed(1) }) : el("span", { class: "id", text: "נוספה ידנית" }),
        s.from ? decisionButtons(kind === "points" ? "point" : "shiatsu", s.id) : null])
    ]));
    if (item && kind === "points") {
      row.appendChild(el("div", { class: "row" }, [
        el("select", { "aria-label": "טכניקה", onchange: function (e) { item.technique = e.target.value; touch(); } },
          Object.keys(TECH).map(function (k) { return el("option", { value: k, text: TECH[k], selected: item.technique === k }); })),
        el("label", { class: "opt" }, [el("input", { type: "checkbox", checked: item.moxa, onchange: function (e) { item.moxa = e.target.checked; touch(); } }), "מוקסה"]),
        el("input", { type: "text", class: "note", placeholder: "הערה (צד, עומק, זמן השארה)", value: item.note, oninput: function (e) { item.note = e.target.value; plan.dirty = true; } })
      ]));
    } else if (item) {
      row.appendChild(el("div", { class: "row" }, [
        el("input", { type: "text", class: "note", placeholder: "הערה (לחץ, משך, תרגול בבית)", value: item.note, oninput: function (e) { item.note = e.target.value; plan.dirty = true; } })
      ]));
    }
    if (!item) {
      if (why.length) row.appendChild(el("details", {}, [el("summary", { text: "למה הוצעה" }), el("div", { class: "why" }, why)]));
      return row;
    }
    if (why.length) row.appendChild(el("div", { class: "why" }, why));
    row.appendChild(el("details", {}, [el("summary", { text: "מיקום והתוויות" }),
      el("div", { class: "src" }, [pt.loc]), el("div", { class: "src" }, [pt.ind]),
      pt.needle && kind === "points" ? el("div", { class: "src" }, [pt.needle]) : null,
      el("div", { class: "id", text: pt.src + (pt.zjdc ? " · " + pt.zjdc : "") })]));
    return row;
  }

  function addBox(placeholder, options, onAdd) {
    var listId = "dl-" + placeholder.length + "-" + options.length;
    var inp = el("input", { type: "text", list: listId, placeholder: placeholder, class: "note" });
    var dl = el("datalist", { id: listId }, options.map(function (o) { return el("option", { value: o.value, text: o.label }); }));
    function go() {
      var v = inp.value.trim().split(" ")[0].toUpperCase();
      var hit = options.filter(function (o) { return o.value.toUpperCase() === v || o.label.indexOf(inp.value.trim()) !== -1 && inp.value.trim(); })[0];
      if (hit) { onAdd(hit.value); } else { inp.setCustomValidity("לא נמצא במאגר"); inp.reportValidity(); }
    }
    inp.addEventListener("input", function () { inp.setCustomValidity(""); });
    inp.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); go(); } });
    return el("div", { class: "row" }, [inp, dl, el("button", { class: "btn ghost", type: "button", text: "הוספה", onclick: go })]);
  }

  var pointOptions = null, herbOptions = null;
  function pointsList() {
    if (!pointOptions) pointOptions = Object.keys(tx.points).map(function (id) { return { value: id, label: id + " " + tx.points[id].zh + " " + tx.points[id].py }; });
    return pointOptions;
  }
  function herbsList() {
    if (!herbOptions) herbOptions = Object.keys(tx.herbs).map(function (id) { return { value: id, label: tx.herbs[id].zh + " " + tx.herbs[id].py }; });
    return herbOptions;
  }

  // Chosen points first, with their reasons; the other suggestions in a closed list below.
  function splitList(panel, suggestions, list, kind, issues) {
    var chosen = el("ul", { class: "txlist" });
    var rest = el("ul", { class: "txlist" });
    var bySugg = {};
    suggestions.forEach(function (s) { bySugg[s.id] = s; });
    list.forEach(function (x) { chosen.appendChild(pointRow(bySugg[x.id] || { id: x.id }, list, kind, issues)); });
    var others = suggestions.filter(function (s) { return !list.some(function (x) { return x.id === s.id; }); });
    others.forEach(function (s) { rest.appendChild(pointRow(s, list, kind, issues)); });
    panel.appendChild(chosen);
    if (others.length) panel.appendChild(el("details", {}, [el("summary", { text: "הצעות נוספות (" + others.length + ")" }), rest]));
  }

  function pointsPanel(issues) {
    var p = el("div", { class: "panel" }, [el("h3", { text: "נקודות דיקור (" + plan.points.length + " נבחרו)" }),
      el("p", { class: "hint", text: "הצעות לפי פעולות הנקודה ב-AcuAtlas שמטפלות באותו איבר ובאותה הפרעה, ולפי ההתוויות ב-AcuAtlas וב-针灸大成 שתואמות את ממצאי התבנית והמטופל." })]);
    if (!plan.sugg.points.length) p.appendChild(el("p", { class: "empty", text: "אין הצעות נקודות לתבנית הזו במאגר." }));
    splitList(p, plan.sugg.points, plan.points, "points", issues);
    p.appendChild(addBox("הוספת נקודה לפי קוד (למשל LR3)", pointsList(), function (id) {
      if (!plan.points.some(function (x) { return x.id === id; })) plan.points.push({ id: id, technique: "even", moxa: false, note: "", origin: "added" });
      touch();
    }));
    return p;
  }

  function shiatsuPanel(issues) {
    var p = el("div", { class: "panel" }, [el("h3", { text: "נקודות לשיאצו (" + plan.shiatsu.length + " נבחרו)" }),
      el("p", { class: "hint", text: "אותן הצעות כמו בדיקור, בלי נקודות סביב העין, הפטמה והטבור. כללי ההיריון חלים גם על לחיצה." })]);
    splitList(p, plan.sugg.points.filter(function (s) { return T.shiatsuAllowed(s.id); }), plan.shiatsu, "shiatsu", issues);
    p.appendChild(addBox("הוספת נקודה לשיאצו", pointsList(), function (id) {
      if (!plan.shiatsu.some(function (x) { return x.id === id; })) plan.shiatsu.push({ id: id, note: "", origin: "added" });
      touch();
    }));
    return p;
  }

  function herbsPanel(issues) {
    var p = el("div", { class: "panel" }, [el("h3", { text: "מרשם צמחים" }),
      el("p", { class: "hint", text: "מרשמי הבסיס הם מ-傷寒論 ו-金匱要略 בלבד (152 מרשמים במאגר), ולכן לתבניות של איברים פנימיים ההתאמה לעיתים חלשה. המינון המקורי מוצג לעיון; המינון בגרם נקבע על ידך." })]);
    var fr = el("div", { class: "checks" });
    function formulaOption(id, s) {
      var f = tx.formulas[id];
      return el("label", { class: "opt" }, [
        el("input", { type: "radio", name: "tx-formula", checked: plan.formula_id === id, onchange: function () { T.setFormula(plan, id); touch(); } }),
        f.zh + " " + f.py, s ? el("span", { class: "id", text: " · " + s.score.toFixed(1) }) : null
      ]);
    }
    plan.sugg.formulas.forEach(function (s) { fr.appendChild(formulaOption(s.id, s)); });
    if (plan.formula_id && !plan.sugg.formulas.some(function (s) { return s.id === plan.formula_id; })) fr.appendChild(formulaOption(plan.formula_id));
    fr.appendChild(el("label", { class: "opt" }, [el("input", { type: "radio", name: "tx-formula", checked: !plan.formula_id, onchange: function () { T.setFormula(plan, null); touch(); } }), "בלי מרשם בסיס"]));
    p.appendChild(fr);
    if (!plan.sugg.formulas.length) p.appendChild(el("p", { class: "empty", text: "לא נמצא במאגר מרשם קלאסי שמתאים לתבנית הזו. אפשר לבנות מרשם מהצמחים המוצעים למטה." }));

    var sel = plan.sugg.formulas.filter(function (s) { return s.id === plan.formula_id; })[0];
    if (plan.formula_id) {
      var f = tx.formulas[plan.formula_id];
      var why = [];
      if (sel) {
        var carrying = [].concat.apply([], sel.from.map(function (x) { return x.herbs; }));
        var finds = [].concat.apply([], sel.from.map(function (x) { return x.findings; }));
        if (carrying.length) why.push(el("div", {}, ["צמחים במרשם שפעולתם תואמת את עקרון הטיפול: " + carrying.filter(function (x, i) { return carrying.indexOf(x) === i; }).map(T.label).join(", ")]));
        if (finds.length) why.push(el("div", {}, ["ממצאי התבנית בסעיפים: " + findingNames(finds.filter(function (x, i) { return finds.indexOf(x) === i; }))]));
        if (sel.patient && sel.patient.length) why.push(el("div", {}, ["ממצאי המטופל בסעיפים: " + findingNames(sel.patient) + " ", el("span", { class: "id", text: sel.patient.map(function (h) { return h.c + " “" + h.ev + "”"; }).join(" · ") })]));
      }
      p.appendChild(el("div", { class: "why" }, why.concat([el("div", { class: "id", text: f.src + (f.ind_src ? " · " + f.ind_src : "") }), sel ? decisionButtons("formula", plan.formula_id) : null])));
    }

    var table = el("table", { class: "herbs" }, [el("thead", {}, [el("tr", {}, ["צמח", "מינון מקורי", "גרם", "הערה", ""].map(function (h) { return el("th", { text: h }); }))])]);
    var tb = el("tbody");
    plan.herbs.forEach(function (h) {
      var herb = tx.herbs[h.id] || { zh: h.id, py: "" };
      var sev = sevOf(issues, h.id);
      tb.appendChild(el("tr", { class: sev ? "risk-" + sev : "" }, [
        el("td", {}, [el("b", { text: herb.zh }), " " + herb.py]),
        el("td", { text: h.dose_original || "" }),
        el("td", {}, [el("input", { type: "number", min: "0", step: "0.5", inputmode: "decimal", class: "gram", "aria-label": "גרם " + herb.zh, value: h.dose_g,
          oninput: function (e) { h.dose_g = e.target.value === "" ? "" : Number(e.target.value); plan.dirty = true; },
          onchange: function () { touch(); } })]),
        el("td", {}, [el("input", { type: "text", class: "note", value: h.note, oninput: function (e) { h.note = e.target.value; plan.dirty = true; } })]),
        el("td", {}, [el("button", { class: "mini", type: "button", text: "הסרה", onclick: function () { plan.herbs.splice(plan.herbs.indexOf(h), 1); touch(); } })])
      ]));
    });
    table.appendChild(tb);
    if (plan.herbs.length) p.appendChild(el("div", { class: "scroll" }, [table]));

    if (plan.sugg.herbs.length) {
      var det = el("details", { open: "" }, [el("summary", { text: "צמחים בודדים שפעולתם ב-本草備要 תואמת את עקרון הטיפול (" + plan.sugg.herbs.length + ")" })]);
      det.appendChild(el("ul", { class: "ev" }, plan.sugg.herbs.map(function (s) {
        var herb = tx.herbs[s.id];
        var acts = [].concat.apply([], s.from.map(function (x) { return x.actions; }));
        var inPlan = plan.herbs.some(function (h) { return h.id === s.id; });
        return el("li", {}, [el("b", { text: herb.zh }), " " + herb.py + " ", el("span", { class: "zh", text: "“" + acts.join("，") + "”" }),
          " ", el("span", { class: "id", text: herb.src }), " ",
          inPlan ? el("span", { class: "id", text: "במרשם" }) : el("button", { class: "mini", type: "button", text: "הוספה למרשם", onclick: function () {
            plan.herbs.push({ id: s.id, dose_original: "", dose_g: "", note: "", origin: "added" });
            touch();
          } }),
          " ", decisionButtons("herb", s.id)]);
      })));
      p.appendChild(det);
    }
    p.appendChild(addBox("הוספת צמח (שם סיני או פיניין)", herbsList(), function (id) {
      if (!plan.herbs.some(function (h) { return h.id === id; })) plan.herbs.push({ id: id, dose_original: "", dose_g: "", note: "", origin: "added" });
      touch();
    }));
    return p;
  }

  function exportPlan(issues) {
    var rep = ctx.report;
    return {
      schema_version: "treatment_plan.v1",
      status: "draft",
      created_at: new Date().toISOString(),
      kb_version: tx.kb_version,
      patient: rep.patient,
      patterns: plan.patterns.map(function (sid) { return { syndrome_id: sid, name: patternName(sid) }; }),
      principle: {
        methods: plan.methods.map(function (i) { var m = tx.methods[i]; return { who_no: m.no, zh: m.zh, en: m.en, source: "WHO-ISTTCM-2022 #" + m.no }; }),
        text_he: plan.principle_he
      },
      acupuncture: plan.points.map(function (p) { return { point_id: p.id, technique: p.technique, moxa: p.moxa, note_he: p.note, origin: p.origin }; }),
      herbal: {
        base_formula: plan.formula_id ? { formula_id: plan.formula_id, zh: tx.formulas[plan.formula_id].zh, source: tx.formulas[plan.formula_id].src } : null,
        herbs: plan.herbs.map(function (h) { return { herb_id: h.id, zh: (tx.herbs[h.id] || {}).zh, dose_original: h.dose_original || null, dose_g: h.dose_g === "" ? null : h.dose_g, note_he: h.note, origin: h.origin }; })
      },
      shiatsu: plan.shiatsu.map(function (p) { return { point_id: p.id, note_he: p.note, origin: p.origin }; }),
      followup: { interval: plan.followup.interval, sessions: plan.followup.sessions === "" ? null : Number(plan.followup.sessions), notes_he: plan.followup.notes_he },
      safety_check: issues.map(function (i) { return { severity: i.sev, rule_id: i.rule, entity_ids: i.ids, message_he: i.he, source: i.src || null }; }),
      link_decisions: Object.keys(plan.decisions).map(function (k) {
        var parts = k.split("|");
        return { syndrome_id: parts[0], kind: parts[1], target_id: parts[2], decision: plan.decisions[k] };
      }),
      clinician_note_he: plan.clinician_note
    };
  }

  function planText(doc) {
    var lines = ["תכנית טיפול (טיוטה) · " + doc.created_at.slice(0, 10)];
    lines.push("תבניות: " + doc.patterns.map(function (p) { return p.name; }).join("; "));
    if (doc.principle.methods.length || doc.principle.text_he) lines.push("עקרון טיפול: " + doc.principle.methods.map(function (m) { return m.zh + " (" + m.en + ")"; }).join("; ") + (doc.principle.text_he ? " · " + doc.principle.text_he : ""));
    if (doc.acupuncture.length) lines.push("דיקור: " + doc.acupuncture.map(function (p) { return p.point_id + " " + TECH[p.technique] + (p.moxa ? " + מוקסה" : "") + (p.note_he ? " (" + p.note_he + ")" : ""); }).join(", "));
    if (doc.herbal.herbs.length) lines.push("צמחים" + (doc.herbal.base_formula ? " (בסיס " + doc.herbal.base_formula.zh + ")" : "") + ": " + doc.herbal.herbs.map(function (h) { return h.zh + " " + (h.dose_g === null ? "[מינון לא נקבע]" : h.dose_g + " גרם"); }).join(", "));
    if (doc.shiatsu.length) lines.push("שיאצו: " + doc.shiatsu.map(function (p) { return p.point_id + (p.note_he ? " (" + p.note_he + ")" : ""); }).join(", "));
    lines.push("מעקב: " + INTERVAL[doc.followup.interval] + (doc.followup.sessions ? " · " + doc.followup.sessions + " טיפולים" : "") + (doc.followup.notes_he ? " · " + doc.followup.notes_he : ""));
    var risks = doc.safety_check.filter(function (s) { return s.severity !== "info"; });
    if (risks.length) lines.push("בטיחות: " + risks.map(function (s) { return s.message_he; }).join(" | "));
    if (doc.clinician_note_he) lines.push("הערה: " + doc.clinician_note_he);
    return lines.join("\n");
  }

  function loadSaved() {
    try { return JSON.parse(root.localStorage.getItem(STORE) || "[]"); } catch (e) { return []; }
  }

  function followupPanel(issues) {
    var p = el("div", { class: "panel" }, [el("h3", { text: "מעקב ושמירה" })]);
    p.appendChild(el("div", { class: "row" }, [
      el("label", { class: "row" }, ["הטיפול הבא: ", el("select", { onchange: function (e) { plan.followup.interval = e.target.value; touch(); } },
        Object.keys(INTERVAL).map(function (k) { return el("option", { value: k, text: INTERVAL[k], selected: plan.followup.interval === k }); }))]),
      el("label", { class: "row" }, ["מספר טיפולים מתוכנן: ", el("input", { type: "number", min: "1", max: "50", style: "width:5em", value: plan.followup.sessions,
        oninput: function (e) { plan.followup.sessions = e.target.value; plan.dirty = true; } })])
    ]));
    p.appendChild(el("label", { class: "field" }, ["מה לבדוק בטיפול הבא",
      el("textarea", { value: plan.followup.notes_he, placeholder: "למשל: שינה, תדירות כאבי הראש, לשון ודופק", oninput: function (e) { plan.followup.notes_he = e.target.value; plan.dirty = true; } })]));
    p.appendChild(el("label", { class: "field" }, ["הערה כללית",
      el("textarea", { value: plan.clinician_note, oninput: function (e) { plan.clinician_note = e.target.value; plan.dirty = true; } })]));

    var reds = issues.filter(function (i) { return i.sev === "red"; });
    var status = el("span", { class: "progress", role: "status" });
    var out = el("pre", { class: "json", hidden: true });
    function doc() { return exportPlan(T.checkSafety(plan, ctx.state.patient, constraints())); }
    var buttons = el("div", { class: "answers" }, [
      el("button", { class: "btn", type: "button", text: "שמירת התכנית", onclick: function () {
        var d = doc();
        if (reds.length && !root.confirm("יש " + reds.length + " התראות בטיחות אדומות. לשמור בכל זאת?")) return;
        var saved = loadSaved();
        saved.unshift(d);
        try { root.localStorage.setItem(STORE, JSON.stringify(saved.slice(0, 50))); status.textContent = "נשמר בדפדפן הזה (" + Math.min(saved.length, 50) + " תכניות). להעברה למערכת אחרת הורידו JSON."; }
        catch (e) { status.textContent = "הדפדפן לא מאפשר שמירה מקומית. הורידו את התכנית כ-JSON."; }
      } }),
      el("button", { class: "btn ghost", type: "button", text: "הורדת JSON", onclick: function () {
        var d = doc();
        var blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
        var a = el("a", { href: URL.createObjectURL(blob), download: "treatment_plan_" + d.created_at.slice(0, 10) + ".json" });
        document.body.appendChild(a); a.click(); a.remove();
      } }),
      el("button", { class: "btn ghost", type: "button", text: "העתקת סיכום", onclick: function () {
        var text = planText(doc());
        out.hidden = false; out.textContent = text;
        try { root.navigator.clipboard.writeText(text).then(function () { status.textContent = "הסיכום הועתק."; }, function () { status.textContent = "סמנו והעתיקו מהתיבה."; }); }
        catch (e) { status.textContent = "סמנו והעתיקו מהתיבה."; }
      } })
    ]);
    p.appendChild(buttons);
    p.appendChild(status);
    p.appendChild(out);
    var saved = loadSaved();
    if (saved.length) {
      p.appendChild(el("details", {}, [el("summary", { text: "תכניות שמורות בדפדפן הזה (" + saved.length + ")" }),
        el("ul", { class: "ev" }, saved.map(function (d) {
          return el("li", { text: d.created_at.slice(0, 16).replace("T", " ") + " · " + d.patterns.map(function (x) { return x.name; }).join("; ") });
        }))]));
    }
    var decided = Object.keys(plan.decisions).length;
    if (decided) p.appendChild(el("p", { class: "hint", text: decided + " החלטות על קישורים (אישור או דחייה) נכללות בקובץ ה-JSON, כדי שאפשר יהיה להכניס אותן למאגר." }));
    return p;
  }

  root.TCMTreatmentUI = { render: render, getPlan: function () { return plan; }, reset: function () { plan = null; userPicked = false; } };
})(typeof window !== "undefined" ? window : this);
