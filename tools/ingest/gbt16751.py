"""Parse the GB/T 16751.2 revision draft (TCM clinical terminology, part 2: syndromes/patterns)
into staging records.

The draft is a .docx where each entry is a code paragraph ("5.6.2.3.1.2"), one or more name
paragraphs (the Chinese term with its English name, then Chinese synonyms) and one definition
paragraph. Definitions of concrete patterns read "因…所致。临床以 <findings> 为特征的证候。";
category entries ("…一类证候") have no findings of their own. The findings before 伴见/或伴见/可伴见
are the main ones, the rest secondary, so links can tell the two apart.

Usage:
    python3 tools/ingest/gbt16751.py
"""

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "classics"))

from common import STAGING, latest_raw_files, write_jsonl  # noqa: E402

SOURCE = "GBT-16751-2"
CODE_RE = re.compile(r"^\d+(\.\d+)*$")
NAME_RE = re.compile(r"^([一-鿿、（）()]+?证)(?:\s+(.*))?$")
FINDINGS_RE = re.compile(r"临床以(.+?)等?为特征")
SECONDARY_RE = re.compile(r"[，,]?\s*(?:或|可|并|常)?伴(?:见|有)")
CAUSE_RE = re.compile(r"^(.*?所致)。")


def paragraphs(docx_path):
    xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode("utf-8")
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        text = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", p)).strip()
        if text:
            yield text


def parse(docx_path):
    records = []
    current = None
    for text in paragraphs(docx_path):
        if CODE_RE.match(text):
            current = {"code": text, "names": [], "en": None, "definition": None}
            records.append(current)
            continue
        if current is None or current["definition"]:
            continue  # front matter, or the alphabetical indexes after the last entry
        if "。" in text:
            current["definition"] = text
            continue
        m = NAME_RE.match(text)
        if m:
            current["names"].append(m.group(1))
            if m.group(2) and not current["en"]:
                current["en"] = m.group(2).strip()
    out = []
    codes = {r["code"] for r in records}
    for r in records:
        if not r["names"] or not r["definition"]:
            continue
        parent = r["code"].rsplit(".", 1)[0] if "." in r["code"] else None
        while parent and parent not in codes:
            parent = parent.rsplit(".", 1)[0] if "." in parent else None
        rec = {"code": r["code"], "parent": parent, "name_zh": r["names"][0], "synonyms_zh": r["names"][1:],
               "name_en": r["en"], "definition": r["definition"], "cause": None,
               "findings_main": None, "findings_secondary": None}
        cause = CAUSE_RE.match(r["definition"])
        if cause:
            rec["cause"] = cause.group(1)
        found = FINDINGS_RE.search(r["definition"])
        if found:
            parts = SECONDARY_RE.split(found.group(1), maxsplit=1)
            rec["findings_main"] = parts[0].strip("，, ")
            rec["findings_secondary"] = parts[1].strip("，, ") if len(parts) > 1 else None
        out.append(rec)
    return out


def main():
    files = latest_raw_files(SOURCE)
    docx = next(path for path, _ in files if path.suffix == ".docx")
    records = parse(docx)
    write_jsonl(STAGING / SOURCE / "syndromes.jsonl", records)
    with_findings = sum(1 for r in records if r["findings_main"])
    print(f"{len(records)} entries, {with_findings} with findings -> kb/staging/{SOURCE}/syndromes.jsonl")


if __name__ == "__main__":
    main()
