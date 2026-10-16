"""Parse the Gutenberg Shanghan Lun (#24272) into clause and formula staging records.

Writes kb/staging/GUT-SHANGHAN/clauses.jsonl and formulas.jsonl. A formula record keeps the
ingredient list as written (name, original dose, preparation note) and the clauses that
prescribe it ("...主之", "宜...", "與..."). Classical doses are not converted to grams.

Usage:
    python3 tools/ingest/classics/shanghan.py
"""

import re
import sys

from common import STAGING, clean, digit_number, herb_key, latest_raw, write_jsonl

SOURCE = "GUT-SHANGHAN"

CLAUSE_RE = re.compile(r"^[　\s]*([一二三四五六七八九０0〇 ]{1,5})[、，](.*)$")
CHAPTER_RE = re.compile(r"^辨.+第[一二三四五六七八九十]+$")
FORMULA_RE = re.compile(r"^(\S+?[湯散丸煎])方$")
END_RE = re.compile(r"^[　\s]*上[一二三四五六七八九十]+味")
NUM = "一二三四五六七八九十百千半"
UNIT = "兩斤銖枚升合個箇分錢片尺斗把莖"
QTY = rf"(?:(?:如彈丸大|如雞子大)?(?:[{NUM}]+[{UNIT}])+半?匕?|兩半|如雞子大|如博棋子大|等分)"
DOSE_RE = re.compile(rf"^(各)?({QTY})$")
# Transcription slips in the Gutenberg text, fixed before parsing (the raw file stays untouched).
TYPOS = [("&#0;", "一"), ("桂技", "桂枝"), ("桂校", "桂枝"), ("黃岑", "黃芩"), ("三兩了", "三兩"), ("（孽）", "（擘）"),
         ("（半合）", "半合"), ("株茯苓", "茯苓"), ("兩檗三兩，黃連", "黃檗三兩　黃連"), (r"([一二三四五六七八九十]\s*)株", r"\1銖")]
# Short names the clauses use for a formula.
ALIASES = {"白散": "三物小白散"}
# Formulas whose only ingredient is not a materia medica item.
NOT_HERBAL = {"燒褌散"}
# A phrase that prescribes the formula; 不可與 / 不中與 (contraindications) are excluded.
PRESCRIBE_RE = r"(?:{name})(?:主之|亦主之|微發汗|亦可服)|(?<!不可)(?<!不中)(?:宜|與|屬|服|作)(?:{name})"


def body_lines(text):
    start = text.index("*** START OF THE PROJECT GUTENBERG")
    end = text.index("*** END OF THE PROJECT GUTENBERG")
    return text[start:end].splitlines()[1:]


def split_ingredients(block):
    """Split an ingredient block on full-width spaces and on closing notes run into the next herb."""
    text = re.sub(r"\s*\n\s*", "", block.strip("　 \n"))
    text = re.sub(r"）(?=[^\s　，、各（）])", "）　", text)
    return [t for t in re.split(r"[　 ]+", text) if t]


DOSE_PREFIX_RE = re.compile(rf"(各)?({QTY})")


def parse_token(token):
    """One whitespace-separated token can hold several herbs (芍藥二兩大棗十二枚); return them all."""
    notes = re.findall(r"（([^）]*)）", token)
    bare = re.sub(r"（[^）]*）", "", token).strip("，、")
    if DOSE_RE.match(bare):  # a dose split from its herb by a line break
        return [{"name": "", "dose_original": DOSE_RE.match(bare).group(2), "shared": False, "prep": ""}]
    for i in range(1, len(bare)):
        m = DOSE_PREFIX_RE.match(bare, i)
        if m and m.group(2):
            name = bare[:i].removesuffix("大者")
            item = {"name": name, "dose_original": m.group(2), "shared": bool(m.group(1)), "prep": "；".join(notes)}
            rest = bare[m.end():].strip("，、")
            return [item] + (parse_token(rest) if rest else [])
    return [{"name": bare, "dose_original": None, "shared": False, "prep": "；".join(notes)}]


def parse_ingredients(block):
    items, pending = [], []
    for item in (i for token in split_ingredients(block) for i in parse_token(token)):
        if not item["name"]:
            target = pending.pop() if pending else (items[-1] if items else None)
            if target is not None:
                target["dose_original"] = target["dose_original"] or item["dose_original"]
                if target not in items:
                    items.append(target)
            continue
        if item["dose_original"] is None:
            pending.append(item)
            continue
        if item["shared"]:  # 芍藥　生薑　甘草各一兩: the dose applies to every herb since the last dose
            for p in pending:
                p["dose_original"] = item["dose_original"]
        items += pending + [item]
        pending = []
    items += pending
    return [{k: v for k, v in i.items() if k != "shared"} for i in items]


def split_run_together(formulas):
    """Names joined by a line break (大戟芫花) are split when both halves occur as herbs elsewhere; repeats go."""
    known = {i["name"] for f in formulas for i in f["ingredients"]}
    for f in formulas:
        out = []
        for item in f["ingredients"]:
            name = item["name"]
            cut = next((k for k in range(1, len(name)) if name[:k] in known and name[k:] in known), None)
            parts = [name[:cut], name[cut:]] if cut else [name]
            for n, part in enumerate(parts):
                if part not in (o["name"] for o in out):  # a note in parentheses belongs to the last half
                    out.append(dict(item, name=part, prep=item["prep"] if n == len(parts) - 1 else ""))
        f["ingredients"] = out


def link_clauses(clauses, formulas, aliases=None):
    """Fill clause["prescribes"] and formula["clauses"]; clauses carry "clause" ids, formulas are keyed by name."""
    # Match on folded characters (白术/白術) and longest names first, so 小柴胡湯 is not read as 柴胡湯.
    by_key = {herb_key(n): n for n in formulas} | {herb_key(a): n for a, n in (aliases or ALIASES).items()}
    names = sorted(by_key, key=len, reverse=True)
    pattern = re.compile("|".join(herb_key(PRESCRIBE_RE).format(name=re.escape(n)) for n in names))
    name_re = re.compile("|".join(map(re.escape, names)))
    for c in clauses:
        hits = set()
        for m in pattern.finditer(herb_key(c["text"])):
            if m.start() == 0 and m.group(0).startswith("服"):  # 服桂枝湯，... opens with earlier treatment
                continue
            hits.update(by_key[k] for k in name_re.findall(m.group(0)))
        c["prescribes"] = sorted(hits)
    for f in formulas.values():
        f["clauses"] = [c["clause"] for c in clauses if f["name_zh"] in c["prescribes"]]


def parse(text):
    for wrong, right in TYPOS:
        text = re.sub(wrong, right, text)
    lines = body_lines(text)
    clauses, formulas = [], {}
    chapter, current = None, None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip("　 ")
        if CHAPTER_RE.match(stripped):
            chapter, current = stripped, None
        elif (m := CLAUSE_RE.match(line)) and chapter and "脈證並治" in chapter and "可" not in chapter \
                and 0 < (digit_number(m.group(1)) or 0) - (clauses[-1]["clause"] if clauses else 0) <= 3:
            current = {"clause": digit_number(m.group(1)), "chapter": chapter, "text": m.group(2)}
            clauses.append(current)
        elif (m := FORMULA_RE.match(stripped)):
            name, block, j = m.group(1), [], i + 1
            while j < len(lines) and not END_RE.match(lines[j]) and not FORMULA_RE.match(lines[j].strip("　 ")) \
                    and not CLAUSE_RE.match(lines[j]):
                block.append(lines[j])
                j += 1
            method, k = [], j
            if j < len(lines) and END_RE.match(lines[j]):  # 上五味，以水七升... runs to the next blank line
                while k < len(lines) and lines[k].strip("　 "):
                    method.append(lines[k])
                    k += 1
            if name not in formulas:
                formulas[name] = {"name_zh": name, "herbal": name not in NOT_HERBAL, "chapter": chapter, "after_clause": clauses[-1]["clause"]
                                  if clauses else None, "ingredients": parse_ingredients("\n".join(block)),
                                  "preparation": clean("".join(method)), "ingredient_text": clean("".join(block))}
            current, i = None, k
            continue
        elif current is not None and stripped:
            current["text"] += stripped
        elif not stripped:
            current = None
        i += 1

    split_run_together(formulas.values())
    for c in clauses:
        c["text"] = clean(c["text"])
    link_clauses(clauses, formulas)
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
