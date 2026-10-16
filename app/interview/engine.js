// Rule-based engine for the Hebrew interview prototype: Hebrew free-text extraction, safety screen,
// pattern scoring, next-question choice and the draft DiagnosticReport.
// Runs in the browser (window.TCMEngine) and in Node (module.exports) so tests can drive it.
//
// Scoring is a placeholder until the clinician sets real weights: every derived pattern-feature
// link carries kb.defaults.weight, and a pattern's score is a cosine similarity between the
// findings the patient confirmed and the pattern's linked features, minus a penalty for linked
// features the patient denied.
(function (root) {
  "use strict";

  var MIN_LINKS = 3;          // patterns with fewer derived links are too thin to rank
  var TOP_K = 8;              // candidates considered when choosing the next question
  var MAX_ADAPTIVE = 12;      // adaptive questions after the screening phase
  var NIQQUD = /[֑-ׇ]/g;
  var PREFIX = "ובכלמשה";
  var NEG_BEFORE = /(^|[\s,.;])(לא|אין|בלי|ללא)(\s+(לי|לו|לה|בכלל|ממש|כל כך|אף פעם|היה לי|היו לי))*\s+$/;

  function normalize(text) {
    return String(text || "").replace(NIQQUD, "").replace(/[״"׳']/g, "").toLowerCase();
  }

  function isBoundary(ch) {
    return ch === undefined || /[\s,.;:!?()\-–—/]/.test(ch);
  }

  // Hebrew attaches prefixes (ו, ה, ב, כ, ל, מ, ש) to words, so a term may start after up to two of
  // them; anything else before it means the term is part of another word ("ליחה" in "סליחה").
  function termAt(text, term) {
    var hits = [];
    var from = 0;
    while (true) {
      var i = text.indexOf(term, from);
      if (i === -1) return hits;
      var j = i;
      var prefixes = 0;
      while (prefixes < 2 && j > 0 && PREFIX.indexOf(text[j - 1]) !== -1 && !isBoundary(text[j - 1])) {
        j -= 1;
        prefixes += 1;
      }
      if (isBoundary(text[j - 1])) hits.push(i);
      from = i + 1;
    }
  }

  function quoteAround(original, index, length) {
    var start = index;
    var end = index + length;
    while (start > 0 && !/[,.;!?\n]/.test(original[start - 1])) start -= 1;
    while (end < original.length && !/[,.;!?\n]/.test(original[end])) end += 1;
    return original.slice(start, end).trim();
  }

  function createEngine(kb) {
    var features = kb.features;
    var featById = {};
    features.forEach(function (f) { featById[f.id] = f; });
    var weight = kb.defaults.weight;
    var penalty = kb.defaults.denied_penalty;
    var syndromes = kb.syndromes.filter(function (s) { return s.links.length >= MIN_LINKS; });
    var groupOrder = Object.keys(kb.groups);

    function newState(patient) {
      return {
        patient: patient || {},   // {age, sex: "F"|"M", pregnancy: "yes"|"no"|"unknown"|"na"}
        answers: {},              // feature id -> {value: true|false|null, source, quote}
        asked: [],                // feature ids in the order asked
        adaptiveAsked: 0,
        flags: [],                // safety flags
        halted: false,
        tongueObserved: false,
        pulseObserved: false,
        transcript: []
      };
    }

    function sexAllows(f, state) {
      return !f.sex || !state.patient.sex || f.sex === state.patient.sex;
    }

    function setAnswer(state, featureId, value, source, quote) {
      if (!featById[featureId]) throw new Error("unknown feature " + featureId);
      state.answers[featureId] = { value: value, source: source, quote: quote || "" };
    }

    // Clinician tongue/pulse entry: checked items are present, every other item in the section is
    // absent (the clinician looked), and nothing is recorded when the section was not observed.
    function setObjective(state, kind, checkedIds) {
      var observed = checkedIds !== null;
      if (kind === "tongue") state.tongueObserved = observed;
      else state.pulseObserved = observed;
      features.forEach(function (f) {
        if (f.kind !== kind) return;
        if (!observed) { delete state.answers[f.id]; return; }
        setAnswer(state, f.id, checkedIds.indexOf(f.id) !== -1, "clinician");
      });
    }

    // Hebrew free text -> findings. Negated mentions ("אין לי צמא") become "no" answers.
    function extract(text) {
      var original = String(text || "");
      var norm = normalize(original);
      var found = {};
      features.forEach(function (f) {
        (f.syn_he || []).forEach(function (term) {
          var t = normalize(term);
          termAt(norm, t).forEach(function (i) {
            var before = norm.slice(Math.max(0, i - 24), i);
            var negated = NEG_BEFORE.test(before) && !/^(לא|אין|בלי)/.test(t);
            var prev = found[f.id];
            // a positive mention wins over a negated one of the same feature
            if (!prev || (prev.value === false && !negated)) {
              found[f.id] = { feature: f.id, value: !negated, quote: quoteAround(original, i, t.length) };
            }
          });
        });
      });
      return Object.keys(found).map(function (k) { return found[k]; });
    }

    function screenText(text) {
      var norm = normalize(text);
      var hits = [];
      kb.safety.red_flag_terms.forEach(function (rule) {
        rule.terms.forEach(function (term) {
          var t = normalize(term);
          termAt(norm, t).forEach(function (i) {
            var before = norm.slice(Math.max(0, i - 24), i);
            if (NEG_BEFORE.test(before)) return;
            hits.push({ category: "A", type: rule.gloss_en.replace(/\W+/g, "_"), gloss_en: rule.gloss_en,
                        verbatim_he: quoteAround(String(text), i, t.length) });
          });
        });
      });
      return hits;
    }

    function addFlag(state, flag) {
      var exists = state.flags.some(function (x) { return x.type === flag.type && x.category === flag.category; });
      if (!exists) state.flags.push(flag);
      if (flag.category === "A") state.halted = true;
    }

    // Takes the patient's free-text answer: red-flag screen first, then finding extraction.
    function ingestText(state, text, context) {
      state.transcript.push({ role: "patient", text: text, context: context || "" });
      var redFlags = screenText(text);
      redFlags.forEach(function (f) { f.status = "current"; addFlag(state, f); });
      if (state.halted) return { halted: true, findings: [], flags: redFlags };
      var findings = extract(text).filter(function (x) { return sexAllows(featById[x.feature], state); });
      findings.forEach(function (x) {
        if (!state.answers[x.feature]) setAnswer(state, x.feature, x.value, "free_text", x.quote);
      });
      return { halted: false, findings: findings, flags: redFlags };
    }

    function ingestMedications(state, text) {
      state.patient.medications = text;
      var norm = normalize(text);
      kb.safety.constraint_terms.forEach(function (rule) {
        rule.terms.forEach(function (term) {
          var t = normalize(term);
          if (termAt(norm, t).length) {
            addFlag(state, { category: "C", type: rule.code.toLowerCase(), gloss_en: rule.gloss_en,
                             verbatim_he: quoteAround(String(text), norm.indexOf(t), t.length), status: "current" });
          }
        });
      });
    }

    function redFlagAnswer(state, questionId, yes) {
      if (!yes) return;
      var q = kb.safety.red_flag_questions.filter(function (x) { return x.id === questionId; })[0];
      addFlag(state, { category: "A", type: questionId.toLowerCase(), gloss_en: q.gloss_en,
                       verbatim_he: q.q_he + " - כן", status: "current" });
    }

    function score(state) {
      var yes = Object.keys(state.answers).filter(function (k) { return state.answers[k].value === true; });
      var yesWeight = yes.length * weight;
      var ranked = syndromes.map(function (s) {
        var P = 0, D = 0, L = 0, supporting = [], contradicting = [], missing = [];
        s.links.forEach(function (l) {
          if (!sexAllows(featById[l.f], state)) return;
          L += weight;
          var a = state.answers[l.f];
          if (a && a.value === true) { P += weight; supporting.push(l); }
          else if (a && a.value === false) { D += weight; contradicting.push(l); }
          else missing.push(l);
        });
        var value = yesWeight && L ? Math.max(0, P - penalty * D) / Math.sqrt(L * yesWeight) : 0;
        return { syndrome: s, score: value, supporting: supporting, contradicting: contradicting, missing: missing };
      });
      ranked.sort(function (a, b) { return b.score - a.score || b.supporting.length - a.supporting.length; });
      return ranked;
    }

    function screeningQueue(state) {
      return features
        .filter(function (f) { return f.screen && (f.kind || "symptom") === "symptom" && sexAllows(f, state); })
        .sort(function (a, b) { return groupOrder.indexOf(a.group) - groupOrder.indexOf(b.group); })
        .filter(function (f) { return !state.answers[f.id]; });
    }

    // The question that best splits the current top candidates: the feature whose linked
    // candidates hold closest to half of the candidates' score mass.
    function bestDiscriminator(state, ranked) {
      var top = ranked.slice(0, TOP_K).filter(function (r) { return r.score > 0; });
      if (top.length === 0) return null;
      var total = top.reduce(function (s, r) { return s + r.score; }, 0);
      var best = null;
      features.forEach(function (f) {
        if ((f.kind || "symptom") !== "symptom" || state.answers[f.id] || !sexAllows(f, state)) return;
        var mass = 0, separates = [];
        top.forEach(function (r) {
          if (r.syndrome.links.some(function (l) { return l.f === f.id; })) {
            mass += r.score / total;
            separates.push(r.syndrome.id);
          }
        });
        if (!separates.length) return;
        var value = Math.min(mass, 1 - mass) + (separates[0] === top[0].syndrome.id ? 0.05 : 0);
        if (top.length === 1) value = 1;
        if (!best || value > best.value) best = { feature: f, value: value, separates: separates };
      });
      return best;
    }

    function nextQuestion(state) {
      if (state.halted) return null;
      var queue = screeningQueue(state);
      if (queue.length) return { phase: "screening", feature: queue[0], separates: [] };
      if (state.adaptiveAsked >= MAX_ADAPTIVE) return null;
      var best = bestDiscriminator(state, score(state));
      if (!best) return null;
      return { phase: "adaptive", feature: best.feature, separates: best.separates };
    }

    function answerQuestion(state, question, value) {
      setAnswer(state, question.feature.id, value, "question");
      state.asked.push(question.feature.id);
      if (question.phase === "adaptive") state.adaptiveAsked += 1;
      state.transcript.push({ role: "system", text: question.feature.q_he, feature: question.feature.id });
      state.transcript.push({ role: "patient", text: value === true ? "כן" : value === false ? "לא" : "לא בטוח/ה" });
    }

    function principle(yesFeatures, a, b, labels) {
      var sa = [], sb = [];
      yesFeatures.forEach(function (f) {
        if ((f.tags || []).indexOf(a) !== -1) sa.push(f.id);
        if ((f.tags || []).indexOf(b) !== -1) sb.push(f.id);
      });
      var value = "undetermined";
      if (sa.length >= 2 && sa.length >= 2 * Math.max(sb.length, 1)) value = labels[0];
      else if (sb.length >= 2 && sb.length >= 2 * Math.max(sa.length, 1)) value = labels[1];
      else if (sa.length >= 2 && sb.length >= 2) value = "mixed";
      return { value: value, supporting_feature_ids: value === labels[0] ? sa : value === labels[1] ? sb : sa.concat(sb) };
    }

    function report(state, meta) {
      meta = meta || {};
      var ranked = score(state).filter(function (r) { return r.score > 0; });
      var findingIds = {};
      var findings = Object.keys(state.answers).map(function (fid, i) {
        var a = state.answers[fid];
        var f = featById[fid];
        var id = (f.kind === "tongue" ? "OBS-T" : f.kind === "pulse" ? "OBS-P" : "F-") + (i + 1);
        findingIds[fid] = id;
        return { finding_id: id, feature_id: fid, label_he: f.label_he,
                 value: a.value === true ? "present" : a.value === false ? "absent" : "unknown",
                 source: a.source, verbatim_he: a.quote || null };
      });
      var yesFeatures = Object.keys(state.answers)
        .filter(function (k) { return state.answers[k].value === true; })
        .map(function (k) { return featById[k]; });
      var flags = state.flags.map(function (f) {
        return { code: "SAFETY_CATEGORY_" + f.category, severity: f.category === "A" ? "red" : "amber",
                 message_en: f.gloss_en, verbatim_he: f.verbatim_he, related_ids: [] };
      });
      var p = state.patient;
      if (p.sex === "F" && p.age >= 12 && p.age <= 55 && (!p.pregnancy || p.pregnancy === "unknown")) {
        flags.push({ code: "PREGNANCY_STATUS_UNKNOWN", severity: "red",
                     message_en: "Woman aged " + p.age + "; pregnancy status not confirmed.", related_ids: ["safety.pregnancy_status"] });
      }
      if (p.pregnancy === "yes") {
        flags.push({ code: "PREGNANCY", severity: "red", message_en: "Patient reports pregnancy.", related_ids: ["safety.pregnancy_status"] });
      }
      if (!state.tongueObserved || !state.pulseObserved) {
        flags.push({ code: "OBJECTIVE_FINDINGS_MISSING", severity: "amber",
                     message_en: "Tongue or pulse not entered; confidence is capped at moderate.", related_ids: [] });
      }
      flags.push({ code: "PLACEHOLDER_WEIGHTS", severity: "info",
                   message_en: "Pattern-feature links were derived automatically from WHO 2022 text and all carry the same placeholder weight. Ranking is a proposal only.", related_ids: [] });
      var differential = ranked.slice(0, 5).map(function (r, i) {
        var s = r.syndrome;
        var objective = state.tongueObserved && state.pulseObserved;
        var confidence = r.supporting.length < 3 ? "low" : "moderate";
        if (!objective && confidence === "moderate" && r.supporting.length < 5) confidence = "low";
        return {
          rank: i + 1,
          role: i === 0 ? "primary" : "alternative",
          syndrome_id: s.id,
          names: { en: s.en, pinyin: s.py, zh: s.zh, he: s.he || null },
          category: s.cat,
          graph_score: Math.round(r.score * 1000) / 1000,
          confidence: confidence,
          supporting: r.supporting.map(function (l) {
            return { finding_id: findingIds[l.f], feature_id: l.f, matched_manifestation_en: l.ev, evidence_ref: s.src };
          }),
          contradicting: r.contradicting.map(function (l) {
            return { finding_id: findingIds[l.f], feature_id: l.f, conflict_en: "Reported absent: " + l.ev, evidence_ref: s.src };
          }),
          missing_key_manifestations: r.missing.map(function (l) {
            var f = featById[l.f];
            return { feature_id: l.f, manifestation_en: l.ev, evidence_ref: s.src, suggested_question_he: f.q_he || null };
          }),
          source_text: { presentation: s.text, tongue: s.tongue, pulse: s.pulse },
          treatment_principle: s.tp ? { text_en: s.tp, evidence_ref: s.src } : null
        };
      });
      var disc = bestDiscriminator(state, score(state));
      var summary = clinicianSummary(differential, state, flags);
      return {
        schema_version: "diagnostic_report.v1",
        generator: "interview_prototype.v0 (rule-based, placeholder weights)",
        report_id: meta.report_id || "dx_proto_" + Date.now(),
        session_id: meta.session_id || null,
        kb_version: kb.kb_version,
        created_at: meta.created_at || new Date().toISOString(),
        status: "draft_for_clinician",
        patient: { age: p.age || null, sex: p.sex || null, pregnancy: p.pregnancy || null, medications_he: p.medications || null },
        data_completeness: {
          tongue_observed: state.tongueObserved,
          pulse_observed: state.pulseObserved,
          unanswered_key_slots: flags.some(function (f) { return f.code === "PREGNANCY_STATUS_UNKNOWN"; }) ? ["safety.pregnancy_status"] : []
        },
        eight_principles: {
          interior_exterior: principle(yesFeatures, "interior", "exterior", ["interior", "exterior"]),
          cold_heat: principle(yesFeatures, "cold", "heat", ["cold", "heat"]),
          deficiency_excess: principle(yesFeatures, "def", "excess", ["deficiency", "excess"])
        },
        findings: findings,
        differential: differential,
        discriminating_questions: disc ? [{ feature_id: disc.feature.id, question_he: disc.feature.q_he, separates: disc.separates }] : [],
        flags: flags,
        clinician_summary: { language: "he", text: summary }
      };
    }

    function clinicianSummary(differential, state, flags) {
      if (state.halted) return "הראיון הופסק בגלל סימן אזהרה דחוף. נדרשת פנייה רפואית לפני כל טיפול.";
      if (!differential.length) return "אין מספיק ממצאים כדי להציע תבנית. מומלץ להשלים ראיון ובדיקת לשון ודופק.";
      var first = differential[0];
      var labels = first.supporting.map(function (x) { return featById[x.feature_id].label_he; });
      var text = "הממצאים תואמים בעיקר את התבנית " + first.names.en + " (" + first.names.zh + "): " +
        labels.slice(0, 6).join(", ") + ".";
      if (differential[1]) text += " חלופה: " + differential[1].names.en + ".";
      var missing = flags.filter(function (f) { return f.code === "OBJECTIVE_FINDINGS_MISSING" || f.code === "PREGNANCY_STATUS_UNKNOWN"; });
      if (missing.length) text += " חסר: " + missing.map(function (f) {
        return f.code === "PREGNANCY_STATUS_UNKNOWN" ? "סטטוס היריון" : "לשון/דופק";
      }).join(", ") + ".";
      return text + " זו הצעה לשיקול המטפל/ת, על בסיס משקלות ברירת מחדל שטרם כוילו.";
    }

    return {
      newState: newState,
      extract: extract,
      ingestText: ingestText,
      ingestMedications: ingestMedications,
      redFlagAnswer: redFlagAnswer,
      setAnswer: setAnswer,
      setObjective: setObjective,
      score: score,
      nextQuestion: nextQuestion,
      answerQuestion: answerQuestion,
      report: report,
      features: features,
      featById: featById,
      MAX_ADAPTIVE: MAX_ADAPTIVE
    };
  }

  var api = { createEngine: createEngine, normalize: normalize };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TCMEngine = api;
})(typeof window !== "undefined" ? window : this);
