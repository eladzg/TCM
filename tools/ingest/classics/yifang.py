"""Parse the Wikisource Yifang Jijie (醫方集解, Wang Ang 1682) into formula staging records.

The Wikisource page holds the whole book on one page: each main formula (正方) opens with its
category line (補養之劑第一 ... 經產之劑第二十一), then its name, an optional origin note （《局方》）,
the indications (治...), the ingredient line and Wang Ang's commentary. Appended formulas (附方,
"本方加...名...") are not extracted.

The transcription (from a scan, see the ctext links on the page) has known losses, handled here and
recorded in each record rather than hidden:
  * many lines lose their last characters, so an ingredient list can stop early; such records get
    `partial: true` (no preparation text after the ingredients, or a cut line inside the list);
  * 芪 is missing everywhere: 黃芪 prints as a bare 黄 ("黄（蜜炙。钱半）"). A 黄 standing alone in an
    ingredient list is read as 黃耆, and four formula names are restored (NAME_FIXES).
Ingredients are written run together with the dose after a group ("人參白术（土炒）茯苓（二钱）"):
the dose applies to every herb since the previous dose, as in the book's own convention, and stays
as printed (二钱, 钱半). Names are segmented with the herb names of Bencao Beiyao, the Shanghan Lun
and Jingui Yaolue plus ALIASES; a short unknown run is kept as a name and reported.

Writes kb/staging/WS-YFJJ/formulas.jsonl.

Usage:
    python3 tools/ingest/classics/yifang.py
"""

import re
import sys

from common import STAGING, clean, herb_key, latest_raw, read_jsonl, write_jsonl

SOURCE = "WS-YFJJ"
CATEGORY_RE = re.compile(r"^\s*(\S{2,8}之[劑剂])第([一二三四五六七八九十]+)\s*$")
FORMULA_SUFFIX = re.compile(r"[湯汤散丸丹膏飲饮煎酒方粥子]$")
INDICATION_RE = re.compile(r"^(?:统治|統治|通治|主治|治)")
NUM = "一二三四五六七八九十百千半"
UNIT = "兩两斤銖铢枚片個个升合分錢钱撮具匙杯盏盞碗斗尺寸條条莖茎粒握把"
DOSE = rf"(?:各?(?:[{NUM}]+[{UNIT}]+半?)+|各?[錢钱两兩]半|等分|少許|少许)"
DOSE_RE = re.compile(DOSE)
DOSE_ONLY_RE = re.compile(rf"^{DOSE}$")
# A preparation tail ("，煎。", "爲末，蜜丸", "每服四钱") names how the drug is made or taken.
PREP_RE = re.compile(r"[煎丸末服调調糊膏熬浸搗捣研]")
# Commentary pieces in the indications: explanations (也, 故, 則...) rather than findings.
COMMENT_RE = re.compile(r"也|故|皆|則|则|曰|謂|蓋|所以|者$|宜")

# Abbreviations the book uses -> the name under which Bencao Beiyao (or the Han classics) lists the drug.
ALIASES = {
    "熟地": "熟地黃", "生地": "生地黃", "地黄": "熟地黃", "山茱肉": "山茱萸", "山茱": "山茱萸", "萸肉": "山茱萸",
    "山萸肉": "山茱萸", "丹皮": "牡丹皮", "白芍": "白芍藥", "赤芍": "白芍藥", "芍藥": "白芍藥", "抚芎": "川芎", "撫芎": "川芎",
    "芎": "川芎", "麦冬": "麥門冬", "天冬": "天門冬", "五味": "五味子", "枸杞": "枸杞子", "菟丝": "菟絲子",
    "补骨脂": "破故紙", "故纸": "破故紙", "归身": "當歸", "归尾": "當歸", "当归身": "當歸", "当归尾": "當歸",
    "枣仁": "酸棗仁", "枣": "大棗", "红枣": "大棗", "姜": "生薑", "煨姜": "生薑", "生姜": "生薑", "炮姜": "乾薑",
    "干姜": "乾薑", "黑姜": "乾薑", "炙甘草": "甘草", "炙草": "甘草", "甘草梢": "甘草", "陳皮": "陳皮", "橘皮": "陳皮",
    "橘红": "陳皮", "蔻仁": "白豆蔻", "白蔻": "白豆蔻", "草蔻": "草豆蔻", "砂仁": "砂仁", "缩砂": "砂仁", "缩砂仁": "砂仁",
    "莲肉": "蓮子", "莲子肉": "蓮子", "扁豆": "白扁豆", "苡仁": "薏苡仁", "米仁": "薏苡仁", "桑皮": "桑白皮",
    "钩藤": "釣藤鉤", "钩藤钩": "釣藤鉤", "菖蒲": "石菖蒲", "玄參": "元參", "玄参": "元參",
    "南星": "天南星", "胆星": "天南星", "龟板": "龜板", "败龟板": "龜板", "龟甲": "龜板", "龙胆草": "龍膽草",
    "龙胆": "龍膽草", "车前子": "車前草", "车前": "車前草", "苏叶": "紫蘇", "紫苏叶": "紫蘇", "苏子": "紫蘇",
    "紫苏子": "紫蘇", "全蝎": "蠍", "益智仁": "益智子", "益智": "益智子", "麦芽": "大麥芽", "莱菔子": "萊菔",
    "河车": "紫河车", "小茴香": "茴香", "大茴香": "茴香", "川楝子": "苦楝子", "金铃子": "苦楝子", "樗皮": "椿樗白皮",
    "椿根皮": "椿樗白皮", "莲须": "蓮蕊須", "莲蕊须": "蓮蕊須", "芜荑": "蕪夷", "灯心": "燈草", "灯草": "燈草",
    "海石": "浮石", "海浮石": "浮石", "朱砂": "丹砂", "辰砂": "丹砂", "皂荚": "皂角", "猪牙皂角": "皂角", "蜜": "蜂蜜",
    "白蜜": "蜂蜜", "炼蜜": "蜂蜜", "饴糖": "膠飴", "葱白": "蔥", "葱": "蔥", "豆豉": "淡豆豉", "香豉": "淡豆豉",
    "赤茯苓": "茯苓", "白茯苓": "茯苓", "茯苓皮": "茯苓", "菊花": "甘菊花", "甘菊": "甘菊花", "草决明": "決明子",
    "鼠粘子": "牛蒡子", "牛蒡": "牛蒡子", "玄胡索": "延胡索", "元胡": "延胡索", "延胡": "延胡索", "黄耆": "黃耆",
    "黄芪": "黃耆", "附子": "附子", "熟附子": "附子", "川附子": "附子", "肉桂": "肉桂", "官桂": "肉桂", "桂": "肉桂",
    "竹叶": "淡竹葉", "淡竹叶": "淡竹葉", "人參": "人參", "人参": "人參", "黄连": "黃連", "川连": "黃連",
    "黄芩": "黃芩", "条芩": "黃芩", "片芩": "黃芩", "黄柏": "黃柏", "川柏": "黃柏", "大黄": "大黃", "川大黄": "大黃",
    "知母": "知母", "苍术": "蒼朮", "白术": "白朮", "於术": "白朮", "茯神": "茯神", "远志": "遠志", "柏仁": "柏子仁",
    "柏子仁": "柏子仁", "龙眼肉": "龍眼肉", "枳壳": "枳殼", "枳实": "枳實", "枳實": "枳實", "厚朴": "厚朴",
    "川芎": "川芎", "羌活": "羌活", "防风": "防風", "荆芥": "荊芥", "荆芥穗": "荊芥", "薄荷": "薄荷", "升麻": "升麻",
    "柴胡": "柴胡", "葛根": "葛根", "白芷": "白芷", "细辛": "細辛", "桔梗": "桔梗", "杏仁": "杏仁", "贝母": "貝母",
    "川贝母": "貝母", "瓜蒌": "栝樓仁", "栝蒌": "栝樓仁", "栝蒌仁": "栝樓仁", "瓜蒌仁": "栝樓仁", "花粉": "天花粉",
    "石膏": "石膏", "竹茹": "竹茹", "麻黄": "麻黃", "天麻": "天麻", "蝉蜕": "蟬蛻", "白附子": "白附子",
    "山楂": "山楂", "神曲": "神麴", "阿胶": "阿膠", "艾叶": "艾葉", "鹿茸": "鹿茸", "肉苁蓉": "肉蓯蓉",
    "苁蓉": "肉蓯蓉", "锁阳": "鎖陽", "巴戟": "巴戟天", "巴戟天": "巴戟天", "牡蛎": "牡蠣", "龙骨": "龍骨",
    "赤石脂": "赤石脂", "诃子": "訶子", "诃子肉": "訶子", "肉豆蔻": "肉豆蔻", "肉蔻": "肉豆蔻", "乌梅": "烏梅",
    "金樱子": "金櫻子", "桑螵蛸": "桑螵蛸", "覆盆子": "覆盆子", "使君子": "使君子", "防己": "防己", "汉防己": "防己",
    "木瓜": "木瓜", "萆薢": "萆薢", "茵陳": "茵陳", "茵陈": "茵陳", "竹沥": "竹瀝", "白芥子": "白芥子", "青黛": "青黛",
    "琥珀": "琥珀", "磁石": "磁石", "牛黄": "牛黃", "麝香": "麝香", "冰片": "冰片", "雄黄": "雄黃",
    "金银花": "金銀花", "连翘": "連翹", "乳香": "乳香", "没药": "沒藥", "粳米": "粳米", "糯米": "糯米",
    "桑叶": "桑葉", "蔓荆子": "蔓荊子", "决明子": "決明子", "密蒙花": "密蒙花", "木贼": "木賊", "石斛": "石斛",
    "沙参": "沙參", "北沙参": "沙參", "百合": "百合", "款冬花": "款冬花", "款冬": "款冬花", "紫菀": "紫菀",
    "旋复花": "旋覆花", "旋覆花": "旋覆花", "枇杷叶": "枇杷葉", "马兜铃": "馬兜鈴", "葶苈": "葶藶", "前胡": "前胡",
    "射干": "射干", "山豆根": "山豆根", "地骨皮": "地骨皮", "青蒿": "青蒿", "鳖甲": "鱉甲", "犀角": "犀角",
    "羚羊角": "羚羊角", "郁金": "鬱金", "丹參": "丹參", "丹参": "丹參", "红花": "紅花", "桃仁": "桃仁",
    "五灵脂": "五靈脂", "蒲黄": "蒲黃", "青皮": "青皮", "槟榔": "檳榔", "木香": "木香", "沉香": "沉香", "乌药": "烏藥",
    "香附": "香附", "香附子": "香附", "吴茱萸": "吳茱萸", "吴萸": "吳茱萸", "茱萸": "吳茱萸", "滑石": "滑石",
    "泽瀉": "澤瀉", "泽泻": "澤瀉", "猪苓": "豬苓", "木通": "木通", "半夏": "半夏", "茯苓": "茯苓", "栀子": "梔子",
    "山栀": "梔子", "黑栀": "梔子", "牛膝": "牛膝", "杜仲": "杜仲", "续断": "續斷", "桑寄生": "桑寄生", "独活": "獨活",
    "秦艽": "秦艽", "何首乌": "何首烏", "首乌": "何首烏", "菟丝子": "菟絲子", "枸杞子": "枸杞子", "黄精": "黃精",
    "山藥": "山藥", "山药": "山藥", "芡实": "芡實", "芡實": "芡實", "藿香": "藿香", "藿香叶": "藿香", "紫苏": "紫蘇",
    "生地黄": "生地黃", "熟地黄": "熟地黃", "干地黄": "乾地黃", "当归": "當歸", "麦門冬": "麥門冬", "天門冬": "天門冬",
    "酸枣仁": "酸棗仁", "大枣": "大棗", "甘草": "甘草", "白芍药": "白芍藥", "赤芍药": "白芍藥", "芍药": "白芍藥",
    "芒硝": "芒硝", "朴硝": "朴硝", "元明粉": "芒硝", "玄明粉": "芒硝", "甘遂": "甘遂", "大戟": "大戟", "芫花": "芫花",
    "葳蕤": "葳蕤", "玉竹": "葳蕤", "石菖蒲": "石菖蒲", "紫河车": "紫河車", "人乳": "人乳", "乳汁": "人乳",
    "川乌": "烏頭", "川牛膝": "牛膝", "干葛": "葛根", "枯矾": "白礬", "白矾": "白礬", "浮小麦": "小麥", "淡豉": "淡豆豉",
    "良姜": "高良薑", "高良姜": "高良薑", "苦酒": "醋", "米醋": "醋", "荆介": "荊芥", "薏仁": "薏苡仁", "薤白": "薤",
    "虎胫骨": "虎骨", "风化硝": "朴硝", "黑豆": "黑大豆", "胡桃肉": "胡桃", "枣肉": "大棗", "白酒": "酒", "神曲": "神麴",
    "九節菖蒲": "石菖蒲", "人乳粉": "人乳", "生甘草": "甘草", "草乌": "草烏頭", "地龙": "白頸蚯蚓", "唐球子": "山楂",
    "半夏曲": "半夏", "诃子皮": "訶子", "泽兰叶": "澤蘭", "泽兰": "澤蘭",
    "肉苁": "肉蓯蓉",   # 蓉 cut at a line end in 还少丹
    "栝蒌根": "天花粉", "瓜蒌根": "天花粉",
    "豉": "淡豆豉",
}
# Leftovers of a cut note that are not drugs; the list ends there.
NOT_NAMES = {"风熱"}
# Names that lost a character in the transcription (芪) or were run together.
NAME_FIXES = {"黄汤": "黄芪汤", "黄鳖甲散": "黄芪鳖甲散", "防己黄汤": "防己黄芪汤", "托里黄汤": "托里黄芪汤"}
# Procedures and external applications, not internal formulas.
NOT_HERBAL_RE = re.compile(r"法$|擦牙|点眼|點眼|入目|外敷")


def lexicon():
    """Folded herb name -> printed name, from Bencao Beiyao and the Han-classic ingredient lists, plus ALIASES."""
    names = set(ALIASES) | set(ALIASES.values())
    for r in read_jsonl(STAGING / "GUT-BENCAO-BEIYAO" / "herbs.jsonl"):
        names.add(r["name_zh"])
        names.update(r["other_names"])
    for source in ("GUT-SHANGHAN", "WS-JINGUI"):
        path = STAGING / source / "formulas.jsonl"
        if path.exists():
            names.update(i["name"] for f in read_jsonl(path) for i in f["ingredients"] if 1 < len(i["name"]) <= 5)
    return {herb_key(n): n for n in names if n}


class Segmenter:
    """Longest-match herb names in a run-together ingredient line."""

    def __init__(self, lex):
        self.lex = lex
        self.longest = max(map(len, lex))

    def herb_at(self, s, i):
        for n in range(min(self.longest, len(s) - i), 0, -1):
            piece = s[i:i + n]
            if herb_key(piece) in self.lex and (n > 1 or piece in ALIASES):
                return piece
        # 黄芪 prints as a bare 黄 (芪 lost); 黄 before a note or another herb is that drug.
        if s[i] == "黄" and i + 1 < len(s) and (s[i + 1] == "（" or self.herb_at(s, i + 1)):
            return "黄"
        return None


def paren_end(s, i):
    """End of the note opened at s[i] == "（": its "）", or the next "（" / end when the close was lost."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "（":
            if depth and j > i:
                return j      # a new note opens before this one closed: the close was cut
            depth += 1
        elif s[j] == "）":
            return j + 1
    return len(s)


PREP_CHARS = "炙炒煨酒浸洗去皮尖心蒸焙研姜薑汁盐鹽醋蜜麸麩土泔制製煅烧燒擘切捣搗碎"
DOSE_LEAD_RE = re.compile(rf"^({DOSE})([{PREP_CHARS}].*)$")
DOSE_TRAIL_RE = re.compile(rf"^([{PREP_CHARS}]+)({DOSE})$")
PREP_START_RE = re.compile(r"^[，。、]?(?:加|入|每|共|上|右|同|将|將|用|水|酒|爲|为|研|煎|冷服|熱服|温服|空心|食[前後后])")


def parse_ingredients(text, seg):
    """Read a run-together ingredient line.

    Returns (items, end, preparation, unknown names, stopped): items are {name, dose_original, prep};
    `end` is where the list stops in `text`; `stopped` is true when the list ends without reaching a
    preparation (煎, 爲末, 蜜丸...), i.e. the transcription cut it."""
    items, pending, unknown = [], [], []
    i, prep, stopped = 0, "", True
    while i < len(text):
        ch = text[i]
        if ch == "（":
            j = paren_end(text, i)
            note = text[i + 1:j].rstrip("）")
            dose_parts, notes = [], []
            for part in re.split(r"[。，、；,]", note):
                part = part.strip()
                if not part:
                    continue
                # "二两姜炒" / "炙五钱": a dose run together with a preparation word
                lead, trail = DOSE_LEAD_RE.match(part), DOSE_TRAIL_RE.match(part)
                if DOSE_ONLY_RE.match(part):
                    dose_parts.append(part)
                elif lead:
                    dose_parts.append(lead.group(1))
                    notes.append(lead.group(2))
                elif trail:
                    notes.append(trail.group(1))
                    dose_parts.append(trail.group(2))
                else:
                    notes.append(part)
            target = pending[-1] if pending else (items[-1] if items else None)
            if target is not None and notes:
                target["prep"] = "；".join(filter(None, [target["prep"], *notes]))
            if dose_parts:   # the dose after a group applies to every herb since the previous dose
                for p in pending:
                    p["dose_original"] = dose_parts[0].removeprefix("各")
                items += pending
                pending = []
            i = j
            continue
        if ch in "，、 　":
            i += 1
            continue
        name = seg.herb_at(text, i)
        m = DOSE_RE.match(text, i)
        if m and (pending or items) and not (name and len(name) >= len(m.group(0))):   # 百合 is a herb, not 百 + 合
            dose = m.group(0)
            group = pending if dose.startswith("各") else pending[-1:]
            if not group and items:
                group = items[-1:]
            for p in group:
                p["dose_original"] = p["dose_original"] or dose.removeprefix("各")
            items += pending
            pending = []
            i = m.end()
            continue
        if name:
            pending.append({"name": "黄芪" if name == "黄" else name, "dose_original": None, "prep": ""})
            i += len(name)
            continue
        # Not a herb, dose or note: the preparation, a short unknown name, or the end of the list.
        rest = text[i:]
        run = re.match(r"[^（，、。；]+", rest)
        run = run.group(0) if run else rest[:1]
        after = rest[len(run):]
        followed = not after or after[0] == "（" or bool(seg.herb_at(after, 0))
        if PREP_START_RE.match(rest) or (PREP_RE.search(rest[:8]) and not (len(run) <= 3 and followed)):
            prep = rest
            stopped = not PREP_RE.search(rest[:16])
            break
        if 2 <= len(run) <= 3 and followed and run not in NOT_NAMES:
            pending.append({"name": run, "dose_original": None, "prep": ""})
            unknown.append(run)
            i += len(run)
            continue
        if len(run) == 1 and len(rest) > 1 and (rest[1] == "（" or seg.herb_at(rest, 1)):
            i += 1           # a lone character left from a name the transcription cut (牛 for 牛膝)
            continue
        break
    items += pending
    return items, i, prep, unknown, stopped


def strip_notes(text):
    """Remove the commentary in （）; a note whose close was lost removes the rest."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "（":
            j = text.find("）", i)
            if j == -1:
                break
            i = j + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def main_indications(paragraph):
    """The indications as printed, without Wang Ang's notes: 治... up to the first explanation piece."""
    text = strip_notes(paragraph)
    pieces, out = re.split(r"([，。；])", text), ""
    for k in range(0, len(pieces), 2):
        piece, sep = pieces[k], pieces[k + 1] if k + 1 < len(pieces) else ""
        if out and (COMMENT_RE.search(piece) or len(piece) > 24):
            break
        out += piece + sep
        if re.search(r"[等諸诸之]證$|等證|等症", piece):
            break
    return out.rstrip("，；")


def blocks(lines):
    """(category, category number, first line no., [lines]) for each category-headed block."""
    out, cur = [], None
    for n, line in enumerate(lines, 1):
        if m := CATEGORY_RE.match(line):
            cur = (m.group(1), m.group(2), n, [])
            out.append(cur)
        elif cur is not None and not line.startswith(("{{", "[[Category")):
            cur[3].append((n, line.rstrip()))
    return out


def parse(text, lex):
    seg = Segmenter(lex)
    formulas, seen = [], {}
    for category, number, _, body in blocks(text.splitlines()):
        rows = [(n, l.strip()) for n, l in body if l.strip()]
        if not rows:
            continue
        name_line, printed = rows[0]
        name = re.sub(r"（[^）]*）$", "", printed).strip()
        name = NAME_FIXES.get(name, name)
        origin = printed[len(name):].strip("（）") if printed.startswith(name) else ""
        if len(name) < 2 or len(name) > 12 or not FORMULA_SUFFIX.search(name) and not name.endswith("法"):
            continue   # the category preamble, or a name the transcription cut to one character
        record = {"name_zh": name, "name_as_printed": printed, "category": f"{category}第{number}",
                  "line": name_line, "herbal": not NOT_HERBAL_RE.search(name), "origin": origin}
        k = 1
        while k < len(rows) and not INDICATION_RE.match(rows[k][1]) and k < 4 and rows[k][1].startswith("（"):
            record["origin"] = record["origin"] or rows[k][1].strip("（）")
            k += 1
        if re.match(r"^（[见見].{1,4}[門门]）$", rows[1][1] if len(rows) > 1 else ""):
            record["see_also"] = rows[1][1].strip("（）")
        # indications: from the 治 line to the ingredient line
        start = next((j for j in range(1, min(len(rows), 6)) if INDICATION_RE.match(rows[j][1])), None)
        ing = None
        for j in range((start or 0) + 1, len(rows)):
            line = rows[j][1]
            if line.startswith(("此", "本方", "一方")):
                break
            if line[0] == "黄" and rows[j - 1][1][-1:] in "大地麻雄硫牛蒲姜":
                continue     # 大\n黄: the end of a name broken over two lines, not 黃芪
            if seg.herb_at(line, 0) and ("（" in line[:12] or DOSE_RE.search(line[:16])):
                ing = j
                break
        if start is not None:
            paragraph = clean("".join(l for _, l in rows[start:ing or start + 1]))
            record["indications_text"] = paragraph
            record["indications"] = main_indications(paragraph)
        record["ingredients"], record["ingredient_text"], record["preparation"] = [], "", ""
        if ing is not None:
            lines = []
            for j in range(ing, min(len(rows), ing + 8)):
                line = rows[j][1]
                if j > ing and (line.startswith(("此", "本方", "一方")) or seg.herb_at(line, 0) is None
                                and not line.startswith("（") and len(lines[-1]) >= 36):
                    break
                lines.append(line)
            joined = "".join(lines)
            items, end, prep, unknown, stopped = parse_ingredients(joined, seg)
            record["ingredients"] = items
            record["ingredient_text"] = clean(joined[:end])
            record["preparation"] = clean(re.match(r"[^（。]*。?", prep).group(0)) if prep else ""
            record["unknown_names"] = unknown
            # Complete when the list reaches its preparation and no line inside it was cut short.
            short = any(len(l) < 30 for l in lines[:-1])
            record["partial"] = stopped or short
            record["ingredient_line"] = rows[ing][0]
        record["text"] = clean("".join(l for _, l in rows))
        record["locator"] = f"{record['category']}·{name}"
        key = herb_key(name)
        if key in seen:           # 四物湯, 生脈散 and others appear in a second category
            seen[key].setdefault("also_in", []).append(record["category"])
            if not seen[key]["ingredients"] and record["ingredients"]:
                for f in ("ingredients", "ingredient_text", "preparation", "partial", "ingredient_line"):
                    seen[key][f] = record[f]
            if not seen[key].get("indications") and record.get("indications"):
                for f in ("indications", "indications_text", "locator", "category", "line", "origin"):
                    seen[key][f] = record[f]
            continue
        seen[key] = record
        formulas.append(record)
    return formulas


def main():
    path, manifest = latest_raw(SOURCE)
    formulas = parse(path.read_text("utf-8"), lexicon())
    write_jsonl(STAGING / SOURCE / "formulas.jsonl", formulas)
    with_ing = [f for f in formulas if f["ingredients"]]
    print(f"{len(formulas)} formulas from {path.name} (sha256 {manifest['sha256'][:12]}): "
          f"{sum(1 for f in formulas if f.get('indications'))} with indications, {len(with_ing)} with ingredients "
          f"({sum(1 for f in with_ing if f['partial'])} lists cut short by the transcription)")
    unknown = sorted({u for f in formulas for u in f.get("unknown_names", [])})
    if unknown:
        print(f"{len(unknown)} ingredient name(s) not in the herb lexicon: {'、'.join(unknown)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
