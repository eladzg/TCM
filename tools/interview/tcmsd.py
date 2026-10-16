"""Read TCM-SD clinical records (Ren et al., CCL 2022) into interview findings.

Each record's history (description) and four-examination summary (detection) are cut into
phrases and matched with the lexicon's Chinese terms. A phrase opening with a negation (无, 不,
未, 否认, 没有) records the findings it names as absent ("无发热，无心慌胸闷"); a few routine
normal phrases (纳可, 眠可, 二便调) do the same. When the record describes the tongue or pulse,
every tongue or pulse feature it does not name counts as absent, as when the clinician fills in
the tongue and pulse section.

The expert's pattern (norm_syndrome) is mapped to a WHO pattern by Chinese name, directly or
through GB/T 16751.2 synonyms; records whose pattern has no WHO counterpart are skipped.
"""

import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest" / "classics"))

import build_interview as B  # noqa: E402
from common import latest_raw_files  # noqa: E402

SOURCE = "TCM-SD"
CLAUSE = re.compile(r"[，。；;,.！？!?：:\s]+")
NEGATED = re.compile(r"^(无|不|未|否认|没有|未见|未诉)")
NEGATION_INSIDE = re.compile(r"(无|未|否认|没有)")
NORMAL = {  # routine "normal" phrases -> features they rule out
    "纳可": ["FT.POOR_APPETITE"], "纳食可": ["FT.POOR_APPETITE"], "纳眠可": ["FT.POOR_APPETITE", "FT.INSOMNIA"],
    "眠可": ["FT.INSOMNIA"], "寐安": ["FT.INSOMNIA"], "夜寐安": ["FT.INSOMNIA"], "睡眠可": ["FT.INSOMNIA"],
    "二便调": ["FT.LOOSE_STOOL", "FT.CONSTIPATION"], "二便正常": ["FT.LOOSE_STOOL", "FT.CONSTIPATION"],
    "大便正常": ["FT.LOOSE_STOOL", "FT.CONSTIPATION"], "小便正常": ["FT.YELLOW_URINE", "FT.FREQ_URINE"],
}


def phrase_kind(p):
    return "pulse" if "脉" in p else "tongue" if ("舌" in p or "苔" in p) else "symptom"


def extract(text, features):
    """{feature_id: True|False} found in one record's text.

    A clause opening with a negation negates every item in it ("无发热、黄疸"); inside other
    clauses a finding is negated when 无/未/否认/没有 comes before it ("近期无明显消瘦").
    """
    found = {}
    seen_kind = set()
    for clause in CLAUSE.split(text):
        if not clause:
            continue
        for normal, ids in NORMAL.items():
            if clause.startswith(normal):
                for fid in ids:
                    found.setdefault(fid, False)
        kind = phrase_kind(clause)
        clause_negated = kind == "symptom" and bool(NEGATED.match(clause))
        body = NEGATED.sub("", clause) if clause_negated else clause
        for f in features:
            if f.get("kind", "symptom") != kind or not f.get("zh"):
                continue
            hit = first_zh(compiled(f), body)
            if hit is None:
                continue
            negated = clause_negated or (kind == "symptom" and bool(NEGATION_INSIDE.search(body[:hit])))
            if negated:
                found.setdefault(f["id"], False)
            else:
                found[f["id"]] = True
                seen_kind.add(kind)
    for f in features:
        if f.get("kind") in seen_kind and f["id"] not in found:
            found[f["id"]] = False
    return found


_COMPILED = {}


def compiled(f):
    if f["id"] not in _COMPILED:
        _COMPILED[f["id"]] = [(re.compile(p), bool(re.search(f"[{B.ZH_NEGATION}]", p))) for p in f["zh"]]
    return _COMPILED[f["id"]]


def first_zh(patterns, text):
    """Start of the first match of any pattern, ignoring matches right after 不/无/未/没 unless
    the pattern itself is a negative finding, or None."""
    best = None
    for pattern, negative_term in patterns:
        for m in pattern.finditer(text):
            if m.start() > 0 and text[m.start() - 1] in B.ZH_NEGATION and not negative_term:
                continue
            if best is None or m.start() < best:
                best = m.start()
            break
    return best


def raw_records():
    """{"train", "dev", "test"} -> list of records, from the newest raw download."""
    files = {p.name: p for p, _ in latest_raw_files(SOURCE)}
    z = zipfile.ZipFile(files["TCM_SD_train_dev.zip"])
    out = {}
    for name in ("train", "dev"):
        out[name] = [json.loads(line) for line in z.read(f"{name}.json").decode("utf-8").splitlines() if line.strip()]
    out["test"] = [json.loads(line) for line in files["test.json"].read_text("utf-8").splitlines() if line.strip()]
    return out


def who_index():
    import eval_cases
    return eval_cases.who_index(B.load(B.KB / "curation" / "syndromes.yaml"), B.load_gb())


def _prepare_one(args):
    r, gold, features = args
    text = (r.get("description") or "") + "。" + (r.get("detection") or "")
    sex = "F" if re.search(r"月经|经期|带下|妊娠|孕|女性|绝经", text) else "M"
    return {"gold": gold, "sex": sex, "findings": extract(text, features)}


def prepared(split, features, index=None):
    """Records of one split with a WHO pattern: [{gold, sex, findings}]."""
    from multiprocessing import Pool
    index = index or who_index()
    jobs = [(r, index[r["norm_syndrome"]], features) for r in raw_records()[split] if r["norm_syndrome"] in index]
    with Pool() as pool:
        return pool.map(_prepare_one, jobs, chunksize=200)
