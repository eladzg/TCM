# TCM Clinical Adviser: knowledge base

The verified TCM knowledge base (points, channels, herbs, formulas, syndromes, safety rules and the Hebrew symptom lexicon) that the Diagnostic and Treatment agents retrieve from. Agents may only cite entity IDs and chunk IDs that come from here.

## Layout

| Path | What it holds |
| --- | --- |
| `kb/sources.yaml` | Every citable source with its license and `license_class` |
| `kb/config.yaml` | Which license classes are allowed (internal use: non-commercial allowed) and the KB version |
| `kb/curation/<entity>.yaml` | Curated rows, one file per table. Each clinical field needs a `sources` entry with a locator |
| `kb/schema/` | PostgreSQL schema (`001_core.sql`) and pgvector indexes (`002_vectors.sql`) |
| `tools/build.py` | Validates the YAML, writes `build/seed.sql` and `build/chunks.jsonl` |
| `tools/ingest/fetch_raw.py` | Saves a source's raw file under `data/raw/<source>/<date>/` with a sha256 manifest |
| `tools/ingest/classics/` | Parsers for the public-domain classics and AcuAtlas, and `curate.py`, which turns their output into draft curation rows |
| `kb/staging/<source>/*.jsonl` | Parser output: every clause, formula, herb entry and point entry with its full original text and locator |

## Rules the build enforces

- IDs follow fixed patterns: `LR3` (WHO point code, no hyphen), `CH.LR`, `SYN.LR.YANG_RISING`, `HERB.GAN_CAO`, `FORM.GUI_ZHI_TANG`.
- A source whose `license_class` is not allowed in `kb/config.yaml` fails the build. Sacred Lotus and American Dragon are registered as `prohibited`.
- A clinical field without a source ref fails the build.
- Only `approved` rows become chunks. Chunk IDs are a hash of entity, facet and text, so unchanged rows keep their IDs across versions.

## Classical sources (public domain)

| Source | What is extracted |
| --- | --- |
| 傷寒論 Shanghan Lun (Gutenberg #24272) | 397 numbered clauses; 110 formulas with ingredients, original doses (三兩, 十二枚) and preparation; which clauses prescribe each formula |
| 金匱要略 Jingui Yaolue (Wikisource) | 448 paragraphs (chapters 1-22); the 53 formulas whose ingredients this transcription prints |
| 醫方集解 Yifang Jijie (Wang Ang, 1682; Wikisource) | 373 main formulas (正方) with their category (補養之劑 ... 經產之劑), indications (治...), ingredients with the printed doses (二钱, 钱半) and full text; 317 become new formula rows (253 with a composition), 42 add an indications source to a Han-classic row |
| 本草備要 Bencao Beiyao (Gutenberg #26888) | 465 entries: nature, flavour, channels entered, toxicity, pregnancy warnings, 惡/畏/反/忌 relations, full text |
| 針灸大成 Zhenjiu Dacheng (Wikisource vols. 8-9) | 356 point entries (考正穴法) mapped to WHO codes: location, needle and moxa counts, indications |
| AcuAtlas (CC BY 4.0) | English location, actions, indications, depth and cautions for the 361 WHO points |
| WHO International Standard Terminologies on TCM 2022 (CC BY-NC-SA 3.0 IGO) | 3,357 terms; 423 patterns become `syndromes` (presentation, cause, tongue, pulse); 345 symptoms, signs, tongue and pulse findings become `manifestations` |

Everything generated is `draft`. Not extracted, by design: gram doses (`dose_min_g`/`dose_max_g`), syndrome-manifestation weights and the links between syndromes and points or formulas, which are clinician decisions. Known gaps: the Gutenberg Bencao Beiyao has no entries for 大黃, 黃芩 and 黃連, and the Wikisource Jingui omits most formula listings ("方見上"). The Wikisource Yifang Jijie lost the ends of many lines, so 193 of its 292 ingredient lists stop early (the composition locator says "list cut short"); 芪 is missing throughout and a bare 黄 in a list is read as 黃耆; 10 ingredient names (草果, 鬱金, 三棱, 莪术...) match no Bencao Beiyao herb and are left out, as `curate.py` reports. Appended formulas (附方, "本方加...") are not extracted.

Rebuild from the sources:

```
python3 tools/ingest/fetch_raw.py GUT-SHANGHAN https://www.gutenberg.org/cache/epub/24272/pg24272.txt
python3 tools/ingest/fetch_raw.py GUT-BENCAO-BEIYAO https://www.gutenberg.org/cache/epub/26888/pg26888.txt
python3 tools/ingest/fetch_raw.py WS-JINGUI "https://zh.wikisource.org/w/index.php?title=金匱要略&action=raw" --name jingui.wiki
python3 tools/ingest/fetch_raw.py WS-ZJDC "https://zh.wikisource.org/w/index.php?title=針灸大成/卷八&action=raw" --name 卷八.wiki
python3 tools/ingest/fetch_raw.py WS-ZJDC "https://zh.wikisource.org/w/index.php?title=針灸大成/卷九&action=raw" --name 卷九.wiki
python3 tools/ingest/fetch_raw.py WS-YFJJ "https://zh.wikisource.org/w/index.php?title=醫方集解&action=raw" --name index.wiki
python3 tools/ingest/fetch_raw.py ACUATLAS https://acupointatlas.com/data/acupoints.json
python3 tools/ingest/fetch_raw.py WHO-ISTTCM-2022 "https://iris.who.int/server/api/core/bitstreams/02be07cf-ef55-4ae2-9184-ded49210aa05/content" --name who_isttcm_2022.pdf
python3 tools/ingest/who2022.py     # needs pdftotext (poppler-utils)
cd tools/ingest/classics
python3 shanghan.py && python3 jingui.py && python3 bencao_beiyao.py && python3 zjdc.py && python3 yifang.py && python3 curate.py
```

`curate.py` never overwrites a row the clinician marked `reviewed` or `approved`.

## Patient interview prototype (`app/interview/`)

A Hebrew intake interview that runs in the browser with no server and no LLM: open `app/interview/index.html`. The patient answers an intake form, a red-flag screen, a medications question and a free-text description, then yes/no questions; the clinician enters tongue and pulse and sees a draft `diagnostic_report.v1` with up to five candidate WHO 2022 patterns, the evidence for and against each, and the safety flags.

| Path | What it holds |
| --- | --- |
| `kb/lexicon/interview_features.yaml` | 120 findings (symptoms, tongue, pulse): the Hebrew question, Hebrew words for free text, and English phrases that link each finding to WHO 2022 patterns |
| `kb/lexicon/interview_safety.yaml` | Red-flag questions and words (category A), constraint words such as anticoagulants (category C), the emergency message |
| `tools/interview/build_interview.py` | Derives the pattern-finding links from the WHO text and writes `app/interview/kb.js` |
| `app/interview/engine.js` | Free-text extraction, safety screen, scoring, next-question choice, report |

How it decides, for now: every derived link has the same placeholder weight (`defaults.weight` in the lexicon), and a pattern's score is the overlap between the patient's findings and the pattern's findings, minus half a point per finding the patient denied. Up to fifteen screening questions go to everyone (fewer when the free text already answered them); up to twelve more are chosen to split the leading candidates. Everything here is a draft: the Hebrew wording, the links and the weights need the clinician's review, and the red-flag screen is keyword matching, not the LLM Safety Monitor.

```
python3 tools/interview/build_interview.py                        # after editing the lexicon or syndromes
python3 tools/interview/build_interview.py --standalone out.html  # one self-contained file
```

### Sample cases

The "מילוי מקרה לדוגמה" button runs a sample patient through the interview. `app/interview/demo_cases.js` holds 16 curated cases (textbook presentations written for the prototype, not real patients: liver yang, spleen qi, kidney yang and yin, wind-cold, damp-heat in the bladder, blood stasis in the uterus, a pregnancy case, a chest-pain case that must stop the interview, and more), each with the WHO 2022 patterns a clinician would accept. "תרחיש אקראי מתבנית במאגר" builds a case from one pattern's own links, so it checks the engine against its own data, not against clinical judgement. The clinician view then shows which pattern the case was written for and where it ranked.

```
node tools/interview/eval_scenarios.js 300   # rank of the expected pattern for every curated case and 300 random ones
```

## Treatment plan step (`app/interview/treatment.js`)

After the hypotheses, the clinician view shows a draft treatment plan for the leading pattern (or patterns the clinician ticks): treatment principle, acupuncture points, a herbal prescription and shiatsu points, a live safety check, and a follow-up recommendation. The clinician adds and removes points and herbs, sets technique, moxa and gram doses, approves or rejects each suggested link, and saves the plan (`treatment_plan.v1` JSON, kept in the browser and downloadable).

`tools/treatment/build_treatment.py` derives the suggestions and writes `app/interview/treatment_kb.js`. Every link is a draft with its source:

| Suggestion | Derived from |
| --- | --- |
| Treatment principle | WHO 2022 treatment methods (治法) whose definition says "indicated for" a pattern named with the same words |
| Points | AcuAtlas actions that treat the same organ and disorder ("subdues Liver yang"), plus AcuAtlas and 針灸大成 indications that list the pattern's and the patient's findings |
| Herbs | 本草備要 entries whose opening actions name the method ("平肝", "補脾") |
| Base formula | 傷寒論 / 金匱要略 / 醫方集解 formulas (469) carried by those herbs; 醫方集解 formulas whose indications name the pattern's organ and disorder (治脾胃虛弱 for spleen qi deficiency, quoted with its source), with a bonus when the book's category treats it (補養之劑 for a deficiency); clauses and indications describing the findings add to it. 367 of the 423 patterns get a formula (296 with the Han classics alone); liver yang rising still gets none |

The safety check runs the 150 draft rules in `kb/curation/safety_rules.yaml` (pregnancy, 十八反/十九畏, toxic herbs, 禁針/禁灸 points), the AcuAtlas needling cautions, and the medication answers. Rules for anticoagulants, implanted devices, organ disease and allergy are draft heuristics without a source and say so. No gram dose is ever suggested; formulas show only their classical doses (三兩).

```
python3 tools/treatment/build_treatment.py   # after editing the KB or the lexicon, before build_interview.py --page
```

### Series of sessions and body map

The clinician can split the plan into 7 or 14 sessions. `series()` in `treatment.js` drafts them: session 1 treats the root of the pattern with the chosen points; the middle sessions keep a core of two chosen points and add up to three points whose indications list one of the patient's findings (one finding per session, preferring points no earlier session used, never a point a pregnancy or no-needling rule names); a 14-session series reassesses at session 7 and tapers at 13; the last session reassesses. Each session has an editable focus, its own safety check, and a figure. This is a scheduling heuristic without a source, for the clinician to edit.

`app/interview/body_map.js` draws schematic front and back figures with the course of each channel used, an arrow for its direction of flow (the order of its point numbers), filled dots for acupuncture and rings for shiatsu. Points are placed by hand-set anchors along each channel and interpolated by point number, so the figure is a map, not an anatomical location; the AcuAtlas location text stays the reference.

When WebGL is available the same points show on a 3D figure: `app/interview/body3d.js` (three.js 0.160 from jsDelivr) loads `app/interview/body.glb`, "[Male base muscular anatomy](https://sketchfab.com/3d-models/male-base-muscular-anatomy-0954aa04666d45aab9633009318f7b66)" by Harshit Prajapati, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (credited under every figure), and draws the channels on both sides with arrows for their flow, filled dots for acupuncture and rings for shiatsu; the clinician rotates and zooms it. The 2D figure stays as the fallback. `build_interview.py --page` copies the model next to the page; `--standalone` embeds it.

`tools/treatment/build_points3d.py` places the points from their AcuAtlas location text and writes `app/interview/points3d.js`. Landmarks were measured on the model (umbilicus, nipple, suprasternal notch, xiphisternal junction, pubic symphysis, C7 and the iliac crest for the vertebral levels, glabella, hairlines and ear apex, axillary fold, cubital and wrist creases, knuckles, patella, popliteal crease, malleoli, heel and toes), and the proportional bone-cun of the standard (8 cun xiphisternal junction to umbilicus, 5 to the pubic symphysis, 4 from the midline to the nipple, 12 from the cubital to the wrist crease, 16 from the popliteal crease to the lateral malleolus, 13 from below the medial tibial condyle to the medial malleolus, ...) is laid on them. A parser reads the distances in the text ("3 cun above the prominence of the medial malleolus", "level with the lower edge of the L2 spinous process and 1.5 body-cun from the posterior midline", "in the fifth intercostal space, 4 cun lateral to the anterior midline") and the side of the limb it names ("posterior to the medial border of the tibia", "between the palmaris longus and flexor carpi radialis tendons"); cun across the trunk and head are measured along the skin. Texts that name a spot rather than a distance (the hollows of the hand, foot and ankle, the face, the neck) take a position read from the same text by hand in the script. Of the 361 points, 179 are placed by the parser and 182 by hand; points the text does not resolve would fall back to the schematic anchors of `body_map.js`. The channel lines follow the skin between the points, with a few waypoints where the T-pose would let them cut through the armpit or the neck. It is still approximate (one stylised body, proportions rather than a patient's measurements, the arm turned to the T-pose); the AcuAtlas location text shown with every point stays the reference.

```
python3 tools/treatment/build_points3d.py    # after changing the point locations, the landmarks or the model
```

### Hebrew for the Chinese text

Every Chinese string the page shows (pattern, point, herb and formula names, treatment methods, classical doses, herb actions from 本草備要, indications from 針灸大成, clauses from 傷寒論 / 金匱要略, GB/T 16751.2 text, safety notes) is shown in Hebrew first, with the Chinese original next to it and a "מקור" link. Links to Wikisource and Project Gutenberg carry a text fragment (`#:~:text=`), so the browser opens the source page at the quoted words; WHO 2022, GB/T 16751.2 and AcuAtlas link to the document.

The translations are drafts written with Claude and wait for clinician review. They live in `kb/translations/he/*.txt`, one `chinese|hebrew` pair per line; correct a line there and rebuild. `tools/treatment/build_he.py` writes `app/interview/he_dict.js` with only the strings the page uses (`--check` fails if one is missing); `app/interview/i18n.js` looks them up, renders 十八反/十九畏 notes from the herb names, and builds the source links.

```
python3 tools/treatment/build_he.py          # after editing kb/translations/he or rebuilding the KB files
```

## Run

```
pip install -r requirements.txt
python3 -m pytest -q
python3 tools/build.py            # validate and build
createdb tcm_kb && psql tcm_kb -f kb/schema/001_core.sql -f build/seed.sql
```
