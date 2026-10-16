"""Parse the WHO International Standard Terminologies on TCM (2022) PDF into staging records.

Every term row of the book's tables becomes one record: WGM2 number, English term, synonyms,
definition, Chinese term, pinyin and Chinese synonyms, plus the printed page and the section the
(sub)section heading it sits under. Pattern rows (2.4) also get the tongue and pulse sentences of their
description split out. Needs pdftotext (poppler-utils).

Usage:
    python3 tools/ingest/who2022.py
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "classics"))

from common import STAGING, latest_raw, write_jsonl  # noqa: E402

SOURCE = "WHO-ISTTCM-2022"
COLUMNS = ("number", "term_en", "synonyms_en", "definition", "term_zh", "pinyin", "synonyms_zh")
HEADER_RE = re.compile(r"WGM2#\s+English term\s+Synonyms\s+English definition/description\s+Chinese term\s+Pinyin term")
ENTRY_RE = re.compile(r"^\s{0,3}(\d{1,4})\s{2,}\S")
PAGE_RE = re.compile(r"^\s*(\d{1,3})\s+WHO international standard terminologies|terminologies.*?\s(\d{1,3})\s*$")
CJK_RE = re.compile(r"[一-鿿]")
# Rows with no definition are the book's (sub)section headings; each term belongs to the last one above it.
PART_STARTS = [(1, "fundamentals"), (544, "diagnosis"), (930, "pattern differentiation"), (988, "patterns"),
               (1434, "disorders"), (2250, "treatment")]


def header_positions(line):
    names = ["WGM2#", "English term", "Synonyms", "English definition/description", "Chinese term", "Pinyin term"]
    pos = [line.index(n) for n in names]
    return pos + [pos[-1] + 20]  # Chinese synonyms sit right of the pinyin


def cells(line, positions):
    """Assign each run of text (split on 2+ spaces) to the column whose start is nearest at or before it."""
    out = {}
    for m in re.finditer(r"\S+(?: \S+)*", line):
        text, start = m.group(0), m.start()
        if CJK_RE.match(text):  # Chinese terms are narrower than their layout width: place by kind, not position
            col = 4 if "term_zh" not in out else 6
        else:
            col = max(i for i, p in enumerate(positions) if p <= start + 2) if start + 2 >= positions[0] else 0
            if col >= 4 and not CJK_RE.search(text):
                col = 5 if col <= 5 else 6
        out.setdefault(COLUMNS[col], []).append(text)
    return out


def parse(text):
    records, positions, current, page = [], None, None, None
    for line in text.splitlines():
        if "\f" in line:
            line = line.replace("\f", "")
        if HEADER_RE.search(line):
            positions = header_positions(line)
            continue
        if m := re.search(r"(?:^\s*(\d{1,3})\s+WHO international)|(?:\s(\d{1,3})\s*$)", line):
            if "terminologies" in line:  # the footer closes a page, so what follows is on the next one
                page = int(m.group(1) or m.group(2)) + 1
                continue
        if positions is None or not line.strip() or line.strip() in ("Chinese", "synonyms"):
            continue
        if (m := ENTRY_RE.match(line)) and m.start(1) <= positions[1]:
            current = {c: [] for c in COLUMNS}
            current["number"] = [m.group(1)]
            current["page"] = page
            records.append(current)
            line = line[:m.start(1)] + " " * len(m.group(1)) + line[m.end(1):]
        if current is None:
            continue
        for col, parts in cells(line, positions).items():
            if col != "number":
                current[col] += parts
    out = []
    for r in records:
        rec = {"number": int(r["number"][0]), "page": r["page"]}
        rec["term_en"] = " ".join(r["term_en"]).replace("- ", "-").strip()
        rec["synonyms_en"] = " ".join(r["synonyms_en"]).strip() or None
        rec["definition"] = re.sub(r"\s+", " ", " ".join(r["definition"])).replace("’ ", "’").strip() or None
        rec["term_zh"] = "".join(r["term_zh"][:1]) or None
        rec["synonyms_zh"] = "；".join(r["term_zh"][1:] + r["synonyms_zh"]) or None
        rec["pinyin"] = " ".join(r["pinyin"]).strip() or None
        out.append(rec)
    return out


def assign_sections(records):
    category = None
    for r in records:
        if not r["definition"]:
            category = {"en": re.sub(r"^[\d.]+\s*", "", r["term_en"]), "zh": re.sub(r"^[\d.]+\s*", "", r["term_zh"] or "")}
            r["is_heading"] = True
            continue
        r["is_heading"] = False
        r["part"] = next(name for start, name in reversed(PART_STARTS) if r["number"] >= start)
        r["category_en"], r["category_zh"] = (category or {}).get("en"), (category or {}).get("zh")


def split_pattern(definition):
    sentences = re.split(r"(?<=\.)\s+", definition or "")
    tongue = " ".join(s for s in sentences if re.search(r"\btongue\b", s, re.I)) or None
    pulse = " ".join(s for s in sentences if re.search(r"\bpulse\b", s, re.I)) or None
    rest = " ".join(s for s in sentences if not re.search(r"\b(tongue|pulse)\b", s, re.I)) or None
    return rest, tongue, pulse


def main():
    path, manifest = latest_raw(SOURCE)
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    records = parse(text)
    assign_sections(records)
    records = [r for r in records if not r.pop("is_heading")]
    for r in records:
        r["pinyin"] = re.sub(r"\s*Chinese$", "", r["pinyin"] or "") or None
        if r["part"] == "patterns":
            r["manifestations"], r["tongue"], r["pulse"] = split_pattern(r["definition"])
    write_jsonl(STAGING / SOURCE / "terms.jsonl", records)
    by = {}
    for r in records:
        by[r["part"]] = by.get(r["part"], 0) + 1
    print(f"{len(records)} terms from {path.name} (sha256 {manifest['sha256'][:12]}): {by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
