import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build  # noqa: E402

SOURCES = {
    "PD": {"source_id": "PD", "title": "t", "license": "pd", "license_class": "public_domain"},
    "NC": {"source_id": "NC", "title": "t", "license": "nc", "license_class": "non_commercial"},
    "BAD": {"source_id": "BAD", "title": "t", "license": "arr", "license_class": "prohibited"},
}
CONFIG = {"allowed_license_classes": ["public_domain", "non_commercial"], "kb_version": "kb_test"}


def rows(**overrides):
    base = {name: [] for name in build.ENTITIES}
    base["channels"] = [{"channel_id": "CH.LR", "name_en": "Liver", "name_pinyin": "Zu Jueyin Gan Jing",
                         "status": "approved",
                         "sources": [{"source_id": "PD", "field": "channel_id", "locator": "codes"}]}]
    base["points"] = [{"point_id": "LR3", "channel_id": "CH.LR", "name_pinyin": "Taichong",
                       "location": "On the dorsum of the foot", "status": "approved",
                       "sources": [{"source_id": "PD", "field": "location", "locator": "p. 1"}]}]
    base["herbs"] = [{"herb_id": "HERB.GAN_CAO", "name_pinyin": "Gan Cao", "status": "draft"}]
    base["formulas"] = [{"formula_id": "FORM.GUI_ZHI_TANG", "name_pinyin": "Gui Zhi Tang", "status": "draft",
                         "composition": [{"herb_id": "HERB.GAN_CAO", "dose_original": "二兩"}],
                         "sources": [{"source_id": "PD", "field": "composition", "locator": "條12"}]}]
    base.update(overrides)
    return base


def test_valid_kb_has_no_errors():
    assert build.validate(SOURCES, CONFIG, rows()) == []


def test_repo_kb_is_valid():
    assert build.validate(*build.load_kb()) == []


def test_prohibited_source_is_rejected():
    r = rows()
    r["points"][0]["sources"][0]["source_id"] = "BAD"
    assert any("prohibited" in e for e in build.validate(SOURCES, CONFIG, r))


def test_non_commercial_rejected_when_config_disallows_it():
    r = rows()
    r["points"][0]["sources"][0]["source_id"] = "NC"
    strict = dict(CONFIG, allowed_license_classes=["public_domain"])
    assert build.validate(SOURCES, CONFIG, r) == []
    assert any("non_commercial" in e for e in build.validate(SOURCES, strict, r))


def test_clinical_field_without_source_is_rejected():
    r = rows()
    r["points"][0]["indications"] = "headache"
    assert any("'indications' has no source ref" in e for e in build.validate(SOURCES, CONFIG, r))


def test_bad_id_duplicate_and_missing_fk_are_reported():
    r = rows()
    dup = copy.deepcopy(r["points"][0])
    bad = dict(copy.deepcopy(dup), point_id="LR-3")
    ghost = dict(copy.deepcopy(dup), point_id="GB20", channel_id="CH.GB")
    r["points"] += [dup, bad, ghost]
    errors = build.validate(SOURCES, CONFIG, r)
    assert any("duplicate id" in e for e in errors)
    assert any("points:LR-3: id does not match" in e for e in errors)
    assert any("'CH.GB' not in channels" in e for e in errors)


def test_formula_with_unknown_herb_is_rejected():
    r = rows()
    r["formulas"][0]["composition"].append({"herb_id": "HERB.GUI_ZHI"})
    assert any("HERB.GUI_ZHI" in e for e in build.validate(SOURCES, CONFIG, r))


def test_chunk_ids_are_stable_and_only_approved_rows_are_chunked():
    chunks = build.build_chunks(SOURCES, CONFIG, rows())
    assert [c["entity_id"] for c in chunks] == ["LR3"]
    assert chunks[0]["source_ids"] == ["PD"]
    again = build.build_chunks(SOURCES, CONFIG, rows())
    assert chunks[0]["chunk_id"] == again[0]["chunk_id"]
    edited = rows()
    edited["points"][0]["location"] = "Changed"
    assert build.build_chunks(SOURCES, CONFIG, edited)[0]["chunk_id"] != chunks[0]["chunk_id"]
    drafts = build.build_chunks(SOURCES, CONFIG, rows(), include_drafts=True)
    assert {c["entity_id"] for c in drafts} == {"LR3", "FORM.GUI_ZHI_TANG"}


def test_seed_escapes_quotes_and_includes_formula_herbs():
    r = rows()
    r["points"][0]["name_en"] = "Great Rushing's"
    seed = build.build_seed(SOURCES, CONFIG, r)
    assert "Great Rushing''s" in seed
    assert "INSERT INTO formula_herb (formula_id, herb_id, dose_original)" in seed
