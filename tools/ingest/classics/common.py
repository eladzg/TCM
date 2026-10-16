"""Shared helpers for parsing public-domain classical texts into staging records.

Names are kept in the traditional characters of the source. Matching between books goes through
`herb_key`, which folds variant characters and simplified forms onto one key, and IDs come from
`to_id`, which romanises that key with pypinyin plus a small table of medical readings.
"""

import json
import re
from pathlib import Path

import opencc
from pypinyin import Style, lazy_pinyin, load_phrases_dict

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
STAGING = ROOT / "kb" / "staging"

_t2s = opencc.OpenCC("t2s")

# Variant characters used interchangeably in the editions we parse (applied after t2s).
VARIANTS = str.maketrans({"栝": "瓜", "楼": "蒌", "濃": "浓", "朮": "术", "兒": "儿"})

# Medical readings pypinyin gets wrong (character context is not enough for these).
load_phrases_dict({
    "白术": [["bái"], ["zhú"]], "苍术": [["cāng"], ["zhú"]], "大黄": [["dà"], ["huáng"]],
    "芍药": [["sháo"], ["yào"]], "厚朴": [["hòu"], ["pò"]], "黄柏": [["huáng"], ["bǎi"]],
    "阿胶": [["ē"], ["jiāo"]], "葶苈": [["tíng"], ["lì"]], "瓜蒌": [["guā"], ["lóu"]],
    "射干": [["shè"], ["gān"]], "干姜": [["gān"], ["jiāng"]], "干地黄": [["gān"], ["dì"], ["huáng"]],
    "地黄": [["dì"], ["huáng"]], "大枣": [["dà"], ["zǎo"]], "蜀漆": [["shǔ"], ["qī"]],
    "茵陈": [["yīn"], ["chén"]], "柴胡": [["chái"], ["hú"]], "白头翁": [["bái"], ["tóu"], ["wēng"]],
    "葛根": [["gé"], ["gēn"]], "贝母": [["bèi"], ["mǔ"]], "薄荷": [["bò"], ["he"]],
    "枳实": [["zhǐ"], ["shí"]], "泽泻": [["zé"], ["xiè"]], "藁本": [["gǎo"], ["běn"]],
    "猪苓": [["zhū"], ["líng"]], "芫花": [["yuán"], ["huā"]], "大戟": [["dà"], ["jǐ"]],
    "汤": [["tāng"]], "散": [["sǎn"]], "豉": [["chǐ"]], "调胃": [["tiáo"], ["wèi"]], "当归": [["dāng"], ["guī"]],
    "半夏": [["bàn"], ["xià"]], "石膏": [["shí"], ["gāo"]], "香豉": [["xiāng"], ["chǐ"]],
    "栀子": [["zhī"], ["zǐ"]], "藏": [["zàng"]], "百合": [["bǎi"], ["hé"]], "蛇床": [["shé"], ["chuáng"]],
})

CN_NUM = {"〇": 0, "０": 0, "0": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def digit_number(text):
    """Parse positional Chinese digits as written in the Gutenberg clause numbers: 一五 -> 15, 二 0 -> 20."""
    digits = [CN_NUM[c] for c in text if c in CN_NUM]
    return int("".join(map(str, digits))) if digits else None


def herb_key(name):
    """A comparison key that folds traditional/simplified and variant characters."""
    return _t2s.convert(name).translate(VARIANTS)


def pinyin_words(name_zh):
    return [p for p in lazy_pinyin(herb_key(name_zh), style=Style.NORMAL, errors="ignore") if p]


def to_id(prefix, name_zh):
    words = pinyin_words(name_zh)
    return f"{prefix}." + "_".join(w.upper().replace("Ü", "V") for w in words)


def to_pinyin_title(name_zh):
    return " ".join(w.capitalize() for w in pinyin_words(name_zh))


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def latest_raw_files(source_id):
    """The newest raw files of a source with their manifest entries, as saved by tools/ingest/fetch_raw.py."""
    days = sorted((RAW / source_id).iterdir()) if (RAW / source_id).exists() else []
    if not days:
        raise SystemExit(f"no raw files for {source_id}; run tools/ingest/fetch_raw.py first")
    entries = json.loads((days[-1] / "manifest.json").read_text("utf-8"))
    return [(days[-1] / e["file"], e) for e in entries]


def latest_raw(source_id):
    return latest_raw_files(source_id)[0]


def clean(text):
    return re.sub(r"[\s　]+", "", text)
