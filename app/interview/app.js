// UI for the interview prototype: a Hebrew chat for the patient and a worksheet for the clinician.
(function () {
  "use strict";
  var kb = window.TCM_KB;
  var I = window.TCMI18n;
  kb.syndromes.forEach(function (s) { if (!s.he) s.he = I.he(s.zh) || null; });   // draft Hebrew names
  var E = window.TCMEngine.createEngine(kb);
  var state;
  var current = null;     // the question waiting for an answer
  var step = "intake";
  var chat = document.getElementById("chat");
  var clin = document.getElementById("view-clin");

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function say(text, cls, meta) {
    var m = el("div", { class: "msg " + (cls || "sys"), text: text });
    if (meta) m.appendChild(el("span", { class: "meta", text: meta }));
    chat.appendChild(m);
    m.scrollIntoView({ block: "nearest" });
    return m;
  }
  function panel(children) {
    var p = el("div", { class: "panel" }, children);
    chat.appendChild(p);
    p.scrollIntoView({ block: "nearest" });
    return p;
  }
  function showUnderstood(findings) {
    if (!findings.length) return;
    var box = el("div", { class: "understood" });
    findings.forEach(function (f) {
      box.appendChild(el("span", { class: "chip" + (f.value ? "" : " neg"), text: E.featById[f.feature].label_he }));
    });
    chat.appendChild(box);
  }
  function halt() {
    say(kb.safety.emergency_template_he, "alert");
    step = "halted";
    renderClinician();
  }

  // ---- steps ----
  function start() {
    if (window.TCMTreatmentUI) window.TCMTreatmentUI.reset();
    chat.textContent = "";
    state = E.newState({});
    current = null;
    objective = { tongue: null, pulse: null };
    scenario = null;
    step = "intake";
    say("שלום, אני עוזר/ת האינטייק של הקליניקה. אשאל כמה שאלות לפני הפגישה, והמטפל/ת יעבור/תעבור על התשובות. אני לא נותן/ת אבחנה או טיפול.");
    var age = el("input", { type: "number", id: "age", min: "1", max: "120", inputmode: "numeric", style: "width:6em" });
    var sexRow = el("div", { class: "row" }, [
      el("span", { text: "מין:" }),
      el("label", { class: "opt" }, [el("input", { type: "radio", name: "sex", value: "F", id: "sex-f" }), "אישה"]),
      el("label", { class: "opt" }, [el("input", { type: "radio", name: "sex", value: "M", id: "sex-m" }), "גבר"])
    ]);
    var preg = el("div", { class: "row", hidden: "" }, [
      el("span", { text: "האם יש אפשרות שאת בהיריון?" }),
      el("label", { class: "opt" }, [el("input", { type: "radio", name: "preg", value: "yes", id: "preg-y" }), "כן"]),
      el("label", { class: "opt" }, [el("input", { type: "radio", name: "preg", value: "no", id: "preg-n" }), "לא"]),
      el("label", { class: "opt" }, [el("input", { type: "radio", name: "preg", value: "unknown", id: "preg-u" }), "לא בטוחה"])
    ]);
    function syncPreg() {
      var f = document.getElementById("sex-f").checked;
      var a = Number(age.value);
      preg.hidden = !(f && (!a || (a >= 12 && a <= 55)));
    }
    sexRow.addEventListener("change", syncPreg);
    age.addEventListener("input", syncPreg);
    var go = el("button", { class: "btn", type: "button", text: "המשך" });
    var p = panel([el("label", { class: "row" }, [el("span", { text: "גיל:" }), age]), sexRow, preg, go]);
    go.addEventListener("click", function () {
      var sex = (document.querySelector("input[name=sex]:checked") || {}).value;
      var pr = (document.querySelector("input[name=preg]:checked") || {}).value;
      state.patient = { age: Number(age.value) || null, sex: sex || null,
                        pregnancy: preg.hidden ? "na" : (pr || "unknown") };
      p.remove();
      say([state.patient.age ? "גיל " + state.patient.age : "", sex === "F" ? "אישה" : sex === "M" ? "גבר" : "",
           pr === "yes" ? "ייתכן היריון" : pr === "no" ? "לא בהיריון" : ""].filter(Boolean).join(", ") || "דילגתי", "pt");
      redFlags();
    });
  }

  function redFlags() {
    step = "redflags";
    say("לפני שנתחיל: האם אחד מהדברים האלה קורה לך עכשיו?");
    var boxes = kb.safety.red_flag_questions.map(function (q) {
      return el("label", { class: "opt" }, [el("input", { type: "checkbox", value: q.id, id: "rf-" + q.id }), q.q_he]);
    });
    var none = el("button", { class: "btn no", type: "button", text: "אף אחד מאלה" });
    var yes = el("button", { class: "btn", type: "button", text: "סימנתי" });
    var p = panel([el("div", { style: "display:grid;gap:6px" }, boxes), el("div", { class: "answers" }, [none, yes])]);
    function done(useChecks) {
      var checked = useChecks ? Array.prototype.slice.call(p.querySelectorAll("input:checked")) : [];
      p.remove();
      if (!checked.length) { say("אף אחד מאלה", "pt"); return meds(); }
      checked.forEach(function (c) { E.redFlagAnswer(state, c.value, true); say(c.parentNode.textContent, "pt"); });
      halt();
    }
    none.addEventListener("click", function () { done(false); });
    yes.addEventListener("click", function () { done(true); });
  }

  function composer(placeholder, onSend, allowEmpty) {
    var t = el("textarea", { id: "composer-" + step, placeholder: placeholder });
    var send = el("button", { class: "btn", type: "button", text: "שליחה" });
    var p = panel([t, el("div", { class: "answers" }, [send])]);
    function go() {
      var v = t.value.trim();
      if (!v && !allowEmpty) { t.focus(); return; }
      p.remove();
      onSend(v);
    }
    send.addEventListener("click", go);
    t.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } });
    t.focus();
  }

  function meds() {
    step = "meds";
    say("אילו תרופות, ויטמינים או תוספים את/ה לוקח/ת כרגע? אם יש מחלות רקע או אלרגיות, אפשר לכתוב גם אותן.");
    composer("למשל: אלטרוקסין, ויטמין D. אם אין, כתוב/כתבי 'אין'", function (v) {
      say(v || "אין", "pt");
      E.ingestMedications(state, v);
      complaint();
    }, true);
  }

  function complaint() {
    step = "complaint";
    say("ספר/י לי במילים שלך מה מביא אותך לטיפול. מה מרגישים, ממתי, ומה מחמיר או מקל?");
    composer("כתוב/כתבי בחופשיות", function (v) {
      say(v, "pt");
      var r = E.ingestText(state, v, "chief_complaint");
      if (r.halted) return halt();
      showUnderstood(r.findings);
      if (r.findings.length) say("תודה, רשמתי. עכשיו כמה שאלות קצרות. אפשר לענות בכפתורים, או לכתוב בחופשיות.");
      else say("תודה. עכשיו כמה שאלות קצרות. אפשר לענות בכפתורים, או לכתוב בחופשיות.");
      ask();
    });
  }

  function ask() {
    step = "questions";
    current = E.nextQuestion(state);
    if (!current) return finish();
    var f = current.feature;
    var n = state.asked.length + 1;
    var msg = say(f.q_he, "sys", (current.phase === "screening" ? "סקירה כללית" : "שאלת הבחנה") + " · " + kb.groups[f.group] + " · שאלה " + n);
    var p;
    function answer(v, label) {
      p.remove();
      say(label, "pt");
      E.answerQuestion(state, current, v);
      ask();
    }
    var t = el("textarea", { id: "free-" + n, placeholder: "או כתוב/כתבי תשובה במילים שלך", style: "min-height:44px" });
    var sendFree = el("button", { class: "btn ghost", type: "button", text: "שליחה" });
    p = panel([
      el("div", { class: "answers" }, [
        el("button", { class: "btn", type: "button", text: "כן", onclick: function () { answer(true, "כן"); } }),
        el("button", { class: "btn no", type: "button", text: "לא", onclick: function () { answer(false, "לא"); } }),
        el("button", { class: "btn no", type: "button", text: "לא בטוח/ה", onclick: function () { answer(null, "לא בטוח/ה"); } }),
        el("button", { class: "btn ghost", type: "button", text: "סיום הראיון", onclick: function () { p.remove(); finish(); } })
      ]),
      el("div", { class: "row" }, [t, sendFree]),
      el("span", { class: "progress", text: "עד " + E.MAX_ADAPTIVE + " שאלות הבחנה אחרי הסקירה הכללית" })
    ]);
    t.style.flex = "1";
    sendFree.addEventListener("click", function () {
      var v = t.value.trim();
      if (!v) return;
      p.remove();
      say(v, "pt");
      var r = E.ingestText(state, v, f.id);
      if (r.halted) return halt();
      showUnderstood(r.findings);
      var own = r.findings.filter(function (x) { return x.feature === f.id; })[0];
      if (own || /^(כן|נכון|בטח|כמובן|יש)([\s,.!]|$)/.test(v)) {
        E.answerQuestion(state, current, own ? own.value : true);
      } else if (/^(לא|אין|ממש לא)([\s,.!]|$)/.test(v)) {
        E.answerQuestion(state, current, false);
      } else {
        state.asked.push(f.id);
        if (current.phase === "adaptive") state.adaptiveAsked += 1;
        E.setAnswer(state, f.id, null, "question", v);
      }
      ask();
    });
    void msg;
  }

  function finish() {
    step = "done";
    current = null;
    say("תודה רבה! המטפל/ת יעבור/תעבור על התשובות לפני הפגישה. אם יש עוד משהו שחשוב לך שיידע/תדע, אפשר לכתוב אותו כאן.");
    composer("לא חובה", function (v) {
      if (v) {
        say(v, "pt");
        var r = E.ingestText(state, v, "closing");
        if (r.halted) return halt();
        showUnderstood(r.findings);
      }
      say("הראיון הסתיים. הסיכום מחכה למטפל/ת בלשונית 'סיכום למטפל'.");
      renderClinician();
    }, true);
    renderClinician();
  }

  // ---- clinician view ----
  var objective = { tongue: null, pulse: null };

  function objectivePanel(kind, title) {
    var feats = E.features.filter(function (f) { return f.kind === kind; });
    var observed = el("label", { class: "opt" }, [el("input", { type: "checkbox", id: kind + "-observed" }), "נבדק"]);
    var obsInput = observed.querySelector("input");
    obsInput.checked = objective[kind] !== null;
    var checks = el("div", { class: "checks" }, feats.map(function (f) {
      var inp = el("input", { type: "checkbox", value: f.id, id: "obj-" + f.id });
      inp.checked = !!(objective[kind] && objective[kind].indexOf(f.id) !== -1);
      return el("label", { class: "opt" }, [inp, f.label_he]);
    }));
    function sync() {
      if (!obsInput.checked) objective[kind] = null;
      else objective[kind] = Array.prototype.slice.call(checks.querySelectorAll("input:checked")).map(function (i) { return i.value; });
      renderClinician();
    }
    checks.addEventListener("change", function () { obsInput.checked = true; sync(); });
    obsInput.addEventListener("change", sync);
    return el("div", { class: "panel" }, [el("div", { class: "row" }, [el("h3", { text: title }), observed]), checks]);
  }

  // Clinician answers inside a hypothesis: a symptom becomes a "clinician" answer; a tongue or pulse
  // item goes through the tongue/pulse panel's state, so both places stay in step.
  function setFromCard(fid, value) {
    var f = E.featById[fid];
    if (f.kind === "tongue" || f.kind === "pulse") {
      var list = (objective[f.kind] || []).filter(function (x) { return x !== fid; });
      if (value === true) list.push(fid);
      objective[f.kind] = value === null && !list.length ? null : list;
    } else if (value === null) {
      delete state.answers[fid];
    } else {
      E.setAnswer(state, fid, value, "clinician");
    }
    renderClinician();
  }

  function answerButtons(fid, current) {
    var f = E.featById[fid];
    var objectiveKind = f.kind === "tongue" || f.kind === "pulse";
    var a = state.answers[fid];
    var buttons = [];
    if (current !== true) buttons.push(el("button", { class: "mini", type: "button", text: "כן", onclick: function () { setFromCard(fid, true); } }));
    if (current !== false) buttons.push(el("button", { class: "mini", type: "button", text: "לא", onclick: function () { setFromCard(fid, false); } }));
    if (current !== undefined && (objectiveKind || (a && a.source === "clinician"))) {
      buttons.push(el("button", { class: "mini ghost", type: "button", text: "ביטול", title: "החזרה ללא נבדק",
                                  onclick: function () { setFromCard(fid, null); } }));
    }
    return el("span", { class: "mini-row" }, buttons);
  }

  function evList(items, render, cls) {
    var ul = el("ul", { class: "ev" + (cls ? " " + cls : "") });
    items.forEach(function (x) { ul.appendChild(render(x)); });
    return ul;
  }

  var FLAG_HE = {
    SAFETY_CATEGORY_A: "סימן אזהרה דחוף: ",
    SAFETY_CATEGORY_C: "שיקול בטיחות לטיפול: ",
    SAFETY_CATEGORY_D: "מידע בטיחותי לא ודאי: ",
    PREGNANCY_STATUS_UNKNOWN: "סטטוס היריון לא אושר (אישה בגיל הפוריות).",
    PREGNANCY: "המטופלת מדווחת על היריון אפשרי.",
    OBJECTIVE_FINDINGS_MISSING: "לשון או דופק לא הוזנו, ולכן רמת הביטחון מוגבלת.",
    PLACEHOLDER_WEIGHTS: "הקישורים בין תסמינים לתבניות נגזרו אוטומטית מ-WHO 2022 ומהתקן GB/T 16751.2. למשקלות יש טיוטה מרשומות TCM-SD רק בתבניות שיש להן מספיק נתונים. הדירוג הוא הצעה בלבד."
  };

  function renderClinician() {
    if (!state) return;
    E.setObjective(state, "tongue", objective.tongue);
    E.setObjective(state, "pulse", objective.pulse);
    var rep = E.report(state, { session_id: "proto_session" });
    clin.textContent = "";
    var flagBox = el("div", { class: "flags" }, rep.flags.map(function (f) {
      var he = FLAG_HE[f.code] || "";
      return el("div", { class: "flag " + f.severity, title: f.code }, [
        he, f.code.indexOf("SAFETY_") === 0 ? el("bdi", { text: f.message_en }) : null, f.verbatim_he ? " · “" + f.verbatim_he + "”" : ""
      ]);
    }));
    var ep = rep.eight_principles;
    var heb = { interior: "פנים", exterior: "חוץ", cold: "קור", heat: "חום", deficiency: "חוסר", excess: "עודף", mixed: "מעורב", undetermined: "לא הוכרע" };
    var dxs = rep.differential.map(function (d) {
      var s = E.featById;
      var card = el("article", { class: "dx" + (d.rank === 1 ? " primary" : "") }, [
        el("div", { class: "dx-head" }, [
          el("div", { class: "dx-name" }, [d.rank + ". " + (d.names.he || d.names.en), " ", el("span", { class: "zh", text: d.names.zh + " " + d.names.pinyin }),
            d.names.he ? el("span", { class: "en", text: " " + d.names.en }) : null]),
          el("span", { class: "score", text: "התאמה " + d.graph_score.toFixed(2) + " · ביטחון " + (d.confidence === "moderate" ? "בינוני" : "נמוך") })
        ]),
        el("div", { class: "bar" }, [el("i", { style: "width:" + Math.round(Math.min(1, d.graph_score) * 100) + "%" })]),
        el("span", { class: "id", text: d.syndrome_id + " · " + d.category })
      ]);
      card.appendChild(el("h3", { text: "תומך (" + d.supporting.length + ")" }));
      card.appendChild(evList(d.supporting, function (x) {
        var m = x.matched_manifestation_en || "";
        return el("li", {}, [s[x.feature_id].label_he + " ", el("span", { class: "en", text: I.he(m) ? "“" + I.he(m) + "” " : m }), I.he(m) ? el("span", { class: "zh", text: m }) : null,
          " ", el("span", { class: "id", text: x.sources.join("+") + (x.records ? " · " + x.records + " · משקל " + x.weight : "") }),
          " ", answerButtons(x.feature_id, true)]);
      }));
      if (d.contradicting.length) {
        card.appendChild(el("h3", { text: "סותר (" + d.contradicting.length + ")" }));
        card.appendChild(evList(d.contradicting, function (x) {
          return el("li", {}, ["נשלל: " + s[x.feature_id].label_he + " ", answerButtons(x.feature_id, false)]);
        }, "contra"));
      }
      if (d.missing_key_manifestations.length) {
        var det = el("details", { open: "" }, [el("summary", { text: "לא נשאל / לא נבדק (" + d.missing_key_manifestations.length + "): סמנו כן/לא כדי לדייק" })]);
        det.appendChild(evList(d.missing_key_manifestations, function (x) {
          var m = x.manifestation_en || "";
          return el("li", {}, [s[x.feature_id].label_he + " ", el("span", { class: "en", text: I.he(m) ? "“" + I.he(m) + "” " : m }), I.he(m) ? el("span", { class: "zh", text: m }) : null, " ",
            answerButtons(x.feature_id, undefined)]);
        }));
        card.appendChild(det);
      }
      var src = el("details", {}, [el("summary", { text: "הטקסט במקור (" + I.books(d.supporting[0].evidence_ref) + ")" }),
        el("div", { class: "src" }, [d.source_text.presentation, d.source_text.tongue ? " " + d.source_text.tongue : "", d.source_text.pulse ? " " + d.source_text.pulse : "", " ",
          el("a", { class: "srclink", href: I.source("WHO-ISTTCM-2022").url, target: "_blank", rel: "noopener", text: "מקור" })])]);
      if (d.source_text.gb_zh) {
        var gbLink = I.source("GBT-16751-2");
        src.appendChild(el("div", { class: "src he" }, ["התקן הסיני GB/T 16751.2, סעיף " + d.source_text.gb_code + ": " + I.heOr(d.source_text.gb_zh) + " ",
          el("a", { class: "srclink", href: gbLink.url, target: "_blank", rel: "noopener", text: "מקור" })]));
        src.appendChild(el("div", { class: "src zh" }, [d.source_text.gb_zh]));
      }
      card.appendChild(src);
      return card;
    });
    var json = JSON.stringify(rep, null, 2);
    var copy = el("button", { class: "btn ghost", type: "button", text: "העתקת JSON" });
    var pre = el("pre", { class: "json", text: json });
    copy.addEventListener("click", function () {
      var done = function () { copy.textContent = "הועתק"; setTimeout(function () { copy.textContent = "העתקת JSON"; }, 1500); };
      try {
        navigator.clipboard.writeText(json).then(done, function () { selectPre(); });
      } catch (e) { selectPre(); }
    });
    function selectPre() { var r = document.createRange(); r.selectNodeContents(pre); var sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); }
    var findingsList = rep.findings.filter(function (f) { return E.featById[f.feature_id].kind === undefined || E.featById[f.feature_id].kind === "symptom"; });
    var yes = findingsList.filter(function (f) { return f.value === "present"; });
    var no = findingsList.filter(function (f) { return f.value === "absent"; });
    var dq = rep.discriminating_questions[0];
    var children = [
      scenarioBanner(),
      el("div", { class: "panel" }, [
        el("h2", { text: "הצעה למטפל" }),
        el("p", { class: "summary", text: rep.clinician_summary.text, style: "margin:0" }),
        el("div", { class: "ep" }, [
          el("span", { text: "פנים/חוץ: " + heb[ep.interior_exterior.value] }),
          el("span", { text: "קור/חום: " + heb[ep.cold_heat.value] }),
          el("span", { text: "חוסר/עודף: " + heb[ep.deficiency_excess.value] })
        ]),
        dq ? el("p", { style: "margin:0;font-size:.92rem", text: "שאלת הבחנה מוצעת: " + dq.question_he }) : null
      ]),
      flagBox,
      el("div", { class: "grid2" }, [objectivePanel("tongue", "לשון"), objectivePanel("pulse", "דופק")]),
      el("div", { class: "panel" }, [
        el("h3", { text: "ממצאים מהראיון (" + yes.length + " קיימים, " + no.length + " נשללו)" }),
        el("div", { class: "understood", style: "justify-self:start;max-width:none" },
          yes.map(function (f) { return el("span", { class: "chip", text: f.label_he, title: f.verbatim_he || "" }); })
            .concat(no.map(function (f) { return el("span", { class: "chip neg", text: f.label_he }); }))),
        state.patient.medications ? el("p", { style: "margin:0;font-size:.9rem", text: "תרופות ורקע: " + state.patient.medications }) : null
      ]),
      el("h2", { text: "תבניות אפשריות" })
    ];
    if (!dxs.length) children.push(el("p", { class: "empty", text: "עוד אין מספיק ממצאים. השלימו את הראיון בלשונית 'ראיון המטופל', או לחצו על 'מילוי מקרה לדוגמה'." }));
    children = children.concat(dxs);
    if (window.TCMTreatmentUI) {
      var txSection = el("section", { id: "tx", class: "txwrap" });
      children.push(txSection);
    }
    children.push(el("details", {}, [el("summary", { text: "DiagnosticReport (JSON)" }), el("div", { class: "row", style: "margin:8px 0" }, [copy]), pre]));
    children.forEach(function (c) { if (c) clin.appendChild(c); });
    if (txSection) window.TCMTreatmentUI.render(txSection, { report: rep, state: state, featById: E.featById });
  }

  // ---- tabs and demo ----
  function showTab(which) {
    document.getElementById("tab-patient").setAttribute("aria-selected", which === "patient");
    document.getElementById("tab-clin").setAttribute("aria-selected", which === "clin");
    document.getElementById("view-patient").hidden = which !== "patient";
    clin.hidden = which !== "clin";
    if (which === "clin") renderClinician();
    window.scrollTo(0, 0);
  }
  document.getElementById("tab-patient").addEventListener("click", function () { showTab("patient"); });
  document.getElementById("tab-clin").addEventListener("click", function () { showTab("clin"); });

  // Sample cases (demo_cases.js): curated presentations, or a random case built from one pattern's
  // links. The clinician view then shows which pattern the case was written for and where it ranked.
  var D = window.TCMDemoCases;
  var scenario = null;
  var synById = {};
  kb.syndromes.forEach(function (s) { synById[s.id] = s; });
  var pick = document.getElementById("demo-case");
  pick.appendChild(el("option", { value: "any", text: "מקרה מוכן אקראי" }));
  pick.appendChild(el("option", { value: "random", text: "תרחיש אקראי מתבנית במאגר" }));
  D.CASES.forEach(function (c) { pick.appendChild(el("option", { value: c.id, text: c.title })); });

  function runDemo(c) {
    start();
    chat.textContent = "";
    scenario = c;
    var p = c.patient;
    say("מקרה לדוגמה: " + c.title + ". " + (p.sex === "F" ? "אישה" : "גבר") + " בן/בת " + p.age +
        (p.sex === "F" ? (p.pregnancy === "yes" ? ", בהיריון" : p.pregnancy === "no" ? ", לא בהיריון" : ", סטטוס היריון לא נמסר") : "") + ".", "sys");
    var obj = D.run(E, state, c, function (x, who) {
      if (who === "understood") showUnderstood(x); else say(x, who);
    });
    if (obj.halted) { halt(); showTab("clin"); return; }
    var seen = (obj.tongue || []).concat(obj.pulse || []).map(function (id) { return E.featById[id].label_he; });
    say("הראיון לדוגמה הסתיים." + (seen.length ? " המטפל/ת סימן/ה בבדיקה: " + seen.join(", ") + "." : " לשון ודופק לא הוזנו."));
    objective = { tongue: obj.tongue, pulse: obj.pulse };
    step = "done";
    showTab("clin");
  }
  document.getElementById("demo").addEventListener("click", function () {
    var v = pick.value, c;
    if (v === "random") c = D.random(kb, 1 + Math.floor(Math.random() * 99999));
    else if (v === "any") c = D.CASES[Math.floor(Math.random() * D.CASES.length)];
    else c = D.CASES.filter(function (x) { return x.id === v; })[0];
    runDemo(c);
  });

  // Banner over the clinician view: what the sample case was written for and where it ranked now.
  function scenarioBanner() {
    if (!scenario) return null;
    var c = scenario;
    if (c.halt) {
      return el("div", { class: "scenario " + (step === "halted" ? "ok" : "miss") }, [
        el("b", { text: "מקרה לדוגמה: " + c.title + ". " }),
        step === "halted" ? "הצפוי: הראיון נעצר בגלל סימן אזהרה, וכך קרה." : "הצפוי: הראיון נעצר בגלל סימן אזהרה, אבל הוא לא נעצר."
      ]);
    }
    var best = D.rankOf(E, state, c);
    var names = c.expect.map(function (id) { var s = synById[id]; return s ? (s.he || s.en) : id; });
    var cls = best && best.rank === 1 ? "ok" : best && best.rank <= 5 ? "near" : "miss";
    var where = !best ? "לא קיבלה ציון" : best.rank === 1 ? "במקום הראשון" : "במקום " + best.rank + (best.rank > 5 ? ", מחוץ לחמש המוצגות" : "");
    return el("div", { class: "scenario " + cls }, [
      el("b", { text: (c.random ? c.title + ". " : "מקרה לדוגמה: " + c.title + ". ") }),
      (c.random ? "נבנה מהתבנית: " : "התבנית הצפויה: ") + names.slice(0, c.random ? 1 : 3).join(" / ") + (names.length > 3 ? " ועוד" : "") + ". ",
      "דורגה " + where + (best && c.expect.length > 1 ? " (" + (synById[best.id].he || synById[best.id].en) + ")" : "") + ".",
      c.random ? el("span", { class: "hint", text: " תרחיש אקראי נבנה מהקישורים של התבנית עצמה, ולכן בודק את המנוע מול הנתונים שלו ולא מול שיפוט קליני." }) : null
    ]);
  }

  // Hooks for the voice interview (voice_ui.js): it drives the same state and views, with the
  // ElevenLabs agent in place of the typed composer.
  window.TCMInterviewUI = {
    kb: kb,
    engine: E,
    beginVoice: function () {
      if (window.TCMTreatmentUI) window.TCMTreatmentUI.reset();
      chat.textContent = "";
      state = E.newState({});
      current = null;
      objective = { tongue: null, pulse: null };
      step = "voice";
      showTab("patient");
      renderClinician();
      return state;
    },
    say: say,
    showUnderstood: showUnderstood,
    halt: halt,
    renderClinician: renderClinician,
    showTab: showTab,
    restart: start
  };

  start();
  renderClinician();
})();
