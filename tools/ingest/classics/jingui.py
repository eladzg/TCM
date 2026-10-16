"""Parse the Wikisource Jingui Yaolue into clause and formula staging records.

Same record shapes as shanghan.py. Clause ids are "<chapter>.<paragraph>", e.g. "2.11" for the
eleventh paragraph of chapter 2 (痙濕暍病脈證並治第二). Editorial variant notes ({{*|...}}) are dropped.

Usage:
    python3 tools/ingest/classics/jingui.py
"""

import re
import sys

from common import STAGING, clean, latest_raw, write_jsonl
from shanghan import QTY, link_clauses, parse_ingredients, split_run_together

SOURCE = "WS-JINGUI"
CHAPTER_RE = re.compile(r"^==\s*(.+?第([一二三四五六七八九十]+))\s*==$")
FORMULA_RE = re.compile(r"^(?::;)?\s*(?:''')?([^\s，。：:]+?[湯散丸煎酒膏])方\*?[：:]?(?:''')?(.*)$")
METHOD_RE = re.compile(r"^[上右](?:[一二三四五六七八九十]+味|銼|為|先|以|杵|㕮咀|件|末|切|搗|諸|方)")
NOTE_RE = re.compile(r"^(?:一法|一方|一作|一云|重$|[炮熬炙洗切擘碎燒炒浸去酒蜜研生][^一二三四五六七八九十半]{0,5}$)")
DOSE_SEARCH_RE = re.compile(QTY)
CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
# Chapters 23-25 are dietary taboos and miscellaneous remedies, not syndrome chapters.
LAST_CLINICAL_CHAPTER = 22


def chapter_number(text):
    n = 0
    for part in re.split("十", text):
        n = n * 10 + (CN.get(part, 1 if part == "" else 0))
    return n if "十" in text else CN[text]


def strip_markup(text):
    text = re.sub(r"\{\{\*\|[^{}]*\}\}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return text.replace(":;", "；").replace("'''", "")


def normalise_block(block):
    """Bring 、，；-separated lists to the full-width-space layout shanghan.parse_ingredients reads,
    folding notes such as "炮" or "一法二分" into the preceding herb as (note)."""
    out = []
    block = re.sub(r"（[^）]*）", lambda m: m.group(0).replace("，", "、").replace("、", "/"), block)
    for token in re.split(r"[　\s、，,；;。]+", block):
        if not token:
            continue
        if out and NOTE_RE.match(token):
            out[-1] += f"（{token}）"
        else:
            out.append(token)
    return "　".join(out).replace("/", "，")


def parse(text):
    clauses, formulas = [], {}
    chapter = chapter_no = None
    para = 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if m := CHAPTER_RE.match(line):
            chapter, chapter_no, para = m.group(1), chapter_number(m.group(2)), 0
        elif chapter_no and chapter_no <= LAST_CLINICAL_CHAPTER and (m := FORMULA_RE.match(line)) \
                and "主之" not in line:
            inline = strip_markup(m.group(2))
            name, block, method = m.group(1), [inline] if DOSE_SEARCH_RE.search(inline) else [], []
            i += 1
            while i < len(lines):
                body = strip_markup(lines[i].lstrip(":").strip())
                if CHAPTER_RE.match(lines[i].strip()) or FORMULA_RE.match(lines[i].strip()):
                    break
                if not body:
                    if method:
                        break
                    i += 1
                    continue
                if METHOD_RE.match(body) or method:
                    method.append(body)
                elif "主之" in body or len(body) > 120:
                    break
                else:
                    block.append(body)
                i += 1
            block = [b for b in block if b and not re.match(r"^治|^方見", b)]
            if name not in formulas and block and DOSE_SEARCH_RE.search("".join(block)):
                formulas[name] = {"name_zh": name, "herbal": True, "chapter": chapter,
                                  "after_clause": clauses[-1]["clause"] if clauses else None,
                                  "ingredients": parse_ingredients(normalise_block("\n".join(block))),
                                  "preparation": clean("".join(method)), "ingredient_text": clean("".join(block))}
            continue
        elif chapter_no and chapter_no <= LAST_CLINICAL_CHAPTER and line and not line.startswith(("=", ":", "{{", "[[", "<")):
            para += 1
            clauses.append({"clause": f"{chapter_no}.{para}", "chapter": chapter, "text": clean(strip_markup(line))})
        i += 1
    split_run_together(formulas.values())
    link_clauses(clauses, formulas, aliases={})
    return clauses, list(formulas.values())


def main():
    path, manifest = latest_raw(SOURCE)
    clauses, formulas = parse(path.read_text("utf-8"))
    out = STAGING / SOURCE
    write_jsonl(out / "clauses.jsonl", clauses)
    write_jsonl(out / "formulas.jsonl", formulas)
    missing = [f["name_zh"] for f in formulas if not f["clauses"]]
    print(f"{len(clauses)} clauses, {len(formulas)} formulas from {path.name} (sha256 {manifest['sha256'][:12]})")
    if missing:
        print(f"{len(missing)} formula(s) with no prescribing clause: {'、'.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
