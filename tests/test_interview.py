import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "interview"))

import build_interview as bi  # noqa: E402

FEATURES = bi.load(ROOT / "kb" / "lexicon" / "interview_features.yaml")["features"]


def links_for(presentation, tongue="", pulse=""):
    syn = {"syndrome_id": "SYN.T.X", "presentation": presentation, "tongue": tongue, "pulse": pulse}
    return {l["f"] for l in bi.derive_links([syn], FEATURES)["SYN.T.X"]}


def test_spleen_qi_deficiency_links():
    found = links_for("Characterized by low food intake, abdominal distension that aggravates after eating food, "
                      "loose stools, and lassitude.", "The tongue is pale with a white coating.",
                      "The pulse is slack and weak.")
    assert {"FT.POOR_APPETITE", "FT.ABD_DIST", "FT.POSTMEAL_DIST", "FT.LOOSE_STOOL", "FT.FATIGUE",
            "TG.PALE", "TG.COAT_WHITE", "PL.WEAK", "PL.SLACK"} <= found


def test_negated_phrase_is_not_a_link():
    found = links_for("Characterized by aversion to cold, absence of thirst and absence of sweating.")
    assert "FT.THIRST" not in found
    assert {"FT.NO_THIRST", "FT.NO_SWEAT", "FT.AVERSION_COLD"} <= found


def test_tongue_sentence_does_not_count_as_face():
    found = links_for("Characterized by dizziness. The tongue is pale.")
    assert "FT.PALE_FACE" not in found
    assert "TG.PALE" in found


def test_tidal_fever_is_not_acute_fever():
    found = links_for("Characterized by feverish sensations in the palms, soles and chest, and tidal fever in the afternoon.")
    assert "FT.FEVER" not in found and "FT.FEELS_HOT" not in found
    assert {"FT.FIVE_PALM_HEAT", "FT.HOT_FLUSHES"} <= found


def gb_links_for(main, secondary=None):
    syn = {"syndrome_id": "SYN.T.X", "name_zh": "测试证"}
    gb = {"测试证": {"code": "9.9", "findings_main": main, "findings_secondary": secondary}}
    return {l["f"]: l for l in bi.derive_gb_links([syn], FEATURES, gb)["SYN.T.X"]["links"]}


def test_gb_findings_link_by_kind():
    found = gb_links_for("情志抑郁，喜太息，胸胁胀痛，或腹胀，纳呆，便溏不爽，舌苔白，脉弦或缓弱", "口苦")
    assert {"FT.LOW_MOOD", "FT.FLANK_PAIN", "FT.ABD_DIST", "FT.POOR_APPETITE", "FT.LOOSE_STOOL",
            "TG.COAT_WHITE", "PL.WIRY", "PL.SLACK", "PL.WEAK"} <= set(found)
    assert found["FT.BITTER_MOUTH"]["secondary"] and not found["FT.LOW_MOOD"]["secondary"]
    # 白 in the tongue coating is not a pale face, 弦 in the pulse is nothing on the tongue
    assert "FT.PALE_FACE" not in found and "TG.PALE" not in found


def test_gb_negated_findings():
    found = gb_links_for("恶寒，无汗，口不渴，舌质淡红，脉浮紧")
    assert "FT.THIRST" not in found and "FT.PROFUSE_SWEAT" not in found
    assert {"FT.NO_THIRST", "FT.NO_SWEAT", "FT.AVERSION_COLD", "PL.SUPERFICIAL", "PL.TIGHT"} <= set(found)
    assert "TG.PALE" not in found  # 淡红 is the normal tongue colour


def test_links_name_their_sources():
    data = bi.build_data()
    syn = next(s for s in data["syndromes"] if s["zh"] == "肝郁气滞证")
    src = {l["f"]: l["src"] for l in syn["links"]}
    assert src["PL.WIRY"] == ["WHO", "GB"]
    assert src["FT.POOR_APPETITE"] == ["GB"]
    assert syn["gb"] and syn["gbtext"]


def test_build_data_covers_most_patterns():
    data = bi.build_data()
    linked = [s for s in data["syndromes"] if len(s["links"]) >= 3]
    assert len(linked) > 350
    assert all(f.get("q_he") for f in data["features"] if f.get("kind", "symptom") == "symptom")
    assert data["defaults"]["weight"] == 1.0


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_engine_scenarios(tmp_path):
    bi.write_js(bi.build_data(), tmp_path / "kb.js")
    script = tmp_path / "run.js"
    script.write_text(f"""
global.window = {{}};
require({json.dumps(str(tmp_path / "kb.js"))});
const {{ createEngine }} = require({json.dumps(str(ROOT / "app" / "interview" / "engine.js"))});
const e = createEngine(window.TCM_KB);
function run(patient, text, truth, tongue, pulse) {{
  const s = e.newState(patient);
  const r = e.ingestText(s, text);
  let q, n = 0;
  while ((q = e.nextQuestion(s)) && n < 60) {{ e.answerQuestion(s, q, truth.includes(q.feature.id)); n++; }}
  e.setObjective(s, "tongue", tongue); e.setObjective(s, "pulse", pulse);
  return {{ extracted: r.findings, report: e.report(s, {{ report_id: "t", created_at: "t" }}), asked: n }};
}}
const out = {{}};
out.spleen = run({{ age: 60, sex: "M" }}, "אני עייף כל הזמן, אין לי תיאבון ויש לי נפיחות אחרי האוכל ושלשולים",
  ["FT.FATIGUE","FT.POOR_APPETITE","FT.ABD_DIST","FT.POSTMEAL_DIST","FT.LOOSE_STOOL","FT.PALE_FACE","FT.LOW_VOICE","FT.SOB"],
  ["TG.PALE","TG.COAT_WHITE","TG.ENLARGED"], ["PL.WEAK","PL.SLACK"]);
out.liver = run({{ age: 41, sex: "F", pregnancy: "unknown" }}, "יש לי כאבי ראש פועמים ברקות, אני עצבנית מאוד וקשה לי להירדם. אין לי צמא.",
  ["FT.HEADACHE","FT.HEADACHE_DISTENDING","FT.IRRITABLE","FT.INSOMNIA","FT.DIZZY","FT.TINNITUS","FT.RED_FACE","FT.RESTLESS"],
  ["TG.RED"], ["PL.WIRY"]);
const halted = e.newState({{}});
out.halt = e.ingestText(halted, "יש לי כאב בחזה עכשיו");
out.noHalt = e.ingestText(e.newState({{}}), "לא היה לי כאב בחזה");
out.sorry = e.extract("סליחה, אין לי צמא בכלל");
out.meds = e.newState({{}}); e.ingestMedications(out.meds, "אני לוקח קומדין");
console.log(JSON.stringify(out));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)

    spleen = out["spleen"]["report"]
    assert spleen["differential"][0]["syndrome_id"] == "SYN.SP.PI_QI_XU"
    assert spleen["status"] == "draft_for_clinician"
    assert spleen["eight_principles"]["deficiency_excess"]["value"] == "deficiency"

    liver = out["liver"]["report"]
    top3 = [d["syndrome_id"] for d in liver["differential"][:3]]
    assert any(i.startswith("SYN.LR.") for i in top3)
    assert any(f["code"] == "PREGNANCY_STATUS_UNKNOWN" for f in liver["flags"])
    assert all(d["confidence"] != "high" for d in liver["differential"])
    assert out["liver"]["asked"] <= 15 + 12

    assert out["halt"]["halted"] is True
    assert out["noHalt"]["halted"] is False
    sorry = {x["feature"]: x["value"] for x in out["sorry"]}
    assert "FT.PHLEGM" not in sorry          # "ליחה" inside "סליחה" is not phlegm
    assert sorry.get("FT.THIRST") is False   # "אין לי צמא" is a negative answer
    assert [f["type"] for f in out["meds"]["flags"]] == ["anticoagulant"]


def test_committed_kb_js_is_current(tmp_path):
    bi.write_js(bi.build_data(), tmp_path / "kb.js")
    assert (tmp_path / "kb.js").read_text(encoding="utf-8") == (ROOT / "app" / "interview" / "kb.js").read_text(encoding="utf-8"), \
        "run python3 tools/interview/build_interview.py"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_voice_flow(tmp_path):
    bi.write_js(bi.build_data(), tmp_path / "kb.js")
    script = tmp_path / "voice.js"
    script.write_text(f"""
global.window = {{}};
require({json.dumps(str(tmp_path / "kb.js"))});
const {{ createEngine }} = require({json.dumps(str(ROOT / "app" / "interview" / "engine.js"))});
const {{ createVoiceFlow }} = require({json.dumps(str(ROOT / "app" / "interview" / "voice_flow.js"))});
const e = createEngine(window.TCM_KB);
function session(turns) {{
  const s = e.newState({{}});
  const f = createVoiceFlow(e, window.TCM_KB, s);
  const said = turns.map(t => f.step(t));
  return {{ said, state: s, report: e.report(s, {{ report_id: "t", created_at: "t" }}) }};
}}
const out = {{}};
// A woman of 41: age, then sex, then pregnancy, red flags, meds, complaint, then yes/no answers.
const turns = [
  {{ patient_said: "ארבעים ואחת", answer: "other", age: 41 }},
  {{ patient_said: "אישה", answer: "other", sex: "F" }},
  {{ patient_said: "לא", answer: "no", pregnancy: "no" }},
  {{ patient_said: "לא, אף אחד", answer: "no" }},
  {{ patient_said: "אני לוקחת קומדין", answer: "other" }},
  {{ patient_said: "יש לי כאבי ראש פועמים ברקות ואני עצבנית מאוד", answer: "other" }},
];
for (let i = 0; i < 40; i++) turns.push({{ patient_said: "לא", answer: "no" }});
out.full = session(turns);
out.halt = session([
  {{ patient_said: "שלושים", answer: "other", age: 30, sex: "M" }},
  {{ patient_said: "כן, יש לי לחץ בחזה", answer: "yes", red_flags: "RF.CHEST_PAIN" }},
  {{ patient_said: "מה עכשיו?", answer: "other" }},
]);
out.freeHalt = session([
  {{ patient_said: "שלושים", answer: "other", age: 30, sex: "M" }},
  {{ patient_said: "לא", answer: "no" }},
  {{ patient_said: "אין", answer: "no" }},
  {{ patient_said: "אני כבר כמה ימים לא יכול לנשום", answer: "other" }},
]);
console.log(JSON.stringify(out));
""", encoding="utf-8")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)

    said = out["full"]["said"]
    assert [s["status"] for s in said[:6]] == ["ask"] * 6
    assert "היריון" in said[1]["say"]               # pregnancy asked for a woman of 41
    assert "בטיחות" in said[2]["say"]               # then the red-flag screen
    assert said[5]["phase"] == "screening"          # then the engine's own questions
    assert said[-1]["status"] == "done"
    rep = out["full"]["report"]
    assert rep["patient"]["pregnancy"] == "no"
    assert [f["type"] for f in out["full"]["state"]["flags"]] == ["anticoagulant"]
    assert any(f["feature_id"] == "FT.IRRITABLE" and f["value"] == "present" for f in rep["findings"])

    assert [s["status"] for s in out["halt"]["said"]] == ["ask", "halt", "halt"]
    assert out["halt"]["state"]["halted"] is True
    assert out["freeHalt"]["said"][-1]["status"] == "halt"


def test_committed_pages_copy_is_current(tmp_path):
    bi.write_standalone(tmp_path / "index.html", keep_document=True)
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == (ROOT / "docs" / "index.html").read_text(encoding="utf-8"), \
        "run python3 tools/interview/build_interview.py --page docs/index.html"
