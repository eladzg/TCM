"""Parse the Gutenberg Bencao Beiyao (#26888) into one staging record per materia medica entry.

Each record keeps the entry's full text and what can be read off it mechanically:
nature (寒熱溫涼平) and flavour from the opening sentence, channels entered from 入… phrases,
toxicity (有毒/有大毒), pregnancy warnings, and the 惡/畏/反/忌 relations. Wang Ang gives no
gram doses; those stay with the clinician.

Usage:
    python3 tools/ingest/classics/bencao_beiyao.py
"""

import re
import sys

from common import STAGING, clean, latest_raw, write_jsonl

SOURCE = "GUT-BENCAO-BEIYAO"
SECTIONS = {"草部", "木部", "果部", "穀菜部", "金石水土部", "禽獸部", "鱗介魚蟲部", "人部"}
# Headings whose rare characters the Gutenberg edition dropped or garbled, read from each entry's text.
HEADING_FIXES = {"本": "藁本", "芎": "川芎", "草": "豨薟草", "薺": "薺苨", "蓄": "萹蓄", "砂": "硇砂", "石": "礜石",
                 "皮": "蝟皮", "濃朴": "厚朴", "山查": "山楂"}
FLAVOURS = "酸苦甘辛鹹淡澀"
# A flavour run (甘, 辛甘, 甘淡微鹹, 辛甘而) that ends at a nature word, 性, 有毒 or punctuation.
FLAVOUR_RE = re.compile(rf"[{FLAVOURS}](?:[{FLAVOURS}、]|而(?=[{FLAVOURS}])|微(?=[{FLAVOURS}]))*(?=而|性|氣|有|[微大]?[寒熱溫涼平]|[，。；])")
NATURE_RE = re.compile(r"(?:^|性|氣|而|有毒|[，、酸苦甘辛鹹淡澀])((?:[微大]?[寒熱溫涼平])+)")
ORGANS = [("心包", "CH.PC"), ("包絡", "CH.PC"), ("三焦", "CH.TE"), ("大腸", "CH.LI"), ("小腸", "CH.SI"),
          ("膀胱", "CH.BL"), ("命門", "CH.KI"), ("肺", "CH.LU"), ("胃", "CH.ST"), ("脾", "CH.SP"), ("心", "CH.HT"),
          ("腎", "CH.KI"), ("膽", "CH.GB"), ("肝", "CH.LR")]
SIX = {"手太陰": "CH.LU", "手陽明": "CH.LI", "足陽明": "CH.ST", "足太陰": "CH.SP", "手少陰": "CH.HT",
       "手太陽": "CH.SI", "足太陽": "CH.BL", "足少陰": "CH.KI", "手厥陰": "CH.PC", "手少陽": "CH.TE",
       "足少陽": "CH.GB", "足厥陰": "CH.LR"}
ENTER_RE = re.compile(r"入([^，。；︰（）]{1,14})")
PREGNANCY_RE = re.compile(r"[^。；]*(?:墮胎|落胎|下胎|孕婦[^。；]{0,6}[忌禁慎勿]|妊娠[^。；]{0,6}[忌禁慎勿]|[忌禁]用?於?孕|孕婦服之)[^。；]*[。；]?")
# Relation sentences are short and stand alone: 惡龜甲、白鮮皮。畏防風。反藜蘆。
RELATION_RE = re.compile(r"(?:^|[。；])(惡|畏|反|忌)([^。；，（]{1,30})(?=[。；])")
NOT_ITEMS = {"之", "用", "氣", "食", "服"}


def headings(lines):
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s and len(s) <= 9 and not re.search(r"[，。；︰（）！﹗：》《]", s) and not lines[i - 1].strip():
            out.append((i, s))
    return out


def main_text(text):
    """Entry text without Wang Ang's parenthetical commentary (quotes, case notes)."""
    prev = None
    while prev != text:
        prev, text = text, re.sub(r"（[^（）]*）", "", text)
    return text


def channels(text):
    found = []
    for m in ENTER_RE.finditer(text):
        window = m.group(1)
        for six, ch in SIX.items():
            if six in window:
                found.append(ch)
        for organ, ch in ORGANS:
            if organ in window:
                found.append(ch)
                window = window.replace(organ, "")
    return sorted(set(found))


def relations(text):
    rel = {}
    for m in RELATION_RE.finditer(text):
        items = [x for x in re.split(r"[、，]", m.group(2)) if x and len(x) <= 5 and x not in NOT_ITEMS]
        if items:
            rel.setdefault({"惡": "wu", "畏": "wei", "反": "fan", "忌": "ji"}[m.group(1)], []).extend(items)
    return rel


def parse(text):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == "草部")
    end = next(i for i, l in enumerate(lines) if "END OF THE PROJECT GUTENBERG" in l)
    heads = [(i, h) for i, h in headings(lines[start:end]) for i in [i + start]]
    records, section = [], None
    for n, (i, head) in enumerate(heads):
        if head in SECTIONS:
            section = head
            continue
        nxt = heads[n + 1][0] if n + 1 < len(heads) else end
        full = clean("".join(lines[i + 1:nxt]))
        plain = main_text(full)
        first = plain.split("。", 1)[0] + "。"
        window = "。".join(plain.split("。", 2)[:2])
        fm = FLAVOUR_RE.search(window)
        nm = NATURE_RE.search(window, fm.start()) if fm else re.search(r"(?:性|氣)((?:[微大]?[寒熱溫涼平])+)", window)
        names = [HEADING_FIXES.get(h, h) for h in head.split("、")]  # 乾薑、黑薑: one entry, two names
        records.append({
            "name_zh": names[0],
            "other_names": names[1:],
            "heading_as_printed": head,
            "section": section,
            "line": i + 1,
            "summary": first,
            "flavour": fm.group(0).replace("而", "").strip("、") if fm else None,
            "nature": nm.group(1) if nm else None,
            "actions_label": first[:fm.start()].strip("，").removesuffix("味").strip("，") if fm and fm.start() < len(first) else None,
            "channels": channels(plain),
            "toxicity": "有大毒" if "有大毒" in window else "有毒" if "有毒" in window else None,
            "pregnancy": [m.group(0) for m in PREGNANCY_RE.finditer(plain)],
            "relations": relations(plain),
            "text": full,
        })
    return records


def main():
    path, manifest = latest_raw(SOURCE)
    records = parse(path.read_text("utf-8"))
    write_jsonl(STAGING / SOURCE / "herbs.jsonl", records)
    no_nature = [r["name_zh"] for r in records if not r["nature"]]
    print(f"{len(records)} entries from {path.name} (sha256 {manifest['sha256'][:12]}); "
          f"{len(records) - len(no_nature)} with nature/flavour, "
          f"{sum(1 for r in records if r['channels'])} with channels, "
          f"{sum(1 for r in records if r['pregnancy'])} with a pregnancy warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
