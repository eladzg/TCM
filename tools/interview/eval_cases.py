"""Measure pattern matching on real, expert-labelled cases (TCM-BEST4SDT, 300 Chinese case narratives).

Each narrative is cut into phrases and matched with the lexicon's Chinese terms (`zh`), the same
way the build reads GB/T 16751.2. The findings found count as "yes" answers (nothing is denied, no
questions are asked) and the interview engine ranks the WHO patterns from app/interview/kb.js.
The expert's pattern is mapped to WHO by Chinese name, directly or through GB/T 16751.2 synonyms;
cases whose pattern has no WHO counterpart are skipped.

Reported: how often the expert's pattern ranks 1st / in the top 5 / top 10 of all patterns, and
how often it scores highest among the case's own multiple-choice options that exist in WHO.
This measures the knowledge base, not the interview: real patients also answer questions.

Usage:
    python3 tools/interview/eval_cases.py [path/to/kb.js ...]
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_interview as B  # noqa: E402

CASES = "TCM-BEST4SDT"
PHRASE = re.compile(r"[，。；;,.、！？!?\s]+")

SCORER = r"""
const fs = require("fs");
global.window = {};
eval(fs.readFileSync(process.argv[1], "utf8"));
const kb = window.TCM_KB;
const E = require(process.argv[2]).createEngine(kb);
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
const out = cases.map((c) => {
  const st = E.newState({ age: 40, sex: c.sex });
  c.findings.forEach((f) => E.setAnswer(st, f, true, "text"));
  const ranked = E.score(st);
  const score = {};
  ranked.forEach((r) => { score[r.syndrome.id] = r.score; });
  return { score: c.targets.map((t) => score[t] === undefined ? null : score[t]),
           all: ranked.map((r) => r.score) };
});
process.stdout.write(JSON.stringify(out));
"""


def phrases(text):
    """Phrases with their kind; a phrase is tongue or pulse if it mentions them (舌苔 / 脉)."""
    out = []
    for p in PHRASE.split(text):
        if not p:
            continue
        kind = "pulse" if "脉" in p else "tongue" if ("舌" in p or "苔" in p) else "symptom"
        out.append((kind, p))
    return out


def extract(text, features):
    found = []
    for kind, p in phrases(text):
        for f in features:
            if f.get("kind", "symptom") == kind and f.get("zh") and f["id"] not in found and B.find_zh(f["zh"], p):
                found.append(f["id"])
    return found


def who_index(syndromes, gb):
    """Chinese name (pattern name or any GB synonym of the same GB entry) -> syndrome id.

    WHO names come first; a GB pattern WHO does not list never takes over a name a WHO pattern uses."""
    index = {}
    for s in syndromes:
        if B.gb_code(s):
            index.setdefault(s["name_zh"], s["syndrome_id"])
        else:
            index[s["name_zh"]] = s["syndrome_id"]
        rec = B.gb_record(s, gb)
        if rec:
            for name in [rec["name_zh"]] + rec["synonyms_zh"]:
                index.setdefault(name, s["syndrome_id"])
    return index


def load_cases():
    path = next(p for p, _ in B_latest(CASES) if p.suffix == ".json")
    return json.loads(path.read_text("utf-8"))


def B_latest(source_id):
    sys.path.insert(0, str(B.ROOT / "tools" / "ingest" / "classics"))
    from common import latest_raw_files
    return latest_raw_files(source_id)


def prepare():
    syndromes = B.load(B.KB / "curation" / "syndromes.yaml")
    features = B.load(B.KB / "lexicon" / "interview_features.yaml")["features"]
    index = who_index(syndromes, B.load_gb())
    prepared = []
    for case in load_cases():
        out = dict(line.split("：", 1) for line in case["output"] if "：" in line)
        gold = index.get(out.get("证型", "").strip())
        if not gold:
            continue
        options = [o.split(":", 1)[1].strip() for o in out.get("证型选项", "").split(";") if ":" in o]
        option_ids = [index[o] for o in options if o in index and index[o] != gold]
        sex = "F" if re.search(r"女|妇|妊娠|月经|经期", case["instruction"]) else "M"
        prepared.append({"id": case["id"], "sex": sex, "findings": extract(case["instruction"], features),
                         "targets": [gold] + option_ids})
    return prepared


def evaluate(kb_js, prepared):
    engine = str(B.APP / "engine.js")
    res = subprocess.run(["node", "-e", SCORER, str(kb_js), engine], input=json.dumps(prepared),
                         capture_output=True, text=True, check=True)
    results = json.loads(res.stdout)
    n = len(results)
    ranks, mc_total, mc_right = [], 0, 0
    for r in results:
        own = r["score"][0]
        if own is None or own == 0:
            ranks.append(None)
        else:
            ranks.append(1 + sum(1 for s in r["all"] if s >= own) - 1)
        others = [s for s in r["score"][1:] if s is not None]
        if others and own is not None:
            mc_total += 1
            mc_right += own > max(others)

    def top(k):
        return sum(1 for x in ranks if x is not None and x <= k) / n * 100

    return {"cases": n, "top1": top(1), "top5": top(5), "top10": top(10),
            "choice_cases": mc_total, "choice": mc_right / max(1, mc_total) * 100}


def main(argv=None):
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])] or [B.APP / "kb.js"]
    prepared = prepare()
    avg = sum(len(c["findings"]) for c in prepared) / max(1, len(prepared))
    print(f"{len(prepared)} cases with a WHO pattern, {avg:.1f} findings extracted per case")
    for path in paths:
        m = evaluate(path, prepared)
        print(f"{path.name}: top1 {m['top1']:.1f}%  top5 {m['top5']:.1f}%  top10 {m['top10']:.1f}%  "
              f"best of the case's options {m['choice']:.1f}% ({m['choice_cases']} cases)")


if __name__ == "__main__":
    main()
