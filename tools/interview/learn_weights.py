"""Estimate draft pattern-finding weights from TCM-SD clinical records, and test them.

For every pattern (WHO 2022, or GB/T 16751.2 where WHO has none) with at least MIN_RECORDS training
records, and every lexicon feature, counts how often the records of that pattern report the finding versus records of all other
patterns. The likelihood ratio LR = P(finding | pattern) / P(finding | other patterns) becomes the
link's draft weight, log2(LR) clipped to [0.1, 3]: a finding three times more common in the
pattern weighs about 1.6, one no more common than elsewhere weighs 0.1. Findings the text sources
do not link but the records clearly do (LR >= 2, seen in >= 10% and >= 20 of the pattern's
records) are added as TCM-SD links. Only these counts are written
(kb/staging/TCM-SD/link_stats.json), never the records.

These are statistics from one hospital dataset, not clinical judgements: the clinician reviews
them like every other draft link.

Usage:
    python3 tools/interview/learn_weights.py            # write the counts from the train split
    python3 tools/interview/learn_weights.py --eval     # also rank the test split's patterns
"""

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_interview as B  # noqa: E402
import tcmsd  # noqa: E402

STATS = B.KB / "staging" / "TCM-SD" / "link_stats.json"

SCORER = r"""
const fs = require("fs");
global.window = {};
eval(fs.readFileSync(process.argv[1], "utf8"));
const E = require(process.argv[2]).createEngine(window.TCM_KB);
const recs = JSON.parse(fs.readFileSync(0, "utf8"));
const seen = new Set(recs.map((r) => r.gold));
const ranks = recs.map((r) => {
  const st = E.newState({ age: 50, sex: r.sex });
  Object.keys(r.findings).forEach((f) => E.setAnswer(st, f, r.findings[f], "text"));
  const all = E.score(st);
  const rank = (list) => {
    const own = list.find((x) => x.syndrome.id === r.gold);
    if (!own || own.score === 0) return 999;
    return 1 + list.filter((x) => x.syndrome.id !== r.gold && x.score >= own.score).length;
  };
  return [rank(all), rank(all.filter((x) => seen.has(x.syndrome.id)))];
});
process.stdout.write(JSON.stringify(ranks));
"""


def count(records):
    per_pattern = collections.Counter(r["gold"] for r in records)
    yes = collections.defaultdict(collections.Counter)
    for r in records:
        for f, v in r["findings"].items():
            if v:
                yes[r["gold"]][f] += 1
    return {"records": len(records), "patterns": dict(per_pattern),
            "yes": {s: dict(c) for s, c in yes.items()}}


def evaluate(records, kb_js=B.APP / "kb.js"):
    res = subprocess.run(["node", "-e", SCORER, str(kb_js), str(B.APP / "engine.js")],
                         input=json.dumps(records), capture_output=True, text=True, check=True)
    ranks = json.loads(res.stdout)
    gb_only = {s["syndrome_id"] for s in B.load(B.KB / "curation" / "syndromes.yaml") if B.gb_code(s)}
    kb = json.loads(kb_js.read_text("utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    pool = sum(1 for s in kb["syndromes"] if len(s["links"]) >= 3)

    def top(k, i, sel):
        return sum(1 for r in sel if r[i] <= k) / max(1, len(sel)) * 100

    groups = [("all", ranks), ("WHO pattern", [r for r, x in zip(ranks, records) if x["gold"] not in gb_only]),
              ("GB-only pattern", [r for r, x in zip(ranks, records) if x["gold"] in gb_only])]
    for name, sel in groups:
        if not sel:
            continue
        print(f" {name} ({len(sel)} records):")
        for i, label in ((0, f"all {pool} candidate patterns"), (1, "patterns seen in the test records")):
            print(f"  among {label}: top1 {top(1, i, sel):.1f}%  top3 {top(3, i, sel):.1f}%  top10 {top(10, i, sel):.1f}%")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", action="store_true", help="rank the test split with app/interview/kb.js")
    args = ap.parse_args(argv)
    features = B.load(B.KB / "lexicon" / "interview_features.yaml")["features"]
    index = tcmsd.who_index()
    train = tcmsd.prepared("train", features, index)
    stats = count(train)
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    print(f"{len(train)} training records, {len(stats['patterns'])} patterns -> {STATS.relative_to(B.ROOT)}")
    if args.eval:
        test = tcmsd.prepared("test", features, index)
        print(f"{len(test)} test records:")
        evaluate(test)


if __name__ == "__main__":
    main()
