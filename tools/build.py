"""Validate the curated YAML knowledge base and build its SQL seed and RAG chunks.

Usage:
    python3 tools/build.py              # validate, write build/seed.sql and build/chunks.jsonl
    python3 tools/build.py --check      # validate only
    python3 tools/build.py --include-drafts   # also chunk draft/reviewed rows (dev only)
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "kb"

# One entry per curation file: table, key, id pattern, foreign keys, fields that need a source,
# and the facets turned into chunks (one chunk per facet, per architecture section 4.1).
ENTITIES = {
    "regions": dict(key="region_code", pattern=r"^[A-Z]+(\.[A-Z_]+)+$", fks={},
                    clinical=[], facets=[]),
    "channels": dict(key="channel_id", pattern=r"^CH\.[A-Z]{2}$", fks={},
                     clinical=["channel_id"], facets=[]),
    "points": dict(key="point_id", pattern=r"^([A-Z]{2}\d{1,2}|EX-[A-Z]{2}\d{1,2})$",
                   fks={"channel_id": "channels"},
                   clinical=["location", "actions", "indications", "needling_notes", "cautions"],
                   facets=["location", "actions", "indications", "cautions"]),
    "manifestations": dict(key="manifestation_id", pattern=r"^MAN\.[A-Z0-9_]+$", fks={},
                           clinical=[], facets=[]),
    "syndromes": dict(key="syndrome_id", pattern=r"^SYN\.[A-Z]{2,3}\.[A-Z0-9_]+$", fks={},
                      clinical=["aetiology", "tongue", "pulse", "treatment_principle"],
                      facets=["aetiology", "tongue", "pulse", "treatment_principle"]),
    "herbs": dict(key="herb_id", pattern=r"^HERB\.[A-Z0-9_]+$", fks={},
                  clinical=["nature", "flavour", "actions", "dose_min_g", "dose_max_g", "pregnancy_caution"],
                  facets=["actions", "dose", "pregnancy_caution"]),
    "formulas": dict(key="formula_id", pattern=r"^FORM\.[A-Z0-9_]+$", fks={},
                     clinical=["indications", "modifications", "composition"],
                     facets=["indications", "composition", "modifications"]),
    "safety_rules": dict(key="rule_id", pattern=r"^SAFE\.[A-Z0-9_]+$", fks={},
                         clinical=["entity_ids"], facets=["note"]),
    "lexicon_he_en": dict(key="lexicon_id", pattern=r"^LEX\.\d{5}$",
                          fks={"manifestation_id": "manifestations", "default_region": "regions"},
                          clinical=[], facets=[]),
}

STATUSES = {"draft", "reviewed", "approved"}
META = {"sources", "status"}


class BuildError(Exception):
    pass


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def load_kb(kb_dir=KB):
    sources = {s["source_id"]: s for s in load_yaml(kb_dir / "sources.yaml")}
    config = load_yaml(kb_dir / "config.yaml")
    rows = {}
    for name in ENTITIES:
        path = kb_dir / "curation" / f"{name}.yaml"
        rows[name] = load_yaml(path) if path.exists() else []
    return sources, config, rows


def validate(sources, config, rows):
    """Return a list of human-readable errors; empty means the KB is consistent."""
    errors = []
    allowed = set(config["allowed_license_classes"])
    ids = {name: set() for name in ENTITIES}

    for name, spec in ENTITIES.items():
        for row in rows[name]:
            rid = row.get(spec["key"])
            where = f"{name}:{rid}"
            if not rid or not re.match(spec["pattern"], str(rid)):
                errors.append(f"{where}: id does not match {spec['pattern']}")
                continue
            if rid in ids[name]:
                errors.append(f"{where}: duplicate id")
            ids[name].add(rid)
            if row.get("status", "draft") not in STATUSES:
                errors.append(f"{where}: unknown status {row.get('status')!r}")

            refs = row.get("sources", [])
            backed = set()
            for ref in refs:
                src = sources.get(ref.get("source_id"))
                if src is None:
                    errors.append(f"{where}: unknown source {ref.get('source_id')!r}")
                    continue
                if src["license_class"] not in allowed:
                    errors.append(f"{where}: source {src['source_id']} is {src['license_class']}, "
                                  f"not allowed by kb/config.yaml")
                if not ref.get("locator"):
                    errors.append(f"{where}: source {src['source_id']} has no locator")
                backed.add(ref.get("field"))
            for field in spec["clinical"]:
                if row.get(field) not in (None, "", []) and field not in backed:
                    errors.append(f"{where}: field {field!r} has no source ref")

    for name, spec in ENTITIES.items():
        for row in rows[name]:
            for field, target in spec["fks"].items():
                value = row.get(field)
                if value and value not in ids[target]:
                    errors.append(f"{name}:{row.get(spec['key'])}: {field} {value!r} not in {target}")

    herb_ids, all_ids = ids["herbs"], set().union(*ids.values())
    for row in rows["formulas"]:
        for item in row.get("composition", []):
            if item.get("herb_id") not in herb_ids:
                errors.append(f"formulas:{row['formula_id']}: herb {item.get('herb_id')!r} not in herbs")
    for row in rows["herbs"]:
        lo, hi = row.get("dose_min_g"), row.get("dose_max_g")
        if lo is not None and hi is not None and lo > hi:
            errors.append(f"herbs:{row['herb_id']}: dose_min_g > dose_max_g")
    for row in rows["safety_rules"]:
        for eid in row.get("entity_ids", []):
            if eid not in all_ids:
                errors.append(f"safety_rules:{row['rule_id']}: entity {eid!r} unknown")
    return errors


def chunk_id(entity_id, facet, text):
    """Deterministic, so an unchanged row keeps its chunk id across KB versions."""
    return hashlib.sha256(f"{entity_id}|{facet}|{text}".encode("utf-8")).hexdigest()[:16]


def facet_text(row, facet):
    if facet == "dose":
        lo, hi = row.get("dose_min_g"), row.get("dose_max_g")
        return f"Dose {lo} to {hi} g" if lo is not None and hi is not None else None
    if facet == "composition":
        parts = [f"{c['herb_id']} {c.get('dose_original', '')}".strip() for c in row.get("composition", [])]
        return "; ".join(parts) or None
    value = row.get(facet)
    return str(value) if value not in (None, "", []) else None


def build_chunks(sources, config, rows, include_drafts=False):
    chunks = []
    for name, spec in ENTITIES.items():
        for row in rows[name]:
            if not include_drafts and row.get("status") != "approved":
                continue
            rid = row[spec["key"]]
            for facet in spec["facets"]:
                text = facet_text(row, facet)
                if not text:
                    continue
                field = "dose_min_g" if facet == "dose" else facet
                src_ids = sorted({r["source_id"] for r in row.get("sources", []) if r.get("field") == field})
                chunks.append({"chunk_id": chunk_id(rid, facet, text), "entity_id": rid, "facet": facet,
                               "text": text, "source_ids": src_ids, "kb_version": config["kb_version"]})
    return chunks


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "ARRAY[" + ", ".join(sql_literal(v) for v in value) + "]::text[]" if value else "'{}'::text[]"
    return "'" + str(value).replace("'", "''") + "'"


def insert(table, record):
    cols = ", ".join(record)
    vals = ", ".join(sql_literal(v) for v in record.values())
    return f"INSERT INTO {table} ({cols}) VALUES ({vals});"


def build_seed(sources, config, rows):
    out = ["BEGIN;"]
    for s in sources.values():
        out.append(insert("sources", {k: s.get(k) for k in ("source_id", "title", "edition", "url",
                                                            "license", "license_class")}))
    version = config["kb_version"]
    for name, spec in ENTITIES.items():
        for row in rows[name]:
            rid = row[spec["key"]]
            record = {k: v for k, v in row.items() if k not in META and k != "composition"}
            record.update(status=row.get("status", "draft"), kb_version=version)
            out.append(insert(name, record))
            for ref in row.get("sources", []):
                out.append(insert("source_refs", {"entity_id": rid, "field": ref["field"],
                                                  "source_id": ref["source_id"], "locator": ref["locator"],
                                                  "quote": ref.get("quote")}))
    for row in rows["formulas"]:
        for item in row.get("composition", []):
            out.append(insert("formula_herb", {"formula_id": row["formula_id"], **item}))
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--include-drafts", action="store_true")
    args = parser.parse_args(argv)

    sources, config, rows = load_kb()
    errors = validate(sources, config, rows)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print(f"{len(errors)} error(s)", file=sys.stderr)
        return 1
    counts = ", ".join(f"{n}={len(r)}" for n, r in rows.items() if r)
    print(f"KB valid ({counts})")
    if args.check:
        return 0

    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    (out / "seed.sql").write_text(build_seed(sources, config, rows), encoding="utf-8")
    chunks = build_chunks(sources, config, rows, args.include_drafts)
    with open(out / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote build/seed.sql and {len(chunks)} chunk(s) to build/chunks.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
