import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "ingest"))

import pubmed  # noqa: E402


def test_binomials_from_pharmaceutical_latin():
    assert pubmed.binomials("Salviae Miltiorrhizae Radix Et Rhizoma") == {"Salvia miltiorrhiza"}
    assert "Citrus reticulata" in pubmed.binomials("Citri Reticulatae Pericarpium")
    assert "Zingiber" in pubmed.binomials("Zingiberis Rhizoma")


def test_herb_term_drops_the_genus_when_a_species_is_known():
    sm = {"pinyin": "Chenpi", "latin": ["Citri Reticulatae Pericarpium", "Pericarpium Citri Reticulatae"]}
    term = pubmed.herb_term({"name_pinyin": "Chen Pi"}, sm)
    assert '"Citrus reticulata"[tiab]' in term and "Citrus[tiab]" not in term and "ChenPi[tiab]" in term


def test_every_topic_names_a_screened_constraint():
    import yaml
    lex = yaml.safe_load((ROOT / "kb" / "lexicon" / "interview_safety.yaml").read_text("utf-8"))
    codes = {c["code"] for c in lex["constraint_terms"]}
    assert {c for _, c in pubmed.TOPICS.values() if c} <= codes


def test_staged_evidence_keeps_metadata_only():
    path = ROOT / "kb" / "staging" / "PUBMED" / "herb_evidence.json"
    ev = json.loads(path.read_text("utf-8"))
    for pmid in {p for h in ev["herbs"].values() for r in h["topics"].values() for p in r["pmids"]}:
        assert set(ev["articles"][pmid]) == {"title", "journal", "year", "types"}
    assert "anticoagulant" in ev["herbs"]["HERB.DAN_SHEN"]["topics"]
