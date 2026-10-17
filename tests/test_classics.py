import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "ingest" / "classics"))

import bencao_beiyao  # noqa: E402
import common  # noqa: E402
import jingui  # noqa: E402
import shanghan  # noqa: E402
import yifang  # noqa: E402
import zjdc  # noqa: E402


def names_doses(items):
    return [(i["name"], i["dose_original"]) for i in items]


def test_ids_use_medical_readings_and_fold_variants():
    assert common.to_id("HERB", "白朮") == common.to_id("HERB", "白术") == "HERB.BAI_ZHU"
    assert common.to_id("HERB", "大黃") == "HERB.DA_HUANG"
    assert common.to_id("FORM", "梔子豉湯") == "FORM.ZHI_ZI_CHI_TANG"
    assert common.digit_number("一五") == 15 and common.digit_number("二 0 ") == 20


def test_shared_dose_and_split_tokens():
    block = "　　芍藥　生薑（切）　甘草（炙）　麻黃（去節）各一兩　大棗四枚（擘）杏仁二十四枚（湯浸）"
    items = shanghan.parse_ingredients(block)
    assert names_doses(items) == [("芍藥", "一兩"), ("生薑", "一兩"), ("甘草", "一兩"), ("麻黃", "一兩"),
                                  ("大棗", "四枚"), ("杏仁", "二十四枚")]
    assert items[1]["prep"] == "切"


def test_dose_split_by_line_break_and_names_starting_with_numerals():
    assert names_doses(shanghan.parse_ingredients("大棗十\n二枚　五味子半升　半夏二合半")) == [
        ("大棗", "十二枚"), ("五味子", "半升"), ("半夏", "二合半")]
    assert names_doses(shanghan.parse_ingredients("芍藥二兩大棗十二枚")) == [("芍藥", "二兩"), ("大棗", "十二枚")]


def test_prescribing_clauses_prefer_longest_name_and_skip_contraindications():
    formulas = {"柴胡湯": {"name_zh": "柴胡湯"}, "小柴胡湯": {"name_zh": "小柴胡湯"}, "桂枝湯": {"name_zh": "桂枝湯"}}
    clauses = [{"clause": 96, "text": "往來寒熱，小柴胡湯主之。"},
               {"clause": 17, "text": "若酒客病，不可與桂枝湯，得之則嘔。"},
               {"clause": 28, "text": "服桂枝湯，或下之，仍頭項強痛，宜柴胡湯。"}]
    shanghan.link_clauses(clauses, formulas, aliases={})
    assert [c["prescribes"] for c in clauses] == [["小柴胡湯"], [], ["柴胡湯"]]
    assert formulas["小柴胡湯"]["clauses"] == [96]


def test_jingui_list_layout_folds_notes_into_previous_herb():
    block = jingui.normalise_block("蜀椒一兩，一法二分；烏頭一分，炮；附子半兩（炮，去皮）")
    items = shanghan.parse_ingredients(block)
    assert names_doses(items) == [("蜀椒", "一兩"), ("烏頭", "一分"), ("附子", "半兩")]
    assert items[1]["prep"] == "炮" and items[2]["prep"] == "炮，去皮"


def test_yifang_group_dose_restored_huangqi_and_cut_lists():
    seg = yifang.Segmenter({common.herb_key(n): n for n in ["人參", "白术", "茯苓", "甘草", "当归", "百合", "麦冬", "姜", "枣"]})
    items, end, prep, unknown, stopped = yifang.parse_ingredients("人參白术（土炒）茯苓（二钱）甘草（一钱。）姜三片枣二枚，煎。", seg)
    assert names_doses(items) == [("人參", "二钱"), ("白术", "二钱"), ("茯苓", "二钱"), ("甘草", "一钱"),
                                  ("姜", "三片"), ("枣", "二枚")]
    assert items[1]["prep"] == "土炒" and prep.startswith("煎") and not stopped
    items, *_, stopped = yifang.parse_ingredients("黄（炙。钱半）麦冬（钱半）百合当归（酒洗）", seg)
    assert names_doses(items) == [("黄芪", "钱半"), ("麦冬", "钱半"), ("百合", None), ("当归", None)]
    assert stopped      # no preparation after the list: the transcription cut it


def test_bencao_nature_flavour_channels_and_relations():
    text = ("\n草部\n\n桂枝\n輕，解肌，調營衛辛甘而溫，氣薄升浮。入太陰肺、太陽膀胱經。溫經通脈。\n\n"
            "附子\n大燥，回陽辛甘有毒，大熱純陽。孕婦忌之。畏人參、黃耆。反貝母、半夏。\n\n"
            "*** END OF THE PROJECT GUTENBERG EBOOK ***\n")
    gui, fu = bencao_beiyao.parse(text)
    assert (gui["flavour"], gui["nature"], gui["channels"]) == ("辛甘", "溫", ["CH.BL", "CH.LU"])
    assert gui["actions_label"] == "輕，解肌，調營衛"
    assert (fu["nature"], fu["toxicity"]) == ("大熱", "有毒")
    assert fu["relations"] == {"wei": ["人參", "黃耆"], "fan": ["貝母", "半夏"]}
    assert fu["pregnancy"] == ["孕婦忌之。"]


def test_zjdc_maps_short_and_garbled_names_by_channel():
    table = {"GB": [("头临泣", "GB15"), ("足临泣", "GB41")], "ST": [("足三里", "ST36"), ("上巨虚", "ST37")],
             "GV": [("哑门", "GV15")]}
    seen = []
    assert zjdc.match_code("臨泣", "GB", table, seen) == "GB15"
    assert zjdc.match_code("臨泣", "GB", table, seen) == "GB41"
    assert zjdc.match_code("三里", "ST", table, seen) == "ST36"
    assert zjdc.match_code("上廉", "ST", table, seen) == "ST37"
    assert zjdc.match_code("{{PUA|}}門", "GV", table, seen) == "GV15"


def test_who_pattern_description_is_split_into_tongue_pulse_and_cause():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "ingest"))
    import who2022
    rest, tongue, pulse = who2022.split_pattern(
        "Characterized by dizziness and tinnitus. The tongue is red with a scanty coating. "
        "The pulse is thready and rapid. This pattern often occurs when liver yin fails to control liver yang.")
    assert tongue == "The tongue is red with a scanty coating."
    assert pulse == "The pulse is thready and rapid."
    assert rest.startswith("Characterized by dizziness") and rest.endswith("liver yang.")


def test_who_table_cells_go_to_their_columns():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "ingest"))
    import who2022
    header = ("WGM2#   English term             Synonyms              English definition/description"
              "                         Chinese term    Pinyin term           synonyms")
    row = ("        Hyperactivity of liver   Liver yang            Characterized by dizziness, blurred"
           "                    肝阳上亢证           gān yáng shàng")
    got = who2022.cells(row, who2022.header_positions(header))
    assert got["term_en"] == ["Hyperactivity of liver"] and got["synonyms_en"] == ["Liver yang"]
    assert got["term_zh"] == ["肝阳上亢证"] and got["pinyin"] == ["gān yáng shàng"]
    assert got["definition"] == ["Characterized by dizziness, blurred"]
