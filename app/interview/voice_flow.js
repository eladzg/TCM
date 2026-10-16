// Turn logic for the voice interview. The ElevenLabs agent only speaks and listens: after every
// patient answer it calls the `interview_step` client tool, and this module feeds the answer to the
// rule-based engine and returns what the agent should say next. The engine, not the LLM, decides
// the questions and runs the safety screen.
// Runs in the browser (window.TCMVoiceFlow) and in Node (module.exports) so tests can drive it.
(function (root) {
  "use strict";

  var CLOSING_Q = "לפני שנסיים, יש עוד משהו שחשוב לך שהמטפל ידע?";
  var DONE_SAY = "תודה רבה. המטפל יעבור על התשובות לפני הפגישה.";
  var ASK_AGE = "בן או בת כמה את או אתה?";
  var ASK_SEX = "ולצורך הרישום, את אישה או אתה גבר?";
  var ASK_PREGNANCY = "האם יש אפשרות שאת בהיריון?";
  var ASK_MEDS = "אילו תרופות, ויטמינים או תוספים את או אתה לוקחים כרגע? ואם יש מחלות רקע או אלרגיות, אפשר לספר גם עליהן.";
  var ASK_COMPLAINT = "ספרו לי במילים שלכם מה מביא אתכם לטיפול: מה מרגישים, ממתי, ומה מחמיר או מקל?";

  function createVoiceFlow(E, kb, state) {
    var step = "intake";
    var current = null;           // engine question waiting for an answer
    var pregnancyAsked = false;
    var redFlagRepeats = 0;
    var rfIds = kb.safety.red_flag_questions.map(function (q) { return q.id; });

    function out(status, say, extra) {
      var r = { status: status, say: say, step: step };
      Object.keys(extra || {}).forEach(function (k) { r[k] = extra[k]; });
      return r;
    }

    function halt() {
      step = "halted";
      current = null;
      return out("halt", kb.safety.emergency_template_he);
    }

    function needsPregnancy() {
      var p = state.patient;
      return p.sex === "F" && (!p.age || (p.age >= 12 && p.age <= 55));
    }

    function redFlagPrompt() {
      return "לפני שנמשיך, כמה שאלות בטיחות. האם אחד מהדברים האלה קורה לך עכשיו? " +
        kb.safety.red_flag_questions.map(function (q) { return q.q_he.replace(/^האם\s+/, "").replace(/\?$/, ""); }).join("; ") + "?";
    }

    function askNext() {
      current = E.nextQuestion(state);
      if (!current) {
        step = "closing";
        return out("ask", CLOSING_Q);
      }
      return out("ask", current.feature.q_he, { feature: current.feature.id, phase: current.phase });
    }

    function step_(p) {
      p = p || {};
      var said = String(p.patient_said || "").trim();
      var answer = p.answer || "other";
      var findings = [];

      if (step === "halted") return halt();
      if (step === "done") return out("done", DONE_SAY);

      if (step === "intake") {
        if (p.age) state.patient.age = Number(p.age) || state.patient.age;
        if (p.sex === "F" || p.sex === "M") state.patient.sex = p.sex;
        if (pregnancyAsked) {
          state.patient.pregnancy = p.pregnancy ||
            (answer === "yes" ? "yes" : answer === "no" ? "no" : "unknown");
        }
        if (screenOnly(said)) return halt();
        if (!state.patient.age) return out("repeat", ASK_AGE);
        if (!state.patient.sex) return out("ask", ASK_SEX);
        if (needsPregnancy() && !pregnancyAsked) {
          pregnancyAsked = true;
          return out("ask", ASK_PREGNANCY);
        }
        if (!needsPregnancy()) state.patient.pregnancy = "na";
        step = "redflags";
        return out("ask", redFlagPrompt());
      }

      if (step === "redflags") {
        var ids = String(p.red_flags || "").split(/[\s,]+/).filter(function (x) { return rfIds.indexOf(x) !== -1; });
        if (answer === "yes" || ids.length) {
          ids.forEach(function (id) { E.redFlagAnswer(state, id, true); });
          if (!ids.length) {
            state.flags.push({ category: "A", type: "rf_unspecified", gloss_en: "urgent symptom reported at screening",
                               verbatim_he: said, status: "current" });
          }
          state.halted = true;
          return halt();
        }
        if (screenOnly(said)) return halt();
        if (answer === "unsure" && redFlagRepeats === 0) {
          redFlagRepeats += 1;
          return out("repeat", "רק כדי לוודא, כי זה חשוב: " + redFlagPrompt());
        }
        if (answer === "unsure") {
          state.flags.push({ category: "D", type: "rf_uncertain", gloss_en: "patient unsure about urgent-symptom screening",
                             verbatim_he: said, status: "current" });
        }
        step = "meds";
        return out("ask", ASK_MEDS);
      }

      if (step === "meds") {
        if (screenOnly(said)) return halt();
        E.ingestMedications(state, answer === "no" ? "" : said);
        step = "complaint";
        return out("ask", ASK_COMPLAINT, { medications: state.patient.medications });
      }

      if (step === "complaint") {
        var c = E.ingestText(state, said, "chief_complaint");
        if (c.halted) return halt();
        step = "questions";
        return withFindings(askNext(), c.findings);
      }

      if (step === "questions") {
        var f = current.feature;
        var r = E.ingestText(state, said, f.id);
        if (r.halted) return halt();
        findings = r.findings;
        var own = r.findings.filter(function (x) { return x.feature === f.id; })[0];
        if (answer === "yes" || answer === "no" || answer === "unsure") {
          E.answerQuestion(state, current, answer === "yes" ? true : answer === "no" ? false : null);
        } else if (own) {
          E.answerQuestion(state, current, own.value);
        } else {
          state.asked.push(f.id);
          if (current.phase === "adaptive") state.adaptiveAsked += 1;
          E.setAnswer(state, f.id, null, "question", said);
        }
        return withFindings(askNext(), findings);
      }

      if (step === "closing") {
        if (said && answer !== "no") {
          var z = E.ingestText(state, said, "closing");
          if (z.halted) return halt();
          findings = z.findings;
        }
        step = "done";
        return withFindings(out("done", DONE_SAY), findings);
      }
      throw new Error("unknown step " + step);
    }

    // A red-flag word in an intake or medication answer halts the interview too; only then is the
    // answer passed to ingestText, so these answers never add symptom findings.
    function screenOnly(said) {
      if (!said || !E.screenText(said).length) return false;
      return E.ingestText(state, said, step).halted;
    }

    function withFindings(r, findings) {
      r.findings = findings || [];
      return r;
    }

    return {
      step: step_,
      current: function () { return current; },
      stage: function () { return step; },
      finish: function () { if (step !== "halted") step = "done"; }
    };
  }

  var api = { createVoiceFlow: createVoiceFlow };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TCMVoiceFlow = api;
})(typeof window !== "undefined" ? window : this);
