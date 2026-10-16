"""Build the data file for the Hebrew patient-interview prototype.

Reads the WHO 2022 patterns (kb/curation/syndromes.yaml) and the interview lexicon
(kb/lexicon/interview_features.yaml, interview_safety.yaml), derives pattern-feature links by
matching each feature's English phrases against the pattern text, and writes app/interview/kb.js.

Every derived link is a DRAFT with the placeholder weight from the lexicon `defaults`; the
clinician replaces these with real weights and essential flags later.

Usage:
    python3 tools/interview/build_interview.py                 # write app/interview/kb.js
    python3 tools/interview/build_interview.py --standalone F  # also write one self-contained HTML file
"""

import argparse
import json
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

    Sentences of the presentation that describe the tongue or pulse are moved to those texts,
    so 'pale' in 'the tongue is pale' never counts as a pale face.
    """
    symptom, tongue, pulse = [], [syn.get("tongue", "")], [syn.get("pulse", "")]
    for sentence in SENTENCE.split(syn.get("presentation", "") or ""):
        low = sentence.lower()
        if "tongue" in low:
            tongue.append(sentence)
        if "pulse" in low:
            pulse.append(sentence)
        if "tongue" not in low and "pulse" not in low:
            symptom.append(sentence)
    return " ".join(symptom), " ".join(t for t in tongue if t), " ".join(p for p in pulse if p)


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
        for p in f["en"]:
            re.compile(p)
        if f.get("kind", "symptom") == "symptom" and not f.get("q_he"):
            raise SystemExit(f"{f['id']}: symptom feature needs q_he")

    links = derive_links(syndromes, features)
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
            "status": syn.get("status", "draft"),
            "links": links[syn["syndrome_id"]],
        })
    return {
        "schema_version": "interview_kb.v1",
        "kb_version": config.get("kb_version", ""),
        "defaults": lex["defaults"],
        "groups": lex["groups"],
        "features": [{k: v for k, v in f.items() if k != "en"} for f in features],
        "safety": safety,
        "syndromes": out_syndromes,
    }


def write_js(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    path.write_text("// Generated by tools/interview/build_interview.py. Do not edit by hand.\n"
                    f"window.TCM_KB = {body};\n", encoding="utf-8")


def write_standalone(path):
    """Inline the page's local scripts into index.html so the file opens anywhere."""
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
    html = re.sub(r"<!doctype html>\s*|</?html[^>]*>\s*|</?head>\s*|</?body>\s*|<meta charset[^>]*>\s*|<meta name=\"viewport\"[^>]*>\s*",
                  "", html, flags=re.I)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--standalone", type=Path, help="also write a single self-contained HTML file here")
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


if __name__ == "__main__":
    sys.exit(main())
