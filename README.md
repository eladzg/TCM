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

## Rules the build enforces

- IDs follow fixed patterns: `LR3` (WHO point code, no hyphen), `CH.LR`, `SYN.LR.YANG_RISING`, `HERB.GAN_CAO`, `FORM.GUI_ZHI_TANG`.
- A source whose `license_class` is not allowed in `kb/config.yaml` fails the build. Sacred Lotus and American Dragon are registered as `prohibited`.
- A clinical field without a source ref fails the build.
- Only `approved` rows become chunks. Chunk IDs are a hash of entity, facet and text, so unchanged rows keep their IDs across versions.

## Run

```
pip install -r requirements.txt
python3 -m pytest -q
python3 tools/build.py            # validate and build
createdb tcm_kb && psql tcm_kb -f kb/schema/001_core.sql -f build/seed.sql
```
