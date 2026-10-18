"""Build the data file for the treatment-plan step of the interview prototype.

For every WHO 2022 pattern this derives DRAFT treatment suggestions, each with the source text it
came from, and writes app/interview/treatment_kb.js (window.TCM_TX):

  methods   WHO 2022 treatment methods (治法) whose definition says "It is indicated for ..." a
            pattern with the same words as this one (token overlap of the two English names)
  points    acupuncture points whose AcuAtlas actions treat the same organ and the same disorder
            ("subdues Liver yang" for Hyperactivity of liver yang), plus points whose AcuAtlas
            indications or Zhenjiu Dacheng 主 text list the pattern's findings
  herbs     Bencao Beiyao herbs whose actions name the method ("平肝", "補氣")
  evidence  PubMed articles on each herb's interactions with screened drug classes, liver and kidney
            toxicity and pregnancy (kb/staging/PUBMED, built by tools/ingest/pubmed.py)
  formulas  Shanghan Lun / Jingui Yaolue / Yifang Jijie formulas whose herbs carry those actions, Yifang
            Jijie formulas whose indications (治...) name the pattern's organ and disorder (with a bonus
            when the book's category, e.g. 補養之劑, treats that disorder), and whose clauses or
            indications describe the pattern's findings

The patient-specific part (re-ranking by the patient's own findings) and the safety check run in the
browser (app/interview/treatment.js) from the per-point and per-formula findings written here.

Nothing here is a clinical decision: every link is a draft for the clinician to approve or reject,
and no gram dose is ever produced (formulas carry only their classical doses, e.g. 三兩).

Usage:
    python3 tools/treatment/build_treatment.py
"""

import json
import math
import re
import sys
from pathlib import Path

import opencc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "interview"))
import build_interview as bi  # noqa: E402

KB = ROOT / "kb"
OUT = ROOT / "app" / "interview" / "treatment_kb.js"
T2S = opencc.OpenCC("t2s")

TOP_POINTS, TOP_HERBS, TOP_FORMULAS, TOP_METHODS = 10, 10, 5, 3

# ---- English concepts shared by pattern names, WHO method names and AcuAtlas point actions ----
ORGANS = {
    "LIVER": r"\bliver\b", "GB": r"gall ?bladder", "HEART": r"\bheart\b", "PC": r"pericardium",
    "SPLEEN": r"\bspleen\b", "STOMACH": r"\bstomach\b", "LUNG": r"\blungs?\b",
    "LI": r"large intestine|\bintestin", "SI": r"small intestine", "KIDNEY": r"\bkidneys?\b",
    "BLADDER": r"bladder", "SJ": r"sanjiao|three jiao|triple burner", "UTERUS": r"uterus|chong|\bren\b|menstrua",
}
SUBSTANCES = {"QI": r"\bqi\b", "BLOOD": r"\bblood\b", "YIN": r"\byin\b", "YANG": r"\byang\b",
              "ESSENCE": r"essence|marrow", "FLUID": r"fluids?\b"}
# Each disorder: words naming it in a pattern, and words in a point's action that treat it.
DISORDERS = {
    "HEAT": (r"heat|fire|\bhot\b|summer", r"clears?\b.*(heat|fire)|cools?|drains? fire|reduces? fire"),
    "COLD": (r"\bcold\b", r"warms?|dispels? cold|scatters? cold|dissipates? cold"),
    "WIND": (r"\bwind\b", r"wind"),
    "DAMP": (r"damp", r"damp"),
    "PHLEGM": (r"phlegm", r"phlegm"),
    "STASIS": (r"stasis", r"stasis|invigorates? blood|moves? blood|activates? blood"),
    "STAG": (r"stagna|constraint|depress", r"spreads?|moves? qi|regulates? qi|soothes?|frees? .*qi|unbinds?|stagna|constraint"),
    "DEF": (r"deficien|insufficien|weakness|depletion|sinking|insecur|collapse",
            r"tonif|strengthens?|nourish|supplement|supports?|benefits?|builds?|reinforces?|fortif|secures?|lifts?|raises?"),
    "HYPER": (r"hyperactiv|ascend|rising|upward|flaming|counterflow|rebellious",
              r"subdues?|descends?|anchors?|settles?|downbears?|rebellious|pacif|calms? .*liver"),
    "SPIRIT": (r"spirit|mind|shen|restless", r"calms? the (spirit|mind|shen)|settles? the (spirit|mind)|spirit"),
    "WATER": (r"water|fluid retention|oedema|edema", r"water|oedema|edema|urination|fluid"),
    "EXTERIOR": (r"exterior|defence|\bwei\b", r"exterior|defensive|releases?|surface"),
    "DRY": (r"dryness|\bdry\b", r"moisten|generates? fluid"),
    "FOOD": (r"food", r"food|digest"),
}


def concepts(text, role):
    """Concept set of an English phrase; role 'pattern' reads disorders from the noun, 'action' from the verb."""
    low = text.lower()
    out = {k for k, rx in ORGANS.items() if re.search(rx, low)}
    out |= {k for k, rx in SUBSTANCES.items() if re.search(rx, low)}
    idx = 0 if role == "pattern" else 1
    out |= {k for k, rxs in DISORDERS.items() if re.search(rxs[idx], low)}
    if "LI" in out and "SI" in out and "large" not in low:
        out.discard("LI")
    return out


ORGAN_KEYS, DISORDER_KEYS = set(ORGANS), set(DISORDERS)
CHANNEL_ORGAN = {"CH.LR": "LIVER", "CH.GB": "GB", "CH.HT": "HEART", "CH.PC": "PC", "CH.SP": "SPLEEN", "CH.ST": "STOMACH",
                 "CH.LU": "LUNG", "CH.LI": "LI", "CH.SI": "SI", "CH.KI": "KIDNEY", "CH.BL": "BLADDER", "CH.TE": "SJ"}


def concept_score(want, have):
    """How well an action clause (have) answers a pattern (want); 0 unless the disorder matches."""
    organs = want & have & ORGAN_KEYS
    disorders = want & have & DISORDER_KEYS
    subs = want & have - ORGAN_KEYS - DISORDER_KEYS
    if not disorders:
        return 0.0
    if want & ORGAN_KEYS and not organs:     # a Liver pattern needs a Liver action
        return 0.0
    return 1.5 * len(organs) + 1.0 * len(disorders) + 0.5 * len(subs)


# ---- treatment methods (WHO 2022, part "treatment") ----
STOP = set("pattern patterns conditions condition due to of the and in a an with or by both affecting into".split())


def stem(w):
    w = w.lower().strip(",.()")
    for suf in ("ness", "ing", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return {"channel": "meridian"}.get(w, w)


def tokens(s):
    return {stem(w) for w in re.split(r"[\s/,–-]+", s or "") if w and w.lower() not in STOP}


def load_methods():
    out = []
    with open(KB / "staging" / "WHO-ISTTCM-2022" / "terms.jsonl", encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            if t.get("category_en") != "Treatment methods":
                continue
            definition = re.sub(r"\s*3 Treatment principles/methods and therapies.*$", "", t.get("definition") or "")
            m = re.search(r"indicated for (.*?)(?:\.|$)", definition)
            if not m:
                continue
            out.append({"no": t["number"], "zh": t["term_zh"], "en": t["term_en"], "def": definition,
                        "_ind": tokens(m.group(1))})
    return out


def match_methods(syn, methods):
    want = tokens(syn["name_en"])
    if not want:
        return []
    scored = []
    for i, m in enumerate(methods):
        shared = want & m["_ind"]
        if not shared:
            continue
        score = len(shared) / len(want | m["_ind"])
        if score >= 0.4:
            scored.append((round(score, 2), i))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < 0.5:
        return []
    floor = max(0.5, scored[0][0] - 0.25)   # "Warm liver yang" must not ride along with "Soothe the liver and submerge yang"
    return [{"i": i, "s": s} for s, i in scored[:TOP_METHODS] if s >= floor]


# ---- Chinese action phrases for herbs ----
# A pattern's disorder implies the classical action that treats it; used with the WHO method name.
PATTERN_ACTIONS_ZH = [
    (r"气虚|气不足|气陷", ["补气", "益气"]), (r"血虚", ["补血", "养血"]), (r"阴虚|阴亏", ["滋阴", "养阴", "补阴"]),
    (r"阳虚|阳衰", ["补阳", "温阳", "助阳", "温中"]), (r"气滞|气郁|郁结", ["理气", "行气", "疏肝"]),
    (r"血瘀|瘀", ["活血", "行血", "破血", "散瘀"]), (r"痰", ["化痰", "消痰", "祛痰"]),
    (r"湿", ["燥湿", "利湿", "渗湿", "除湿"]), (r"热|火", ["清热", "泻火"]), (r"寒", ["散寒", "温中", "祛寒"]),
    (r"风", ["祛风", "散风", "息风"]), (r"阳上亢|阳亢", ["平肝", "潜阳"]), (r"食", ["消食"]),
    (r"水|饮", ["利水", "逐水", "行水"]), (r"燥", ["润燥", "生津"]), (r"表", ["解表", "发汗"]),
]


VERBS = set("补益滋养温清泻泄疏理行活化燥利渗祛散息熄平潜润生解发消安宁止固收敛涩降升宣开通健和调凉破逐镇")
OBJECTS = set("肝心脾肺肾胃胆肠气血阴阳湿痰热火寒风瘀水饮津燥表食滞神中经络")


ORGAN_ZH = "肝心脾肺肾胃胆"
ORGAN_VERBS = [(r"虚|不足|亏|衰", "补益养健"), (r"热|火", "清泻凉"), (r"寒|阳虚", "温"), (r"郁|滞", "疏"), (r"燥|阴虚", "润滋")]


def organ_phrases(name_zh):
    """Verb + organ phrases a pattern implies: 脾阳虚 -> 补脾, 益脾, 养脾, 健脾, 温脾."""
    out = []
    for organ in ORGAN_ZH:
        if organ not in name_zh:
            continue
        for rx, verbs in ORGAN_VERBS:
            if re.search(rx, name_zh):
                out += [v + organ for v in verbs]
    return out


def method_phrases(zh):
    """Two-character verb-object pieces of a method name: 平肝潜阳 -> 平肝, 潜阳.

    Pieces that are not a verb plus what it acts on (温补, 脾肾, 中气) say nothing on their own."""
    zh = re.sub(r"[（(].*?[)）]|法$", "", zh)
    pieces = [zh[i:i + 2] for i in range(0, len(zh) - 1, 2)]
    return [p for p in pieces if len(p) == 2 and p[0] in VERBS and p[1] in OBJECTS]


def herb_index(herbs):
    """{herb_id: [action phrases as printed]} from the opening of the Bencao Beiyao entry, commentary in （） removed.

    The `actions` field holds only the entry's first clause; the main actions (除心熱，平肝風) follow
    in the next sentences of the same entry, before the indications (治...). The phrases keep the
    edition's traditional characters so the page can quote and link them; match on `simplified()`."""
    out = {}
    for h in herbs:
        text = re.sub(r"（[^（）]*）", "", h.get("classical") or h.get("actions") or "")
        head = text.split("治", 1)[0] if text.find("治") > 8 else text
        head = "。".join(head.split("。")[:3])[:120]
        out[h["herb_id"]] = [p for p in re.split(r"[，。；、︰:]", head) if p]
    return out


def simplified(index):
    return {k: [T2S.convert(p) for p in parts] for k, parts in index.items()}


def match_herbs(phrases, herb_phrases, usage):
    """[(score, herb_id, [action part indices])]; phrases is {phrase: weight}."""
    scored = []
    for hid, parts in herb_phrases.items():
        hits, score = [], 0
        for ph, w in phrases.items():
            for i, part in enumerate(parts):
                if ph in part and i not in hits:
                    hits.append(i)
                    score += w
                    break
        if hits:
            scored.append((score, hid, hits))
    scored.sort(key=lambda x: (-x[0], -usage.get(x[1], 0), x[1]))
    return scored


# ---- findings in point and formula texts ----
def point_findings(points, features):
    """{point_id: [{f, ev, src}]}: findings the point's indications list (AcuAtlas English, ZJDC Chinese)."""
    symptom = [f for f in features if f.get("kind", "symptom") == "symptom"]
    out = {}
    for p in points:
        found = {}
        for f in symptom:
            ev = bi.find(f["en"], p.get("indications") or "")
            if ev:
                found[f["id"]] = {"f": f["id"], "ev": ev, "src": "ACUATLAS"}
        classical = p.get("classical") or ""
        main = classical[classical.find("主"):] if "主" in classical else ""
        for printed in re.split(r"[，。；、]", main):
            phrase = T2S.convert(printed)
            for f in symptom:
                if f["id"] in found or not f.get("zh"):
                    continue
                if bi.find_zh(f["zh"], phrase):
                    found[f["id"]] = {"f": f["id"], "ev": printed, "src": "WS-ZJDC"}
        out[p["point_id"]] = list(found.values())
    return out


CLAUSE_LINE = re.compile(r"^(傷寒論|金匱要略|醫方集解)\s*([^：:]+)[：:](.*)$")

# ---- Yifang Jijie: indications (治...) and category (補養之劑...) against the pattern ----
# Chinese concepts in a pattern name or an indication phrase (simplified characters), with the same
# keys as the English ones above so the two can be compared by concept_score.
ORGANS_ZH = {"LIVER": r"肝", "HEART": r"心(?!下)", "SPLEEN": r"脾|中气|中焦", "STOMACH": r"胃", "LUNG": r"肺",
             "KIDNEY": r"肾|命门|下元", "GB": r"胆", "LI": r"大肠|肠", "BLADDER": r"膀胱",
             "UTERUS": r"胞宫|冲任|经水|月经|经候|崩|带下|胎|妊娠|产"}
SUBSTANCES_ZH = {"QI": r"气", "BLOOD": r"血", "YIN": r"阴|水亏|肾水", "YANG": r"阳|命火|相火不足", "ESSENCE": r"精|髓",
                 "FLUID": r"津|液"}
DISORDERS_ZH = {"DEF": r"虚|不足|亏|损|衰|弱|羸|劳|怯|少气|不固", "HEAT": r"热|火|暑|温毒", "COLD": r"寒|冷",
                "WIND": r"风", "DAMP": r"湿", "PHLEGM": r"痰|饮(?!食)", "STASIS": r"瘀|蓄血|死血|恶血",
                "STAG": r"郁|滞|气结|痞|胀", "HYPER": r"亢|上升|上冲|上逆|上攻|上炎|眩|晕", "DRY": r"燥|枯",
                "FOOD": r"宿食|食积|伤食|饮食不消|积滞", "WATER": r"水肿|水气|浮肿|肿满", "EXTERIOR": r"表|外感"}
# The book's 21 categories and the disorders their formulas treat.
CATEGORY_DISORDERS = {"补养": {"DEF"}, "发表": {"EXTERIOR"}, "表里": {"EXTERIOR"}, "理气": {"STAG", "HYPER"},
                      "理血": {"STASIS", "BLOOD"}, "祛风": {"WIND"}, "祛寒": {"COLD"}, "清暑": {"HEAT"},
                      "利湿": {"DAMP", "WATER"}, "润燥": {"DRY"}, "泻火": {"HEAT"}, "除痰": {"PHLEGM"},
                      "消导": {"FOOD"}, "收涩": {"DEF"}}
IND_PIECE = re.compile(r"[，。；、]")
CATEGORY_BONUS = 0.75


def concepts_zh(text):
    return ({k for k, rx in ORGANS_ZH.items() if re.search(rx, text)}
            | {k for k, rx in SUBSTANCES_ZH.items() if re.search(rx, text)}
            | {k for k, rx in DISORDERS_ZH.items() if re.search(rx, text)})


def yifang_entries(formulas):
    """{formula_id: [(category, locator, [(printed piece, concepts)])]} from the 醫方集解 indications lines."""
    out = {}
    for fm in formulas:
        for line in (fm.get("indications") or "").splitlines():
            m = CLAUSE_LINE.match(line.strip())
            if not m or m.group(1) != "醫方集解":
                continue
            where, printed = m.group(2), m.group(3)
            pieces = [p for p in IND_PIECE.split(printed) if p]
            category = T2S.convert(where.split("之", 1)[0])
            out.setdefault(fm["formula_id"], []).append(
                (category, f"醫方集解 {where}", [(p, concepts_zh(T2S.convert(p))) for p in pieces]))
    return out


def contradicts(want, have):
    """A yang-deficiency pattern against 蒸熱 or 陰, a yin-deficiency one against 虛寒, heat against cold."""
    def lacks(k, other):
        return k in have and other not in have
    if "YANG" in want and "YIN" not in want and lacks("YIN", "YANG"):
        return True
    if "YIN" in want and "YANG" not in want and lacks("YANG", "YIN"):
        return True
    if {"YANG", "DEF"} <= want and lacks("HEAT", "COLD"):
        return True
    if {"YIN", "DEF"} <= want and lacks("COLD", "HEAT"):
        return True
    if "HEAT" in want and "COLD" not in want and lacks("COLD", "HEAT"):
        return True
    return "COLD" in want and "HEAT" not in want and lacks("HEAT", "COLD")


def indication_match(want, entries):
    """Best match of the pattern's concepts in a formula's indications: (score, quote, locator, category, organ matched).

    A piece, or two neighbouring pieces read together (治肝肾不足，真阴亏损), must name the pattern's
    disorder and, when the pattern has an organ, that organ; a piece that names no organ at all counts
    half. The category is returned when it treats the pattern's disorder and a piece matched."""
    best = (0.0, None, None, None, False)
    for category, where, pieces in entries:
        cat = category if CATEGORY_DISORDERS.get(category, set()) & want else None
        for i in range(len(pieces)):
            for span in (1, 2):
                window = pieces[i:i + span]
                if len(window) < span:
                    continue
                have = set().union(*(c for _, c in window))
                if contradicts(want, have):
                    continue
                s, organ = concept_score(want, have), True
                if not s and not (have & ORGAN_KEYS) and want & have & DISORDER_KEYS:
                    s, organ = 0.5 * concept_score(want - ORGAN_KEYS, have), False
                s = s / (1 + 0.25 * (span - 1))     # two pieces must earn their keep
                if s > best[0]:
                    best = (round(s, 2), "，".join(p for p, _ in window), where, cat, organ)
    return best


def formula_findings(formulas, features):
    """{formula_id: [{f, ev, c}]}: findings the formula's clauses describe, c = the clause locator."""
    out = {}
    for fm in formulas:
        found = {}
        for line in (fm.get("indications") or "").splitlines():
            m = CLAUSE_LINE.match(line.strip())
            if not m:
                continue
            book, where, printed = m.groups()
            # Same split on the printed and the simplified text, so each phrase keeps its printed form.
            originals = [x.strip() for x in bi.GB_SEGMENT.split(printed) if x.strip()]
            segments = bi.gb_segments({"findings_main": T2S.convert(printed)})
            if len(originals) != len(segments):
                originals = [s for _, s, _ in segments]
            for (kind, phrase, _), shown in zip(segments, originals):
                for f in features:
                    if f.get("kind", "symptom") != kind or f["id"] in found or not f.get("zh"):
                        continue
                    if bi.find_zh(f["zh"], phrase):
                        found[f["id"]] = {"f": f["id"], "ev": shown, "c": f"{book} {where}"}
        out[fm["formula_id"]] = list(found.values())
    return out


# ---- assembling ----
def clauses(text):
    return [c.strip() for c in re.split(r"[;.]", text or "") if c.strip()]


def first_sentence(text, limit=220):
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def build_data():
    interview = bi.build_data()
    lex = bi.load(KB / "lexicon" / "interview_features.yaml")
    features = lex["features"]
    syndromes = {s["syndrome_id"]: s for s in bi.load(KB / "curation" / "syndromes.yaml")}
    points = bi.load(KB / "curation" / "points.yaml")
    herbs = bi.load(KB / "curation" / "herbs.yaml")
    formulas = bi.load(KB / "curation" / "formulas.yaml")
    rules = bi.load(KB / "curation" / "safety_rules.yaml")
    methods = load_methods()

    herb_printed = herb_index(herbs)
    herb_phrases = simplified(herb_printed)
    herb_ids = {h["herb_id"] for h in herbs}
    p_find = point_findings(points, features)
    f_find = formula_findings(formulas, features)
    yf_entries = yifang_entries(formulas)
    point_clauses = {p["point_id"]: [(c, concepts(c, "action")) for c in clauses(p.get("actions"))] for p in points}

    usage = {}
    for fm in formulas:
        for c in fm.get("composition", []):
            usage[c.get("herb_id")] = usage.get(c.get("herb_id"), 0) + 1

    links = {}
    for syn in interview["syndromes"]:
        sid = syn["id"]
        raw = syndromes[sid]
        meth = match_methods(raw, methods)
        want = concepts(raw["name_en"], "pattern")
        for m in meth:
            want |= concepts(methods[m["i"]]["en"], "pattern") & ORGAN_KEYS
        organs = want & ORGAN_KEYS
        pattern_feats = {l["f"]: l.get("w", interview["defaults"]["weight"]) for l in syn["links"]}

        # points: an action that treats this organ and disorder; findings in the indications add to it
        by_action, by_findings = [], []
        for p in points:
            pid = p["point_id"]
            why, act = [], 0.0
            for i, (_, have) in enumerate(point_clauses[pid]):
                s = concept_score(want, have)
                if s:
                    act += s
                    why.append(i)
            shared = [x["f"] for x in p_find[pid] if x["f"] in pattern_feats]
            sym = min(2.0, 0.4 * sum(pattern_feats[f] for f in shared))
            if act:
                by_action.append((round(min(act, 6.0) + sym, 2), pid, why, shared))
            elif len(shared) >= 3 and (not organs or CHANNEL_ORGAN.get(p["channel_id"]) in organs):
                by_findings.append((round(sym, 2), pid, why, shared))
        by_action.sort(key=lambda x: (-x[0], x[1]))
        by_findings.sort(key=lambda x: (-x[0], x[1]))
        chosen = by_action[:TOP_POINTS]
        chosen += by_findings[:min(3, TOP_POINTS - len(chosen))]   # findings alone fill gaps only
        pts = [{"id": pid, "s": s, "a": why, "f": shared} for s, pid, why, shared in chosen]

        # herbs: actions named by the WHO methods (weight 2) or implied by the pattern's name (weight 1)
        phrases = {}
        for m in meth:
            for ph in method_phrases(methods[m["i"]]["zh"]):
                phrases[ph] = 2
        name_zh = raw.get("name_zh", "")
        for rx, acts in PATTERN_ACTIONS_ZH:
            if re.search(rx, name_zh):
                for ph in acts:
                    phrases.setdefault(ph, 1)
        for ph in organ_phrases(name_zh):
            phrases.setdefault(ph, 1.5)
        hscored = match_herbs(phrases, herb_phrases, usage)
        hs = [{"id": hid, "s": n, "a": hits} for n, hid, hits in hscored[:TOP_HERBS]]
        hscore = {hid: n for n, hid, _ in hscored[:3 * TOP_HERBS]}   # a formula counts only herbs near the top

        # formulas: carried by herbs with those actions; Yifang Jijie indications that name the pattern's
        # organ and disorder, and its category (補養之劑 for a deficiency), add to it; clauses describing
        # the findings multiply it
        want_zh = want | concepts_zh(T2S.convert(name_zh.removesuffix("证").removesuffix("證")))
        fscored = []
        for fm in formulas:
            fid = fm["formula_id"]
            comp = [c["herb_id"] for c in fm.get("composition", []) if c.get("herb_id") in herb_ids]
            carrying = [h for h in comp if h in hscore]
            herb_part = 0.0
            if comp and (len(carrying) >= 2 or carrying == comp):
                herb_part = sum(hscore[h] for h in carrying) / math.sqrt(len(comp))
            else:
                carrying = []
            ind, quote, where, cat, organ = indication_match(want_zh, yf_entries.get(fid, []))
            if not herb_part and not ind:
                continue
            if not (organ or herb_part):
                cat = None          # the category confirms a match; it does not make one
            shared = [x["f"] for x in f_find[fid] if x["f"] in pattern_feats]
            score = (herb_part + ind + (CATEGORY_BONUS if cat else 0)) * (1 + 0.15 * min(len(shared), 5))
            if score >= 1.5:
                link = {"h": carrying, "f": shared}
                if quote:
                    link["q"] = {"ev": quote, "c": where}
                if cat:
                    link["cat"] = where
                fscored.append((round(score, 2), fid, link))
        fscored.sort(key=lambda x: (-x[0], x[1]))
        fms = [{"id": fid, "s": s, **link} for s, fid, link in fscored[:TOP_FORMULAS]]

        links[sid] = {"m": meth, "p": pts, "h": hs, "fm": fms}

    used_methods = sorted({m["i"] for l in links.values() for m in l["m"]})
    remap = {old: new for new, old in enumerate(used_methods)}
    for l in links.values():
        for m in l["m"]:
            m["i"] = remap[m["i"]]

    # Every Han-classic formula stays selectable; a Yifang Jijie-only formula is written only when a pattern links it.
    linked = {f["id"] for l in links.values() for f in l["fm"]}
    shown_formulas = {fm["formula_id"] for fm in formulas
                      if fm["formula_id"] in linked or any(s["source_id"] != "WS-YFJJ" for s in fm.get("sources", []))}

    def anchor(row):
        """The words the source link of a Yifang Jijie composition opens at: the formula's first indication
        piece (治一切陽虛气弱), which, unlike its name, is not repeated in other formulas' commentary."""
        if not src(row, "composition").startswith("WS-YFJJ"):
            return {}
        entries = yf_entries.get(row["formula_id"])
        return {"anchor": entries[0][2][0][0]} if entries and entries[0][2] else {}

    def src(row, field):
        for s in row.get("sources", []):
            if s.get("field") == field:
                return f'{s["source_id"]} {s.get("locator", "")}'.strip()
        return ""

    return {
        "schema_version": "treatment_kb.v1",
        "kb_version": interview["kb_version"],
        "methods": [{k: methods[i][k] for k in ("no", "zh", "en", "def")} for i in used_methods],
        "points": {p["point_id"]: {
            "zh": p["name_zh"], "py": p["name_pinyin"], "en": p["name_en"], "ch": p["channel_id"],
            "loc": p.get("location", ""), "act": [c for c, _ in point_clauses[p["point_id"]]], "ind": p.get("indications", ""),
            "needle": p.get("needling_notes", ""), "caution": p.get("cautions", ""),
            "src": src(p, "actions"), "zjdc": src(p, "classical"), "find": p_find[p["point_id"]],
        } for p in points},
        "herbs": {h["herb_id"]: {
            "zh": h["name_zh"], "py": h["name_pinyin"], "nature": h.get("nature", ""), "flavour": h.get("flavour", ""),
            "channels": h.get("channels_entered", ""), "act": herb_printed[h["herb_id"]], "src": src(h, "actions"),
        } for h in herbs},
        "formulas": {fm["formula_id"]: {
            "zh": fm["name_zh"], "py": fm["name_pinyin"],
            "comp": [{"h": c.get("herb_id"), "d": c.get("dose_original", "")} for c in fm.get("composition", [])],
            "src": src(fm, "composition") or src(fm, "classical"), "ind_src": src(fm, "indications"),
            "find": f_find[fm["formula_id"]],
            **anchor(fm),
        } for fm in formulas if fm["formula_id"] in shown_formulas},
        "safety": [{"id": r["rule_id"], "cond": r["condition"], "ids": r["entity_ids"], "sev": r["severity"],
                    "note": r.get("note", ""), "src": src(r, "entity_ids"), "status": r.get("status", "draft")}
                   for r in rules],
        "links": links,
        "evidence": pubmed_evidence(),
    }


def pubmed_evidence(per_topic=3):
    """PubMed articles per herb and safety topic (kb/staging/PUBMED, from tools/ingest/pubmed.py), cut to
    what the safety panel shows: the hit count and the first few articles' title, year and journal."""
    path = KB / "staging" / "PUBMED" / "herb_evidence.json"
    if not path.exists():
        return {"topics": {}, "herbs": {}, "articles": {}}
    ev = json.loads(path.read_text(encoding="utf-8"))
    herbs = {hid: {t: [r["count"], r["pmids"][:per_topic]] for t, r in h["topics"].items()}
             for hid, h in ev["herbs"].items() if h["topics"]}
    used = {p for h in herbs.values() for _, pmids in h.values() for p in pmids}
    return {
        "retrieved": ev["retrieved"],
        "topics": {t: (v["constraint"] or "").lower() for t, v in ev["topics"].items()},
        "herbs": herbs,
        "articles": {p: [a["title"], a["year"], a["journal"], int("Review" in a["types"] or "Systematic Review" in a["types"])]
                     for p, a in ev["articles"].items() if p in used},
    }


def main(argv=None):
    data = build_data()
    OUT.write_text("// Generated by tools/treatment/build_treatment.py. Do not edit by hand.\n"
                   "window.TCM_TX = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    links = data["links"].values()
    print(f"{sum(1 for l in links if l['m'])} patterns with a WHO method, "
          f"{sum(1 for l in links if l['p'])} with points, {sum(1 for l in links if l['h'])} with herbs, "
          f"{sum(1 for l in links if l['fm'])} with formulas -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
