import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "treatment"))

import build_treatment as bt  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return bt.build_data()


def test_liver_yang_rising_gets_the_who_method_and_lr3(data):
    l = data["links"]["SYN.LR.GAN_YANG_SHANG_KANG"]
    assert [data["methods"][m["i"]]["zh"] for m in l["m"]] == ["平肝潜阳"]
    assert l["p"][0]["id"] == "LR3"
    assert "subdues Liver yang" in [data["points"]["LR3"]["act"][i] for i in l["p"][0]["a"]]


def test_spleen_qi_deficiency_points_treat_the_spleen(data):
    ids = [p["id"] for p in data["links"]["SYN.SP.PI_QI_XU"]["p"]]
    assert {"SP3", "BL20"} <= set(ids)


def test_herb_suggestions_quote_bencao(data):
    l = data["links"]["SYN.LR.GAN_YANG_SHANG_KANG"]
    herb = l["h"][0]
    assert any("平肝" in data["herbs"][herb["id"]]["act"][i] for i in herb["a"])
    assert data["herbs"][herb["id"]]["src"].startswith("GUT-BENCAO-BEIYAO")


def test_no_gram_doses_anywhere(data):
    text = json.dumps(data, ensure_ascii=False)
    assert "dose_g" not in text and "dose_min_g" not in text
    for f in data["formulas"].values():
        assert set().union(*[set(c) for c in f["comp"]]) <= {"h", "d"}


def test_method_pieces_are_verb_object():
    assert bt.method_phrases("平肝潜阳") == ["平肝", "潜阳"]
    assert bt.method_phrases("温补脾阳") == []


def test_committed_treatment_kb_is_current(data):
    text = (ROOT / "app" / "interview" / "treatment_kb.js").read_text("utf-8")
    assert json.loads(text[text.index("=") + 1:].rstrip().rstrip(";")) == data


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_safety_check(tmp_path):
    script = tmp_path / "run.js"
    script.write_text(f"""
global.window = {{}};
require({json.dumps(str(ROOT / "app" / "interview" / "treatment_kb.js"))});
const {{ createTreatment }} = require({json.dumps(str(ROOT / "app" / "interview" / "treatment.js"))});
const T = createTreatment(window.TCM_TX);
const sugg = T.suggest(["SYN.LR.GAN_YANG_SHANG_KANG"], ["FT.HEADACHE"]);
const plan = T.newPlan(["SYN.LR.GAN_YANG_SHANG_KANG"], sugg, {{ pregnancy: "yes" }});
const startPoints = plan.points.map(p => p.id);
plan.herbs.push({{ id: "HERB.GAN_CAO", dose_g: 6 }}, {{ id: "HERB.DA_JI", dose_g: "" }}, {{ id: "HERB.DAN_SHEN", dose_g: 9 }});
plan.points.push({{ id: "SP6", moxa: false }});
const issues = T.checkSafety(plan, {{ pregnancy: "yes" }}, ["anticoagulant"]);
const pregSugg = T.suggest(["SYN.SP.PI_QI_XU"], []);
const pregPlan = T.newPlan(["SYN.SP.PI_QI_XU"], pregSugg, {{ pregnancy: "yes" }});
const banned = id => T.pregnancyRisk(id).length > 0;
console.log(JSON.stringify({{ startPoints, issues,
  bannedChosen: pregPlan.points.concat(pregPlan.shiatsu).filter(p => banned(p.id)).map(p => p.id),
  bannedSuggested: Object.keys(window.TCM_TX.points).filter(banned) }}));
""")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    rules = {i["rule"]: i["sev"] for i in out["issues"]}
    assert rules["SAFE.FAN.DA_JI.GAN_CAO"] == "red"          # 十八反 inside the prescription
    assert rules["SAFE.PREG.DA_JI"] == "red"                  # pregnancy contraindication
    assert rules["DRAFT.ANTICOAGULANT.BLOOD_MOVING"] == "red"  # 丹參 with an anticoagulant
    assert "DOSE.MISSING.HERB.DA_JI" in rules and "DOSE.MISSING.HERB.GAN_CAO" not in rules
    assert out["bannedSuggested"] and not out["bannedChosen"]   # with a reported pregnancy, points a pregnancy rule names start unselected


def test_every_shown_chinese_string_has_hebrew():
    import build_he
    data, missing = build_he.build()
    assert not missing, {c: v[:3] for c, v in missing.items()}
    assert data["平肝潜阳"] and data["太冲"]


def test_committed_he_dict_is_current():
    import build_he
    data, _ = build_he.build()
    text = (ROOT / "app" / "interview" / "he_dict.js").read_text("utf-8")
    assert json.loads(text[text.index("=") + 1:].rstrip().rstrip(";")) == data


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_i18n_templates_and_source_links(tmp_path):
    script = tmp_path / "run.js"
    script.write_text(f"""
global.window = {{}};
require({json.dumps(str(ROOT / "app" / "interview" / "he_dict.js"))});
require({json.dumps(str(ROOT / "app" / "interview" / "i18n.js"))});
const I = window.TCMI18n;
console.log(JSON.stringify({{
  fan: I.he("十八反: 甘草 反 大戟 (do not combine)"),
  zjdc: I.source("WS-ZJDC 卷九 考正穴法, line 59", "主上氣咳逆"),
  gut: I.source("GUT-SHANGHAN 條21", "脈促"),
  books: I.books("傷寒論 條21")
}}));
""")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    assert out["fan"].startswith("שמונה-עשר הניגודים") and "大戟" not in out["fan"]
    assert out["zjdc"]["url"].startswith("https://zh.wikisource.org/wiki/%E9%87%9D%E7%81%B8%E5%A4%A7%E6%88%90/%E5%8D%B7%E4%B9%9D#:~:text=")
    assert out["gut"]["url"].startswith("https://www.gutenberg.org/cache/epub/24272/")
    assert out["books"] == "שאנג האן לון סעיף 21"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_series_and_body_map(tmp_path):
    script = tmp_path / "run.js"
    script.write_text(f"""
global.window = {{}};
require({json.dumps(str(ROOT / "app" / "interview" / "treatment_kb.js"))});
require({json.dumps(str(ROOT / "app" / "interview" / "body_map.js"))});
const {{ createTreatment }} = require({json.dumps(str(ROOT / "app" / "interview" / "treatment.js"))});
const T = createTreatment(window.TCM_TX);
const F = ["FT.HEADACHE", "FT.DIZZY", "FT.INSOMNIA", "FT.TINNITUS"];
const sugg = T.suggest(["SYN.LR.GAN_YANG_SHANG_KANG"], F);
const plan = T.newPlan(["SYN.LR.GAN_YANG_SHANG_KANG"], sugg, {{ pregnancy: "yes" }});
const s7 = T.series(plan, sugg, F, 7, {{ pregnancy: "yes" }});
const s14 = T.series(plan, sugg, F, 14, {{ pregnancy: "yes" }});
const chosen = plan.points.map(p => p.id);
const extra = s14.flatMap(s => s.points).filter(id => chosen.indexOf(id) === -1);
const rules = id => window.TCM_TX.safety.filter(r => r.ids.indexOf(id) !== -1);
const places = Object.keys(window.TCM_TX.points).map(id => [id, window.TCMBodyMap.place(id)]);
console.log(JSON.stringify({{ k7: s7.map(s => s.kind), k14: s14.map(s => s.kind), focus: s7.filter(s => s.kind === "focus").map(s => s.finding),
  extraRules: extra.flatMap(id => rules(id).filter(r => r.cond === "pregnancy" || /NO_NEEDLE/.test(r.id)).map(r => r.id)),
  badPlaces: places.filter(([id, p]) => !p || p.x < 0 || p.x > 200 || p.y < 0 || p.y > 420).map(([id]) => id) }}));
""")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    assert len(out["k7"]) == 7 and out["k7"][0] == "root" and out["k7"][-1] == "review"
    assert len(out["k14"]) == 14 and out["k14"][6] == "midreview" and out["k14"][12] == "taper"
    assert set(out["focus"]) <= {"FT.HEADACHE", "FT.DIZZY", "FT.INSOMNIA", "FT.TINNITUS"} and out["focus"]
    assert out["extraRules"] == []      # added points never carry a pregnancy or no-needling rule
    assert out["badPlaces"] == []       # every point has a place on the schematic figures


def test_committed_points3d_is_current():
    pytest.importorskip("numpy")
    import build_points3d
    text = (ROOT / "app" / "interview" / "points3d.js").read_text("utf-8")
    committed = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))
    built = build_points3d.build()
    assert set(committed) == set(json.loads((ROOT / "app" / "interview" / "treatment_kb.js").read_text("utf-8").split("=", 1)[1].rstrip().rstrip(";"))["points"])
    assert committed == built


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_sample_cases_rank_their_patterns():
    script = ROOT / "tools" / "interview" / "eval_scenarios.js"
    out = json.loads(subprocess.run(["node", str(script), "40"], capture_output=True, text=True, check=True).stdout)
    cur = out["curated_summary"]
    # every curated case puts one of its expected patterns in the five shown; the red-flag case stops
    assert cur["top5"] == cur["n"] and cur["halt_missed"] == 0 and cur["halt_unexpected"] == 0
    assert out["random_summary"]["top5"] >= 0.9 * out["random_summary"]["n"]
