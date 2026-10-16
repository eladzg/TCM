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
