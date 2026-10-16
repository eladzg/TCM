"""Parse the "考正穴法" point entries of Zhenjiu Dacheng (Wikisource volumes 8-9) into staging records.

Each record holds the point name as printed, its channel (from the preceding channel heading),
the WHO code it maps to (by Chinese name against the AcuAtlas list), and the full classical
entry: location, needling and moxibustion counts, and the 主 indications.

Usage:
    python3 tools/ingest/classics/zjdc.py      # needs ACUATLAS raw for the name -> code map
"""

import json
import re
import sys

from common import STAGING, clean, herb_key, latest_raw, latest_raw_files, write_jsonl

SOURCE = "WS-ZJDC"
VOLUMES = ("卷八.wiki", "卷九.wiki")
CHANNEL_HEADINGS = [("肺", "LU"), ("大腸", "LI"), ("胃", "ST"), ("脾", "SP"), ("心包", "PC"), ("小腸", "SI"),
                    ("心", "HT"), ("膀胱", "BL"), ("腎", "KI"), ("三焦", "TE"), ("膽", "GB"), ("肝", "LR"),
                    ("任", "CV"), ("督", "GV")]
PUA = "{{PUA|}}"
ENTRY_RE = re.compile(r"^((?:[一-鿿]|\{\{PUA\|\}\}){2,5}?)(?:\s{2,}|（一名|\s*（)")
# Names Zhenjiu Dacheng writes differently from the modern standard.
NAME_FIXES = {"來白": "俠白", "客主人": "上關", "禾髎": "口禾髎", "太杼": "大杼", "膏肓俞": "膏肓", "附陽": "跗陽",
              "梁邱": "梁丘", "外邱": "外丘", "腰腧": "腰俞", "齗交": "齦交"}
# Short names Zhenjiu Dacheng uses where the channel decides the point; a list applies in order of appearance.
CHANNEL_NAMES = {("LI", "三里"): ["手三里"], ("LI", "五里"): ["手五里"], ("ST", "三里"): ["足三里"],
                 ("LR", "五里"): ["足五里"], ("BL", "通谷"): ["足通谷"], ("KI", "通谷"): ["腹通谷"],
                 ("GB", "竅陰"): ["頭竅陰", "足竅陰"], ("GB", "臨泣"): ["頭臨泣", "足臨泣"],
                 ("GB", "陽關"): ["膝陽關"], ("GV", "陽關"): ["腰陽關"],
                 ("ST", "上廉"): ["上巨虛"], ("ST", "下廉"): ["下巨虛"], ("ST", "巨虛上廉"): ["上巨虛"],
                 ("ST", "巨虛下廉"): ["下巨虛"]}
# Names whose rare character Wikisource marks as {{PUA}} (□ here) and that a prefix cannot settle.
PUA_NAMES = {("LI", "禾□"): "口禾髎", ("BL", "中□"): "中髎", ("BL", "□譆"): "譩譆", ("PC", "□門"): "郄門",
             ("TE", "天□"): "天髎", ("TE", "和□"): "耳和髎", ("GB", "□筋"): "輒筋", ("GV", "□門"): "啞門",
             ("GV", "□會"): "囟會"}
# Variant characters of the Ming text: 谿 for 溪, 鬲 for 膈.
VARIANT_CHARS = str.maketrans({"谿": "溪", "鬲": "膈"})


def acuatlas_names():
    path, _ = latest_raw("ACUATLAS")
    points = json.loads(path.read_text("utf-8"))["points"]
    table = {}
    for p in points:
        code = p["id"].replace("-", "").replace("LV", "LR")
        table.setdefault(code[:2], []).append((herb_key(p["hanzi"]), code))
    return table


def channel_of(heading):
    return next((code for word, code in CHANNEL_HEADINGS if word in heading), None)


def match_code(name, channel, table, seen):
    name = PUA_NAMES.get((channel, name.replace(PUA, "□")), name).translate(VARIANT_CHARS)
    name = NAME_FIXES.get(name.replace(PUA, ""), name)
    if (channel, name) in CHANNEL_NAMES:
        order = CHANNEL_NAMES[(channel, name)]
        short = (channel, name)
        name = order[min(seen.count(short), len(order) - 1)]
        seen.append(short)
    key = herb_key(name.replace(PUA, ""))
    candidates = table.get(channel, [])
    exact = [c for k, c in candidates if k == key]
    if exact:
        return exact[0]
    if PUA in name:  # a glyph the transcription lacks: match the remaining characters as a prefix
        prefix = herb_key(name.split(PUA)[0])
        found = [c for k, c in candidates if prefix and k.startswith(prefix)]
        return found[0] if len(found) == 1 else None
    found = [c for ch in table.values() for k, c in ch if k == key]  # listed under another channel
    return found[0] if len(found) == 1 else None


def parse(files, table):
    records, seen = [], []
    for path in files:
        channel, in_points, current = None, False, None
        text = re.sub(r"\{\{PUA\|[^}]*\}\}", PUA, path.read_text("utf-8"))
        for n, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("==="):
                channel = channel_of(s) or channel
                in_points, current = False, None
            elif s == "考正穴法":
                in_points = True
            elif in_points and (m := ENTRY_RE.match(s)):
                name = m.group(1)
                current = {"name_as_printed": name.replace(PUA, "□"), "channel": channel,
                           "point_id": match_code(name, channel, table, seen),
                           "volume": path.stem, "line": n, "text": s}
                records.append(current)
            elif in_points and current and s:
                current["text"] += s
    for r in records:
        text = clean(r["text"].replace(PUA, "□"))
        r["text"] = text
        m = re.search(r"[。，]主(.+)$", text)
        r["indications"] = m.group(1) if m else None
    return records


def main():
    files = [p for p, e in latest_raw_files(SOURCE) if e["file"] in VOLUMES]
    records = parse(sorted(files, key=lambda p: VOLUMES.index(p.name)), acuatlas_names())
    write_jsonl(STAGING / SOURCE / "points.jsonl", records)
    unmatched = [f"{r['channel']}:{r['name_as_printed']}" for r in records if not r["point_id"]]
    print(f"{len(records)} point entries, {len(records) - len(unmatched)} mapped to WHO codes")
    if unmatched:
        print("unmatched: " + " ".join(unmatched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
