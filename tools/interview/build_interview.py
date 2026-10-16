"""Build the data file for the Hebrew patient-interview prototype.

Reads the WHO 2022 patterns (kb/curation/syndromes.yaml) and the interview lexicon
(kb/lexicon/interview_features.yaml, interview_safety.yaml), derives pattern-feature links by
matching each feature's English phrases against the WHO pattern text and its Chinese phrases
against the findings GB/T 16751.2 lists for the same pattern (kb/staging/GBT-16751-2, matched by
Chinese name), and writes app/interview/kb.js. Each link names the sources that support it.
Where TCM-SD clinical records give enough data (kb/staging/TCM-SD/link_stats.json, written by
learn_weights.py), links get a draft weight from how much more often the pattern's records report
the finding, and findings the records clearly tie to the pattern are added as TCM-SD links.

Every derived link is a DRAFT with the placeholder weight from the lexicon `defaults`; the
clinician replaces these with real weights and essential flags later.

Usage:
    python3 tools/interview/build_interview.py                 # write app/interview/kb.js
    python3 tools/interview/build_interview.py --standalone F  # also write one self-contained HTML file
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb"
APP = ROOT / "app" / "interview"

NEGATION = re.compile(r"(absence of|\bno|without|lack of|\bnot|absent)\s+(?:[\w/-]+[ ,]+){0,2}$", re.I)
NEGATED_TERM = re.compile(r"(absence of|no|without|lack of|not)\b", re.I)  # the feature itself is a negative finding
SENTENCE =re.compile(r"(?<=[.;])\s+")


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_texts(syn):
    """Return (symptom text, tongue text, pulse text) for one pattern.

    The WHO parser sometimes files a whole presentation under `tongue` or `pulse`, so the three
    fields are pooled and re-split by sentence. Sentences about the tongue or pulse go to those
    texts and stay out of the symptom text, so 'pale' in 'the tongue is pale' never counts as a
    pale face, unless the sentence also lists other findings ("Characterized by fever, ... and
    mouth/tongue ulcerations").
    """
    sentences = []
    for field in ("presentation", "tongue", "pulse"):
        for sentence in SENTENCE.split(syn.get(field, "") or ""):
            if sentence.strip() and sentence not in sentences:
                sentences.append(sentence)
    symptom, tongue, pulse = [], [], []
    for sentence in sentences:
        low = sentence.lower()
        if "tongue" in low:
            tongue.append(sentence)
        if "pulse" in low:
            pulse.append(sentence)
        if ("tongue" not in low and "pulse" not in low) or low.startswith("characterized by"):
            symptom.append(sentence)
    return " ".join(symptom), " ".join(tongue), " ".join(pulse)


def find(patterns, text):
    """First non-negated match of any pattern in text, as a short evidence snippet, or None."""
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            negative_term = NEGATED_TERM.match(m.group(0))
            if not negative_term and NEGATION.search(text[max(0, m.start() - 40):m.start()]):
                continue
            start = max(0, text.rfind(",", 0, m.start()) + 1, text.rfind(".", 0, m.start()) + 1)
            end_candidates = [i for i in (text.find(",", m.end()), text.find(".", m.end())) if i != -1]
            end = min(end_candidates) if end_candidates else len(text)
            return text[start:end].strip()
    return None


def derive_links(syndromes, features):
    links = {}
    for syn in syndromes:
        texts = dict(zip(("symptom", "tongue", "pulse"), split_texts(syn)))
        found = []
        for feat in features:
            kind = feat.get("kind", "symptom")
            snippet = find(feat["en"], texts[kind])
            if snippet:
                found.append({"f": feat["id"], "ev": snippet})
        links[syn["syndrome_id"]] = found
    return links


GB_STAGING = KB / "staging" / "GBT-16751-2" / "syndromes.jsonl"
GB_SEGMENT = re.compile(r"[，、；;,]")
ZH_NEGATION = "不无未没"
PULSE_ONLY = re.compile(r"^(或|且|而)?[浮沉伏数疾促迟缓弱无力虚微有实洪大细滑弦涩紧濡软长短结代动芤革牢散]+$")


def load_gb():
    """GB/T 16751.2 entries by Chinese name and synonym, or {} when the source was not ingested."""
    if not GB_STAGING.exists():
        return {}
    index = {}
    with open(GB_STAGING, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            for name in [rec["name_zh"]] + rec["synonyms_zh"]:
                index.setdefault(name, rec)
    return index


def gb_segments(rec):
    """The GB findings of one pattern as (kind, phrase, secondary) triples.

    Tongue phrases mention 舌 or 苔 and pulse phrases 脉; a phrase right after one of them that
    only continues it ("脉沉弦，或浮大无力", "舌质淡，边有齿痕") keeps its kind.
    """
    out = []
    for secondary, text in ((False, rec.get("findings_main")), (True, rec.get("findings_secondary"))):
        kind = "symptom"
        for phrase in GB_SEGMENT.split(text or ""):
            phrase = phrase.strip()
            if not phrase:
                continue
            if "脉" in phrase:
                kind = "pulse"
            elif "舌" in phrase or "苔" in phrase:
                kind = "tongue"
            elif kind == "pulse" and PULSE_ONLY.match(phrase):
                pass
            elif kind == "tongue" and re.match(r"^(或)?(边|尖|有|少津|胖|嫩|裂)", phrase):
                pass
            else:
                kind = "symptom"
            out.append((kind, phrase, secondary))
    return out


def find_zh(patterns, phrase):
    for pattern in patterns:
        for m in re.finditer(pattern, phrase):
            if m.start() > 0 and phrase[m.start() - 1] in ZH_NEGATION and not re.search(f"[{ZH_NEGATION}]", pattern):
                continue
            return True
    return False


def derive_gb_links(syndromes, features, gb):
    """{syndrome_id: [{f, ev, secondary}]} from the GB findings of the pattern with the same name."""
    links = {}
    for syn in syndromes:
        rec = gb.get(syn.get("name_zh", ""))
        if not rec or not rec.get("findings_main"):
            continue
        found = {}
        for kind, phrase, secondary in gb_segments(rec):
            for feat in features:
                if feat.get("kind", "symptom") != kind or feat["id"] in found or not feat.get("zh"):
                    continue
                if find_zh(feat["zh"], phrase):
                    found[feat["id"]] = {"f": feat["id"], "ev": phrase, "secondary": secondary}
        text = rec["findings_main"] + ("；伴见" + rec["findings_secondary"] if rec.get("findings_secondary") else "")
        links[syn["syndrome_id"]] = {"code": rec["code"], "text": text, "links": list(found.values())}
    return links


def merge_links(who_links, gb_links):
    """One link per feature, listing every source that supports it with its evidence."""
    merged = {}
    for sid, found in who_links.items():
        out = {l["f"]: {"f": l["f"], "ev": l["ev"], "src": ["WHO"]} for l in found}
        for l in gb_links.get(sid, {}).get("links", []):
            if l["f"] in out:
                out[l["f"]]["src"].append("GB")
                out[l["f"]]["ev_zh"] = l["ev"]
            else:
                out[l["f"]] = {"f": l["f"], "ev": l["ev"], "src": ["GB"]}
            if l["secondary"]:
                out[l["f"]]["gb_secondary"] = True
        merged[sid] = list(out.values())
    return merged


SD_STATS = KB / "staging" / "TCM-SD" / "link_stats.json"
SD_MIN_RECORDS = 30        # patterns with fewer training records keep the placeholder weight
SD_ADD_LR, SD_ADD_SHARE, SD_ADD_COUNT = 2.0, 0.10, 20


def apply_record_stats(links, features):
    """Draft weights and extra links from TCM-SD counts; a no-op when the counts are missing."""
    if not SD_STATS.exists():
        return
    stats = json.loads(SD_STATS.read_text("utf-8"))
    total = stats["records"]
    all_yes = {}
    for counts in stats["yes"].values():
        for f, c in counts.items():
            all_yes[f] = all_yes.get(f, 0) + c

    def ratio(sid, f):
        n, k = stats["patterns"][sid], stats["yes"].get(sid, {}).get(f, 0)
        p_in = (k + 1) / (n + 2)
        p_out = (all_yes.get(f, 0) - k + 1) / (total - n + 2)
        return p_in / p_out, k, n

    for sid, found in links.items():
        if stats["patterns"].get(sid, 0) < SD_MIN_RECORDS:
            continue
        have = {l["f"] for l in found}
        for l in found:
            lr, k, n = ratio(sid, l["f"])
            l["w"] = round(min(3.0, max(0.1, math.log2(lr))), 2)
            l["sd"] = f"{k}/{n}"
        for feat in features:
            if feat["id"] in have:
                continue
            lr, k, n = ratio(sid, feat["id"])
            if lr >= SD_ADD_LR and k >= SD_ADD_COUNT and k / n >= SD_ADD_SHARE:
                found.append({"f": feat["id"], "ev": f"reported in {k} of {n} TCM-SD records of this pattern",
                              "src": ["TCM-SD"], "w": round(min(3.0, math.log2(lr)), 2), "sd": f"{k}/{n}"})


def locator(syn):
    for src in syn.get("sources", []):
        if src.get("field") == "presentation":
            return f'{src["source_id"]} {src["locator"]}'
    return ""


def build_data():
    syndromes = load(KB / "curation" / "syndromes.yaml")
    lex = load(KB / "lexicon" / "interview_features.yaml")
    safety = load(KB / "lexicon" / "interview_safety.yaml")
    config = load(KB / "config.yaml")
    features = lex["features"]
    ids = [f["id"] for f in features]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"duplicate feature ids: {sorted(dupes)}")
    for f in features:
        for p in f["en"] + f.get("zh", []):
            re.compile(p)
        if f.get("kind", "symptom") == "symptom" and not f.get("q_he"):
            raise SystemExit(f"{f['id']}: symptom feature needs q_he")

    who_links = derive_links(syndromes, features)
    gb_links = derive_gb_links(syndromes, features, load_gb())
    links = merge_links(who_links, gb_links)
    apply_record_stats(links, features)
    out_syndromes = []
    for syn in syndromes:
        out_syndromes.append({
            "id": syn["syndrome_id"],
            "en": syn["name_en"],
            "zh": syn.get("name_zh", ""),
            "py": syn.get("name_pinyin", ""),
            "he": syn.get("name_he"),
            "cat": syn.get("category", ""),
            "text": syn.get("presentation", ""),
            "tongue": syn.get("tongue", ""),
            "pulse": syn.get("pulse", ""),
            "tp": syn.get("treatment_principle"),
            "src": locator(syn),
            "gb": gb_links.get(syn["syndrome_id"], {}).get("code"),
            "gbtext": gb_links.get(syn["syndrome_id"], {}).get("text"),
            "status": syn.get("status", "draft"),
            "links": links[syn["syndrome_id"]],
        })
    return {
        "schema_version": "interview_kb.v1",
        "kb_version": config.get("kb_version", ""),
        "defaults": lex["defaults"],
        "groups": lex["groups"],
        "features": [{k: v for k, v in f.items() if k not in ("en", "zh")} for f in features],
        "safety": safety,
        "syndromes": out_syndromes,
    }


def write_js(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text("// Generated by tools/interview/build_interview.py. Do not edit by hand.\n"
                    f"window.TCM_KB = {body};\n", encoding="utf-8")


def write_standalone(path, keep_document=False):
    """Inline the page's local scripts into index.html so the file opens anywhere.

    By default the document skeleton is dropped for the artifact host; keep_document keeps it, for
    a file opened directly or served from GitHub Pages."""
    html = (APP / "index.html").read_text(encoding="utf-8")
    scripts = [("kb.js", ""), ("engine.js", ""), ("app.js", ""), ("voice_config.js", ""),
               ("voice_flow.js", ""), ("voice_ui.js", ' type="module"')]
    for name, attrs in scripts:
        tag = f'<script{attrs} src="{name}"></script>'
        if tag not in html:
            raise SystemExit(f"index.html has no {tag}")
        code = (APP / name).read_text(encoding="utf-8").replace("</script", "<\\/script")
        html = html.replace(tag, f"<script{attrs}>\n{code}\n</script>")
    # The artifact host wraps the page in its own document skeleton, so drop ours.
    if not keep_document:
        html = re.sub(r"<!doctype html>\s*|</?html[^>]*>\s*|</?head>\s*|</?body>\s*|<meta charset[^>]*>\s*|<meta name=\"viewport\"[^>]*>\s*",
                      "", html, flags=re.I)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--standalone", type=Path, help="also write a single self-contained HTML file here")
    ap.add_argument("--page", type=Path, help="also write a self-contained HTML document here (docs/index.html for GitHub Pages)")
    args = ap.parse_args(argv)
    data = build_data()
    write_js(data, APP / "kb.js")
    linked = sum(1 for s in data["syndromes"] if s["links"])
    total = sum(len(s["links"]) for s in data["syndromes"])
    print(f"{len(data['features'])} features, {linked}/{len(data['syndromes'])} patterns linked, "
          f"{total} draft links -> {APP / 'kb.js'}")
    if args.standalone:
        write_standalone(args.standalone)
        print(f"standalone -> {args.standalone}")
    if args.page:
        write_standalone(args.page, keep_document=True)
        print(f"page -> {args.page}")


if __name__ == "__main__":
    sys.exit(main())
