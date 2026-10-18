"""Find PubMed literature on the safety of every herb in the KB, through the NCBI E-utilities.

For each herb in kb/curation/herbs.yaml this runs one PubMed search per safety topic (interactions
with five drug classes the interview screens for, liver and kidney toxicity, pregnancy) and keeps
the hit count and the most relevant PMIDs, then fetches each article's title, journal, year and
publication types. Output: kb/staging/PUBMED/herb_evidence.json.

Herbs are named in PubMed by their pinyin and their pharmaceutical Latin names. The Latin names
come from SymMap v2.0 (SMHB file, non-commercial; matched on the Chinese name), so herbs SymMap
does not list are searched by pinyin only.

A hit means only that an article mentions the herb together with the topic. It is evidence for the
clinician to read, never a rule: the app shows it as a draft warning with links to the articles.
Only bibliographic metadata is stored (no abstracts).

Responses are cached in data/raw/PUBMED/cache.json, so a rerun only asks NCBI for what is missing.
Without an API key NCBI allows 3 requests a second; set NCBI_API_KEY to go faster.

Usage:
    python3 tools/ingest/pubmed.py [--limit N] [--refresh]
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent / "classics"))
from common import RAW, ROOT, STAGING, herb_key  # noqa: E402

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
SYMMAP_URL = "http://www.symmap.org/static/download/V2.0/SymMap%20v2.0%2C%20SMHB%20file.xlsx"
SYMMAP_FILE = RAW / "SYMMAP" / "SMHB.xlsx"
CACHE = RAW / "PUBMED" / "cache.json"
OUT = STAGING / "PUBMED" / "herb_evidence.json"
TOP, KEEP = 20, 5   # PMIDs fetched per search (by relevance), and kept after the title filter
# Titles of studies where a herb protects against an injury caused by something else. Their PubMed
# indexing looks like toxicity, so the liver, kidney and pregnancy topics drop them by title.
PROTECTIVE = re.compile(r"protect|ameliorat|alleviat|attenuat|against|prevent|mitigat|improv|reliev|revers|"
                        r"treat|therap|beneficial|rescue|counteract|inhibits?\b|suppress|reduc", re.I)
FILTERED = {"hepatotoxicity", "nephrotoxicity", "pregnancy"}

INTERACTION = ('("Herb-Drug Interactions"[MeSH] OR "Drug Interactions"[MeSH] OR interaction*[tiab] '
               'OR pharmacokinetic*[tiab])')
ADVERSE = ('"adverse effects"[Subheading] OR "toxicity"[Subheading] OR "chemically induced"[Subheading] '
           'OR "Case Reports"[Publication Type] OR toxicity[ti] OR adverse[ti])')
# topic -> (PubMed clause, constraint code from kb/lexicon/interview_safety.yaml or None)
TOPICS = {
    "anticoagulant": ('(warfarin[tiab] OR anticoagulant*[tiab] OR antiplatelet[tiab] OR aspirin[tiab] '
                      'OR clopidogrel[tiab] OR heparin[tiab] OR rivaroxaban[tiab] OR apixaban[tiab] '
                      'OR dabigatran[tiab] OR "Anticoagulants"[MeSH] OR "Platelet Aggregation Inhibitors"[MeSH]) '
                      'AND ' + INTERACTION, "ANTICOAGULANT"),
    "antidiabetic": ('(metformin[tiab] OR glibenclamide[tiab] OR glyburide[tiab] OR glipizide[tiab] '
                     'OR gliclazide[tiab] OR sulfonylurea*[tiab] OR "Hypoglycemic Agents"[MeSH]) AND ' + INTERACTION,
                     "ANTIDIABETIC"),
    "antidepressant": ('(SSRI[tiab] OR "serotonin reuptake inhibitor*"[tiab] OR escitalopram[tiab] OR citalopram[tiab] '
                       'OR sertraline[tiab] OR fluoxetine[tiab] OR paroxetine[tiab] OR venlafaxine[tiab] '
                       'OR "Antidepressive Agents"[MeSH]) AND ' + INTERACTION, "ANTIDEPRESSANT"),
    "immunosuppressant": ('(cyclosporine[tiab] OR ciclosporin[tiab] OR tacrolimus[tiab] OR "Immunosuppressive Agents"[MeSH]) '
                          'AND ' + INTERACTION, "IMMUNO"),
    "digoxin": ("(digoxin[tiab] OR digitoxin[tiab] OR \"Cardiac Glycosides\"[MeSH]) AND " + INTERACTION, "DIGOXIN"),
    # The herb as the cause: an adverse-effects subheading or the injury named in the title, so that
    # the many studies where a herb protects against induced liver or kidney injury stay out.
    "hepatotoxicity": ('(hepatotoxic*[ti] OR "liver injury"[ti] OR "liver damage"[ti] OR hepatitis[ti] '
                       'OR "Chemical and Drug Induced Liver Injury/etiology"[MeSH]) AND (' + ADVERSE + ')', "ORGAN"),
    "nephrotoxicity": ('(nephrotoxic*[ti] OR "kidney injury"[ti] OR "renal failure"[ti] OR nephropathy[ti] '
                       'OR "Kidney Diseases/chemically induced"[MeSH]) AND (' + ADVERSE + ')', "ORGAN"),
    "pregnancy": ('(pregnan*[tiab] OR "Pregnancy"[MeSH]) AND (teratogen*[tiab] OR embryotox*[tiab] '
                  'OR "fetal toxicity"[tiab] OR abortion[tiab] OR miscarriage[tiab] OR (' + ADVERSE + '))', None),
}


# Classical names in the Bencao Beiyao that SymMap lists under their modern pharmacopoeia name
# (simplified characters, as SymMap writes them). Names only; nothing clinical is mapped here.
ALIASES = {
    "黄耆": "黄芪", "沙参": "北沙参", "元参": "玄参", "葳蕤": "玉竹", "甘菊花": "菊花", "天门冬": "天冬",
    "麦门冬": "麦冬", "白芨": "白及", "贝母": "川贝母", "瓜蒌仁": "瓜蒌子", "海带": "昆布", "紫苏": "紫苏叶",
    "钓藤钩": "钩藤", "白芍药": "白芍", "生地黄": "地黄", "干地黄": "地黄", "龙胆草": "龙胆", "大青": "大青叶",
    "牵牛": "牵牛子", "葶苈": "葶苈子", "大戟": "京大戟", "灯草": "灯心草", "海金砂": "海金沙", "草乌头": "草乌",
    "破故纸": "补骨脂", "胡卢巴": "胡芦巴", "蒺藜子": "蒺藜", "益智子": "益智", "白豆蔻": "豆蔻",
    "藿香": "广藿香", "茴香": "小茴香", "甘松香": "甘松", "贯众": "绵马贯众", "续随子": "千金子",
    "冬葵子": "冬葵果", "白藓皮": "白鲜皮", "萆薢": "粉萆薢", "旱莲草": "墨旱莲", "刘寄奴草": "北刘寄奴",
    "桂心": "肉桂", "槐实": "槐角", "皂角": "大皂角", "川椒": "花椒", "杏仁": "苦杏仁", "天竹黄": "天竺黄",
    "胡桃": "核桃仁", "莲蕊须": "莲须", "大麦芽": "麦芽", "黑大豆": "黑豆", "胡麻": "黑芝麻",
    "大麻仁": "火麻仁", "御米壳": "罂粟壳", "莱菔": "莱菔子", "白芥子": "芥子",
    "甜瓜蒂": "瓜蒂", "丹砂": "朱砂", "朴硝": "芒硝", "元明粉": "玄明粉", "礞石": "青礞石",
    "代赭石": "赭石", "钟乳": "钟乳石", "石硫黄": "硫黄", "芍药": "白芍",
}


def symmap_names():
    """herb_key(Chinese name) -> {pinyin, latin: [...], en} from the SymMap SMHB file (downloaded once)."""
    if not SYMMAP_FILE.exists():
        SYMMAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SYMMAP_URL, SYMMAP_FILE)
    import openpyxl
    ws = openpyxl.load_workbook(SYMMAP_FILE, read_only=True).active
    rows = ws.iter_rows(values_only=True)
    head = next(rows)
    col = {name: i for i, name in enumerate(head)}
    out = {}
    for r in rows:
        zh = r[col["Chinese_name"]]
        if not zh:
            continue
        latin = [x.strip() for x in (r[col["Latin_name"]] or "").split(",") if x.strip()]
        out.setdefault(herb_key(zh), {"symmap_id": r[col["Herb_id"]], "pinyin": r[col["Pinyin_name"]] or "",
                                      "latin": latin, "en": r[col["English_name"]] or ""})
    return out


# Words of a pharmaceutical Latin name that name the part used or the processing, not the plant.
PART_WORDS = {"radix", "herba", "rhizoma", "fructus", "semen", "folium", "flos", "et", "caulis", "cortex",
              "bulbus", "seu", "pericarpium", "lignum", "ramulus", "medulla", "praeparata", "praeparatum",
              "concha", "cum", "cacumen", "exocarpium", "cornu", "spica", "calculus", "stigma", "stamen",
              "ramuli", "uncis", "radicis", "tuber", "resina", "massa", "carbonisatum", "carbonisata",
              "immaturus", "recens", "pollen", "aculeus", "spina", "nodus", "petiolus", "testa", "endothelium",
              "tegumen", "pulvis", "succus", "oleum", "plumula", "receptaculum", "glumae", "fermentata"}
# Genitive endings of a pharmaceutical name and the nominative endings they may come from
# (Astragali -> Astragalus, Salviae -> Salvia, Panacis -> Panax, Zingiberis -> Zingiber).
GENITIVE = [("ae", ["a"]), ("acis", ["ax"]), ("idis", ["is", "es"]), ("anthis", ["anthes"]), ("inis", ["o", "in"]),
            ("onis", ["o", "on"]), ("eris", ["er"]), ("is", ["is", "", "e"]), ("i", ["us", "um", "i"])]


# Single words a pharmaceutical name reduces to that mostly mean something else in PubMed: a chemical
# element, a food plant genus, an animal.
TOO_BROAD = {"Sulfur", "Talcum", "Piper", "Prunus", "Prunum", "Pruni", "Persica", "Morus", "Morum", "Asparagus",
             "Asparagum", "Asparagi", "Viola", "Rubus", "Rubum", "Aster", "Gecko", "Verba", "Malva", "Phaseolus",
             "Phaseolum", "Phaseoli", "Vigna", "Raphanus", "Raphanum", "Raphani", "Ostrea", "Hirudo", "Lilium",
             "Lilius", "Lilii", "Litchi", "Litchum", "Litchus", "Juncus", "Juncum", "Junci", "Typha", "Inula"}


def nominatives(word):
    for gen, noms in GENITIVE:
        if word.endswith(gen):
            return [word[:-len(gen)] + n for n in noms]
    return [word]


def binomials(latin):
    """Candidate species names behind a pharmaceutical Latin name: 'Salviae Miltiorrhizae Radix' ->
    'Salvia miltiorrhiza', ... Wrong guesses are harmless (PubMed finds nothing for them); a name
    with a single plant word gives genus candidates only when it has none of two words."""
    words = [w for w in re.split(r"\s+", latin.strip()) if w.lower() not in PART_WORDS]
    if not words:
        return set()
    genera = [g.capitalize() for g in nominatives(words[0].lower())]
    if len(words) == 1:
        return {g for g in genera if len(g) >= 5}
    species = nominatives(words[1].lower())
    return {f"{g} {s}" for g in genera for s in species}


def herb_term(herb, sm):
    """The PubMed clause naming a herb: its pinyin as one word (as papers write it, e.g. Danshen) and,
    when SymMap knows it, its pharmaceutical Latin names and the species names they imply."""
    names = set()
    if len(herb["name_pinyin"].split()) >= 2:  # one syllable (Bing, Jian, Ling) is an ordinary word in English text
        names.add(herb["name_pinyin"].replace(" ", ""))
        if sm and sm["pinyin"]:
            names.add(sm["pinyin"].replace(" ", ""))
    terms = sorted(f"{n}[tiab]" for n in names if len(n) >= 4)
    latin = [re.sub(r"\s+", " ", l) for l in (sm or {}).get("latin", [])]
    phrases = {l for l in latin if len(l.split()) >= 2}
    guesses = set().union(*(binomials(l) for l in latin)) if latin else set()
    if any(" " in g for g in guesses):  # a genus alone (Citrus) is too broad when a species is known
        guesses = {g for g in guesses if " " in g}
    guesses -= TOO_BROAD
    phrases |= guesses
    terms += sorted(f'"{p}"[tiab]' if " " in p else f"{p}[tiab]" for p in phrases)
    return "(" + " OR ".join(terms) + ")" if terms else ""


class Eutils:
    def __init__(self, refresh=False):
        self.key = os.environ.get("NCBI_API_KEY", "")
        self.gap = 0.11 if self.key else 0.35
        self.last = 0.0
        self.cache = {} if refresh or not CACHE.exists() else json.loads(CACHE.read_text(encoding="utf-8"))
        self.dirty = 0

    def get(self, tool, params):
        params = dict(params, db="pubmed", retmode="json", tool="tcm-clinical-adviser")
        if self.key:
            params["api_key"] = self.key
        url = EUTILS + tool + "?" + urllib.parse.urlencode(params)
        for attempt in range(5):
            time.sleep(max(0.0, self.last + self.gap - time.time()))
            self.last = time.time()
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:  # NCBI answers 429 or drops the connection under load; back off and retry
                if attempt == 4:
                    raise
                print(f"  retry {tool} after {e}", file=sys.stderr)
                time.sleep(2 ** (attempt + 1))

    def search(self, term):
        if term not in self.cache:
            r = self.get("esearch.fcgi", {"term": term, "retmax": TOP, "sort": "relevance"})["esearchresult"]
            self.cache[term] = {"count": int(r["count"]), "pmids": r.get("idlist", [])}
            self.dirty += 1
            if self.dirty % 100 == 0:
                self.save()
        return self.cache[term]

    def summaries(self, pmids):
        todo = [p for p in pmids if "pmid:" + p not in self.cache]
        for i in range(0, len(todo), 200):
            batch = todo[i:i + 200]
            r = self.get("esummary.fcgi", {"id": ",".join(batch)})["result"]
            for p in batch:
                d = r.get(p, {})
                self.cache["pmid:" + p] = {
                    "title": re.sub(r"<[^>]+>", "", d.get("title", "")).strip(),
                    "journal": d.get("source", ""),
                    "year": (d.get("pubdate") or "")[:4],
                    "types": d.get("pubtype", []),
                }
            self.save()
        return {p: self.cache["pmid:" + p] for p in pmids}

    def save(self):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, help="only the first N herbs (for a quick check)")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and ask NCBI again")
    args = ap.parse_args(argv)

    herbs = yaml.safe_load((ROOT / "kb" / "curation" / "herbs.yaml").read_text(encoding="utf-8"))
    if args.limit:
        herbs = herbs[:args.limit]
    sm = symmap_names()
    api = Eutils(args.refresh)
    out_herbs, all_pmids = {}, set()
    for n, h in enumerate(herbs, 1):
        key = herb_key(h["name_zh"])
        match = sm.get(key) or sm.get(ALIASES.get(key, ""))
        term = herb_term(h, match)
        if not term:
            continue
        topics = {}
        for topic, (clause, _) in TOPICS.items():
            r = api.search(f"{term} AND {clause}")
            if r["count"]:
                topics[topic] = dict(r)
                all_pmids.update(r["pmids"])
        out_herbs[h["herb_id"]] = {"zh": h["name_zh"], "term": term, "symmap_id": match and match["symmap_id"],
                                   "topics": topics}
        if n % 25 == 0:
            print(f"{n}/{len(herbs)} herbs searched", file=sys.stderr)
    api.save()
    meta = api.summaries(sorted(all_pmids, key=int))
    for h in out_herbs.values():
        for topic in list(h["topics"]):
            r = h["topics"][topic]
            kept = [p for p in r["pmids"] if topic not in FILTERED or not PROTECTIVE.search(meta[p]["title"])]
            if kept:
                h["topics"][topic] = {"count": r["count"], "kept": len(kept), "of": len(r["pmids"]), "pmids": kept[:KEEP]}
            else:
                del h["topics"][topic]
    used = {p for h in out_herbs.values() for r in h["topics"].values() for p in r["pmids"]}
    articles = {p: meta[p] for p in sorted(used, key=int)}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source_id": "PUBMED",
        "retrieved": datetime.date.today().isoformat(),
        "note": "Hit = the article mentions the herb with the topic. count = PubMed hits; kept/of = how many of the most relevant 'of' hits passed the title filter; pmids = the first kept. Draft evidence for clinician review, not a rule.",
        "topics": {t: {"query": q, "constraint": c} for t, (q, c) in TOPICS.items()},
        "herbs": out_herbs,
        "articles": articles,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with_hits = sum(1 for h in out_herbs.values() if h["topics"])
    matched = sum(1 for h in out_herbs.values() if h["symmap_id"])
    print(f"{len(out_herbs)} herbs ({matched} with SymMap Latin names), {with_hits} with literature, "
          f"{len(articles)} articles -> {OUT}")
    for t in TOPICS:
        print(f"  {t}: {sum(1 for h in out_herbs.values() if t in h['topics'])} herbs")


if __name__ == "__main__":
    sys.exit(main())
