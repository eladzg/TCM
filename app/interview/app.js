// UI for the interview prototype: a Hebrew chat for the patient and a worksheet for the clinician.
(function () {
  "use strict";
  var kb = window.TCM_KB;
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
    chat.textContent = "";
    state = E.newState({});
    current = null;
    objective = { tongue: null, pulse: null };
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
    PLACEHOLDER_WEIGHTS: "הקישורים בין תסמינים לתבניות נגזרו אוטומטית מטקסט WHO 2022, וכולם במשקל ברירת מחדל זהה. הדירוג הוא הצעה בלבד."
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
          el("div", { class: "dx-name" }, [d.rank + ". " + d.names.en, " ", el("span", { class: "zh", text: d.names.zh + " " + d.names.pinyin })]),
          el("span", { class: "score", text: "התאמה " + d.graph_score.toFixed(2) + " · ביטחון " + (d.confidence === "moderate" ? "בינוני" : "נמוך") })
        ]),
        el("div", { class: "bar" }, [el("i", { style: "width:" + Math.round(Math.min(1, d.graph_score) * 100) + "%" })]),
        el("span", { class: "id", text: d.syndrome_id + " · " + d.category })
      ]);
      card.appendChild(el("h3", { text: "תומך (" + d.supporting.length + ")" }));
      card.appendChild(evList(d.supporting, function (x) {
        return el("li", {}, [s[x.feature_id].label_he + " ", el("span", { class: "en", text: x.matched_manifestation_en }),
          " ", el("span", { class: "id", text: x.sources.join("+") + (x.records ? " · " + x.records + " · משקל " + x.weight : "") })]);
      }));
      if (d.contradicting.length) {
        card.appendChild(el("h3", { text: "סותר (" + d.contradicting.length + ")" }));
        card.appendChild(evList(d.contradicting, function (x) {
          return el("li", {}, ["נשלל: " + s[x.feature_id].label_he]);
        }, "contra"));
      }
      if (d.missing_key_manifestations.length) {
        var det = el("details", {}, [el("summary", { text: "לא נשאל / לא נבדק (" + d.missing_key_manifestations.length + ")" })]);
        det.appendChild(evList(d.missing_key_manifestations, function (x) {
          return el("li", {}, [s[x.feature_id].label_he + " ", el("span", { class: "en", text: x.manifestation_en })]);
        }));
        card.appendChild(det);
      }
      var src = el("details", {}, [el("summary", { text: "הטקסט במקור (" + d.supporting[0].evidence_ref + ")" }),
        el("div", { class: "src" }, [d.source_text.presentation, d.source_text.tongue ? " " + d.source_text.tongue : "", d.source_text.pulse ? " " + d.source_text.pulse : ""])]);
      if (d.source_text.gb_zh) {
        src.appendChild(el("div", { class: "src zh" }, ["GB/T 16751.2 " + d.source_text.gb_code + ": " + d.source_text.gb_zh]));
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
    children.push(el("details", {}, [el("summary", { text: "DiagnosticReport (JSON)" }), el("div", { class: "row", style: "margin:8px 0" }, [copy]), pre]));
    children.forEach(function (c) { if (c) clin.appendChild(c); });
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

  // Sample case from the architecture doc (section 4.4): a 41-year-old woman with temporal headaches.
  document.getElementById("demo").addEventListener("click", function () {
    start();
    chat.textContent = "";
    state.patient = { age: 41, sex: "F", pregnancy: "unknown" };
    say("מקרה לדוגמה: אישה בת 41, סטטוס היריון לא נמסר.", "sys");
    E.ingestMedications(state, "ציפרלקס");
    say("ציפרלקס", "pt");
    var text = "יש לי כאבי ראש פועמים ברקות, בעיקר כשאני בלחץ ולפני המחזור. אני עצבנית מאוד, יש לי טעם מר בפה ואני מתעוררת בלילה.";
    say(text, "pt");
    var r = E.ingestText(state, text, "chief_complaint");
    showUnderstood(r.findings);
    var truth = ["FT.DIZZY", "FT.RED_FACE", "FT.RESTLESS", "FT.FEELS_HOT", "FT.PMS", "FT.MENS_IRREGULAR", "FT.DRY_MOUTH"];
    var q, guard = 0;
    while ((q = E.nextQuestion(state)) && guard++ < 40) {
      var v = truth.indexOf(q.feature.id) !== -1 || (state.answers[q.feature.id] && state.answers[q.feature.id].value === true);
      say(q.feature.q_he, "sys");
      say(v ? "כן" : "לא", "pt");
      E.answerQuestion(state, q, v);
    }
    say("הראיון לדוגמה הסתיים. במקרה הזה המטפל/ת סימן/ה לשון אדומה וצדי לשון אדומים, ודופק מיתרי.");
    objective = { tongue: ["TG.RED", "TG.RED_SIDES"], pulse: ["PL.WIRY"] };
    step = "done";
    showTab("clin");
  });

  // Hooks for the voice interview (voice_ui.js): it drives the same state and views, with the
  // ElevenLabs agent in place of the typed composer.
  window.TCMInterviewUI = {
    kb: kb,
    engine: E,
    beginVoice: function () {
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
