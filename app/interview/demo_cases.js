// Sample patients for the "fill a sample case" button, to check how the matching and the treatment
// plan behave across different presentations. Each curated case is a textbook presentation written
// for this prototype (not a real patient): intake, medications, a free-text complaint, the findings the
// patient would answer "yes" to, the clinician's tongue and pulse, and the WHO 2022 patterns a
// clinician would accept as the answer. random() builds a case from one pattern's own links instead,
// which checks the engine against its own data rather than against clinical judgement.
(function (root) {
  "use strict";

  var CASES = [
    { id: "liver_yang", title: "כאבי ראש ברקות עם עצבנות", expect: ["SYN.LR.GAN_YANG_SHANG_KANG", "SYN.LR.GAN_HUO_SHANG_YAN", "SYN.LR.GAN_YU_HUA_HUO"],
      patient: { age: 41, sex: "F", pregnancy: "unknown" }, meds: "ציפרלקס",
      text: "יש לי כאבי ראש פועמים ברקות, בעיקר כשאני בלחץ ולפני המחזור. אני עצבנית מאוד, יש לי טעם מר בפה ואני מתעוררת בלילה.",
      yes: ["FT.DIZZY", "FT.RED_FACE", "FT.RESTLESS", "FT.FEELS_HOT", "FT.PMS", "FT.MENS_IRREGULAR", "FT.DRY_MOUTH"],
      tongue: ["TG.RED", "TG.RED_SIDES"], pulse: ["PL.WIRY"] },
    { id: "spleen_qi", title: "עייפות ונפיחות אחרי האוכל", expect: ["SYN.SP.PI_QI_XU", "SYN.SP.PI_XU_TAN_SHI", "SYN.QB.QI_XU"],
      patient: { age: 34, sex: "M" }, meds: "",
      text: "אני עייף כל הזמן, הבטן נפוחה אחרי שאני אוכל, אין לי תיאבון והיציאות רכות.",
      yes: ["FT.FATIGUE", "FT.ABD_DIST", "FT.POSTMEAL_DIST", "FT.POOR_APPETITE", "FT.LOOSE_STOOL", "FT.LOW_VOICE", "FT.PALE_FACE", "FT.HEAVINESS"],
      tongue: ["TG.PALE", "TG.ENLARGED", "TG.COAT_WHITE"], pulse: ["PL.WEAK", "PL.SLACK"] },
    { id: "kidney_yang", title: "גב תחתון קר והשתנה לילית", expect: ["SYN.KI.SHEN_YANG_XU", "SYN.KI.SHEN_XU_HAN_SHI", "SYN.KI.SHEN_QI_BU_GU"],
      patient: { age: 63, sex: "M" }, meds: "טמסולוסין",
      text: "כואב לי הגב התחתון והברכיים חלשות, קר לי כל הזמן ואני קם בלילה הרבה לשירותים.",
      yes: ["FT.LOWBACK", "FT.AVERSION_COLD", "FT.COLD_LIMBS", "FT.FREQ_URINE", "FT.CLEAR_URINE", "FT.FATIGUE", "FT.MALE_SEXUAL", "FT.OEDEMA"],
      tongue: ["TG.PALE", "TG.ENLARGED", "TG.COAT_WHITE"], pulse: ["PL.DEEP", "PL.WEAK", "PL.SLOW"] },
    { id: "kidney_yin", title: "גלי חום והזעות לילה בגיל המעבר", expect: ["SYN.KI.SHEN_YIN_XU", "SYN.ZF.GAN_SHEN_YIN_XU", "SYN.ZF.XIN_SHEN_BU_JIAO", "SYN.QB.YIN_XU"],
      patient: { age: 52, sex: "F", pregnancy: "no" }, meds: "",
      text: "יש לי גלי חום והזעות בלילה, אני לא ישנה טוב, יש לי טנטון וכואב לי הגב התחתון.",
      yes: ["FT.HOT_FLUSHES", "FT.NIGHT_SWEATS", "FT.INSOMNIA", "FT.TINNITUS", "FT.LOWBACK", "FT.FIVE_PALM_HEAT", "FT.DRY_MOUTH", "FT.DIZZY"],
      tongue: ["TG.RED", "TG.COAT_SCANTY"], pulse: ["PL.THREADY", "PL.RAPID"] },
    { id: "liver_qi", title: "לחץ, אנחות ומתח בצלעות", expect: ["SYN.LR.GAN_YU_QI_ZHI", "SYN.LR.GAN_YU_XUE_XU", "SYN.ZF.GAN_PI_BU_HE", "SYN.ZF.GAN_WEI_BU_HE"],
      patient: { age: 29, sex: "F", pregnancy: "no" }, meds: "",
      text: "אני במצב רוח ירוד ומרבה לאנוח, יש לי מתח מתחת לצלעות והמחזור לא סדיר.",
      yes: ["FT.LOW_MOOD", "FT.FLANK_PAIN", "FT.MENS_IRREGULAR", "FT.PMS", "FT.BELCHING", "FT.CHEST_TIGHT", "FT.IRRITABLE"],
      tongue: [], pulse: ["PL.WIRY"] },
    { id: "heart_spleen", title: "נדודי שינה, דאגה ודפיקות לב", expect: ["SYN.ZF.XIN_PI_LIANG_XU", "SYN.ZF.XIN_PI_QI_XU", "SYN.HT.XIN_XUE_XU", "SYN.ZF.XIN_GAN_XUE_XU"],
      patient: { age: 45, sex: "F", pregnancy: "no" }, meds: "",
      text: "קשה לי להירדם, יש לי חלומות רבים ודפיקות לב, אני שוכחת דברים ומרגישה עייפה.",
      yes: ["FT.INSOMNIA", "FT.DREAMS", "FT.PALPITATIONS", "FT.POOR_MEMORY", "FT.FATIGUE", "FT.POOR_APPETITE", "FT.PALE_FACE", "FT.ANXIETY", "FT.MENS_SCANTY"],
      tongue: ["TG.PALE"], pulse: ["PL.THREADY", "PL.WEAK"] },
    { id: "wind_cold", title: "הצטננות עם צמרמורות", expect: ["SYN.ETI.FENG_HAN_BIAO", "SYN.LU.FENG_HAN_XI_FEI", "SYN.ETI.BIAO_HAN"],
      patient: { age: 27, sex: "M" }, meds: "",
      text: "התחלתי להרגיש רע אתמול, יש לי צמרמורות, האף סתום ויש לי נזלת וכאבים בגוף.",
      yes: ["FT.AVERSION_COLD", "FT.NASAL", "FT.JOINT_PAIN", "FT.HEADACHE", "FT.NO_SWEAT", "FT.COUGH", "FT.WHITE_PHLEGM"],
      tongue: ["TG.COAT_THIN", "TG.COAT_WHITE"], pulse: ["PL.SUPERFICIAL", "PL.TIGHT"] },
    { id: "wind_heat", title: "כאב גרון וחום", expect: ["SYN.ETI.FENG_RE_BIAO", "SYN.LU.FENG_RE_FAN_FEI", "SYN.ZF.FEI_WEI_FENG_RE"],
      patient: { age: 19, sex: "F", pregnancy: "no" }, meds: "",
      text: "יש לי כאב גרון חזק וחום, אני צמאה ומשתעלת עם ליחה צהובה.",
      yes: ["FT.SORE_THROAT", "FT.FEVER", "FT.THIRST", "FT.COUGH", "FT.YELLOW_PHLEGM", "FT.HEADACHE", "FT.NASAL"],
      tongue: ["TG.RED_TIP", "TG.COAT_THIN", "TG.COAT_YELLOW"], pulse: ["PL.SUPERFICIAL", "PL.RAPID"] },
    { id: "bladder_damp_heat", title: "צריבה במתן שתן", expect: ["SYN.KI.PANG_GUANG_SHI_RE", "SYN.LR.GAN_DAN_SHI_RE", "SYN.ETI.SHI_RE"],
      patient: { age: 33, sex: "F", pregnancy: "no" }, meds: "",
      text: "יש לי צריבה כשאני משתינה, השתן כהה ואני צריכה ללכת לשירותים כל הזמן.",
      yes: ["FT.PAINFUL_URINE", "FT.YELLOW_URINE", "FT.FREQ_URINE", "FT.SCANTY_URINE", "FT.THIRST", "FT.BITTER_MOUTH"],
      tongue: ["TG.RED", "TG.COAT_YELLOW", "TG.COAT_GREASY"], pulse: ["PL.SLIPPERY", "PL.RAPID"] },
    { id: "phlegm_damp", title: "עודף משקל, כבדות וליחה", expect: ["SYN.SP.TAN_SHI_ZHONG_ZU", "SYN.SP.PI_XU_TAN_SHI", "SYN.LU.TAN_SHI_YUN_FEI", "SYN.ETI.SHI_TAN"],
      patient: { age: 50, sex: "M" }, meds: "מטפורמין",
      text: "יש לי עודף משקל, אני מרגיש כבד בכל הגוף, יש לי הרבה ליחה וטעם דביק בפה.",
      yes: ["FT.OBESITY", "FT.HEAVINESS", "FT.PHLEGM", "FT.WHITE_PHLEGM", "FT.STICKY_MOUTH", "FT.SOMNOLENCE", "FT.ABD_DIST", "FT.CHEST_TIGHT", "FT.NAUSEA"],
      tongue: ["TG.ENLARGED", "TG.COAT_GREASY", "TG.COAT_THICK"], pulse: ["PL.SLIPPERY"] },
    { id: "uterus_stasis", title: "כאבי מחזור חזקים עם קרישים", expect: ["SYN.UT.BAO_GONG_YU_ZU", "SYN.UT.CHONG_REN_YU_ZU", "SYN.UT.HAN_NING_BAO_GONG", "SYN.LR.GAN_YU_XUE_YU", "SYN.QB.QI_ZHI_XUE_YU", "SYN.QB.XUE_YU"],
      patient: { age: 31, sex: "F", pregnancy: "no" }, meds: "",
      text: "יש לי כאבי מחזור קשים מאוד, הכאב דוקר ויש הרבה קרישים כהים.",
      yes: ["FT.MENS_PAIN", "FT.MENS_CLOTS", "FT.STABBING_PAIN", "FT.ABD_PAIN", "FT.TENDERNESS", "FT.MENS_IRREGULAR"],
      tongue: ["TG.PURPLE"], pulse: ["PL.HESITANT", "PL.WIRY"] },
    { id: "stomach_fire", title: "צרבת, רעב וריח מהפה", expect: ["SYN.SP.WEI_HUO", "SYN.SP.WEI_RE_YIN_XU", "SYN.ZF.GAN_HUO_FAN_WEI"],
      patient: { age: 38, sex: "M" }, meds: "אומפרדקס",
      text: "יש לי צרבת וכאב בקיבה, אני כל הזמן רעב וצמא למשקאות קרים, והחניכיים מדממות.",
      yes: ["FT.BELCHING", "FT.ABD_PAIN", "FT.HUNGER", "FT.THIRST_COLD", "FT.BLEEDING", "FT.CONSTIPATION", "FT.THIRST", "FT.YELLOW_URINE"],
      tongue: ["TG.RED", "TG.COAT_YELLOW", "TG.DRY"], pulse: ["PL.RAPID", "PL.FORCEFUL"] },
    { id: "cold_damp_bi", title: "כאבי מפרקים שמחמירים בקור", expect: ["SYN.MER.HAN_SHI_ZU_LUO", "SYN.ETI.FENG_SHI_XI_BIAO", "SYN.SKB.HAN_SHI_ZHE_YAO", "SYN.SP.HAN_SHI_KUN_PI"],
      patient: { age: 58, sex: "F", pregnancy: "no" }, meds: "קומדין",
      text: "כואבים לי המפרקים והגב, הכאב מחמיר בקור ובלחות ומשתפר עם חום.",
      yes: ["FT.JOINT_PAIN", "FT.COLD_PAIN", "FT.PAIN_WARMTH", "FT.HEAVINESS", "FT.NUMBNESS", "FT.LOWBACK", "FT.AVERSION_COLD"],
      tongue: ["TG.PALE", "TG.COAT_WHITE", "TG.COAT_GREASY"], pulse: ["PL.SLOW", "PL.TIGHT"] },
    { id: "lung_yin", title: "שיעול יבש ממושך", expect: ["SYN.LU.FEI_YIN_XU", "SYN.QB.YIN_XU", "SYN.QB.YIN_XU_NEI_RE"],
      patient: { age: 66, sex: "M" }, meds: "",
      text: "אני משתעל כבר חודשים שיעול יבש, הגרון יבש ואני מזיע בלילה.",
      yes: ["FT.COUGH", "FT.DRY_MOUTH", "FT.NIGHT_SWEATS", "FT.FIVE_PALM_HEAT", "FT.HOT_FLUSHES", "FT.WEIGHT_LOSS", "FT.LOW_VOICE"],
      tongue: ["TG.RED", "TG.COAT_SCANTY", "TG.DRY"], pulse: ["PL.THREADY", "PL.RAPID"] },
    { id: "pregnant_nausea", title: "בחילות בהיריון (בדיקת בטיחות)", expect: ["SYN.SP.PI_QI_XU", "SYN.ZF.GAN_WEI_BU_HE", "SYN.SP.WEI_QI_SHANG_NI", "SYN.SP.WEI_QI_XU"],
      patient: { age: 30, sex: "F", pregnancy: "yes" }, meds: "חומצה פולית",
      text: "אני בשבוע עשר להיריון, יש לי בחילות והקאות כל בוקר, אין לי תיאבון ואני עייפה.",
      yes: ["FT.NAUSEA", "FT.POOR_APPETITE", "FT.FATIGUE", "FT.TASTELESS", "FT.BELCHING"],
      tongue: ["TG.PALE", "TG.COAT_WHITE"], pulse: ["PL.SLIPPERY"] },
    { id: "chest_pain", title: "לחץ בחזה (בדיקת עצירה)", expect: [], halt: true,
      patient: { age: 61, sex: "M" }, meds: "אספירין",
      text: "יש לי לחץ בחזה שמקרין ליד שמאל וקוצר נשימה מהבוקר.",
      yes: [], tongue: [], pulse: [] }
  ];

  // Small seeded generator, so a random case can be reproduced from its number.
  function rng(seed) {
    var s = seed >>> 0;
    return function () { s = (s + 0x6D2B79F5) >>> 0; var t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function shuffle(a, r) { a = a.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function words(f) {
    var s = f.syn_he;
    if (typeof s === "string") { try { s = JSON.parse(s.replace(/'/g, '"')); } catch (e) { s = []; } }
    return s && s.length ? s[0] : f.label_he.split(" / ")[0];
  }

  var QUIET = ["FT.CHEST_TIGHT", "FT.BLOODY_STOOL", "FT.BLEEDING", "FT.PALPITATIONS", "FT.SOB"];

  // A case built from one pattern: most of its linked symptoms are "yes", its linked tongue and
  // pulse findings are what the clinician sees, plus one unrelated symptom as noise.
  function random(kb, seed) {
    var r = rng(seed);
    var feat = {};
    kb.features.forEach(function (f) { feat[f.id] = f; });
    var kind = function (id) { return feat[id].group === "tongue" ? "tongue" : feat[id].group === "pulse" ? "pulse" : "symptom"; };
    var pool = kb.syndromes.filter(function (s) {
      var sym = s.links.filter(function (l) { return feat[l.f] && kind(l.f) === "symptom"; });
      var g = sym.some(function (l) { return feat[l.f].group === "gyn"; }), m = sym.some(function (l) { return feat[l.f].group === "male"; });
      return sym.length >= 5 && !(g && m);
    });
    var syn = pool[Math.floor(r() * pool.length)];
    var ids = syn.links.map(function (l) { return l.f; }).filter(function (id, i, a) { return feat[id] && a.indexOf(id) === i; });
    var sym = ids.filter(function (id) { return kind(id) === "symptom"; });
    var gyn = sym.some(function (id) { return feat[id].group === "gyn"; });
    var male = sym.some(function (id) { return feat[id].group === "male"; });
    var sex = gyn ? "F" : male ? "M" : (r() < 0.5 ? "F" : "M");
    var age = 22 + Math.floor(r() * 50);
    var yes = shuffle(sym, r).slice(0, Math.max(3, Math.round(sym.length * 0.7)));
    var others = kb.features.filter(function (f) { return kind(f.id) === "symptom" && ids.indexOf(f.id) === -1 && f.group !== "gyn" && f.group !== "male"; });
    yes.push(others[Math.floor(r() * others.length)].id);
    // Words that the red-flag screen stops on (chest pressure, bleeding) go to the yes/no questions only.
    var spoken = yes.filter(function (id) { return QUIET.indexOf(id) === -1; });
    var text = "יש לי " + spoken.slice(0, 3).map(function (id) { return words(feat[id]); }).join(", ") + ".";
    return {
      id: "random_" + seed, seed: seed, random: true, title: "תרחיש אקראי #" + seed, expect: [syn.id],
      patient: { age: age, sex: sex, pregnancy: sex === "F" && age <= 55 ? "no" : undefined },
      meds: "", text: text, yes: yes,
      tongue: ids.filter(function (id) { return kind(id) === "tongue"; }),
      pulse: ids.filter(function (id) { return kind(id) === "pulse"; })
    };
  }

  // Runs a case through the engine the way the patient would answer it. Returns the transcript
  // (for the chat) and the clinician's tongue and pulse; log(text, who) is called for each line.
  function run(E, state, c, log) {
    log = log || function () {};
    state.patient = { age: c.patient.age, sex: c.patient.sex };
    if (c.patient.pregnancy) state.patient.pregnancy = c.patient.pregnancy;
    if (c.meds) { E.ingestMedications(state, c.meds); log(c.meds, "pt"); }
    log(c.text, "pt");
    var r = E.ingestText(state, c.text, "chief_complaint");
    if (r.halted) return { halted: true, tongue: null, pulse: null };
    log(r.findings, "understood");
    var q, guard = 0;
    while ((q = E.nextQuestion(state)) && guard++ < 40) {
      var v = c.yes.indexOf(q.feature.id) !== -1 || (state.answers[q.feature.id] && state.answers[q.feature.id].value === true);
      log(q.feature.q_he, "sys");
      log(v ? "כן" : "לא", "pt");
      E.answerQuestion(state, q, v);
    }
    return { tongue: c.tongue.length ? c.tongue.slice() : null, pulse: c.pulse.length ? c.pulse.slice() : null };
  }

  // Where the expected patterns landed: the best rank among them (1-based, null if not scored).
  function rankOf(E, state, c) {
    var ranked = E.score(state).filter(function (x) { return x.score > 0; });
    var best = null;
    ranked.forEach(function (x, i) { if (best === null && c.expect.indexOf(x.syndrome.id) !== -1) best = { rank: i + 1, id: x.syndrome.id }; });
    return best;
  }

  var api = { CASES: CASES, random: random, run: run, rankOf: rankOf };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TCMDemoCases = api;
})(typeof window !== "undefined" ? window : this);
