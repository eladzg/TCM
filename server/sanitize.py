"""What the patient may send, and what leaves the clinic in an export."""
import secrets

MAX_TEXT = 4000
MAX_ITEMS = 600
PATIENT_SOURCES = {"question", "free_text"}
SEXES = {"F", "M"}
PREGNANCY = {"yes", "no", "unknown", "na"}


class Invalid(ValueError):
    pass


def _text(v, limit=MAX_TEXT):
    if v is None:
        return ""
    if not isinstance(v, str):
        raise Invalid("expected text")
    return v[:limit]


def _id(v):
    if not isinstance(v, str) or not v or len(v) > 80 or not all(ch.isalnum() or ch in "._-" for ch in v):
        raise Invalid("bad id")
    return v


def intake_state(raw):
    """Keep only the fields of the interview engine's state that the patient side produces.

    The patient cannot set clinician answers, tongue or pulse: those come from the clinician side."""
    if not isinstance(raw, dict):
        raise Invalid("state must be an object")
    p = raw.get("patient") or {}
    if not isinstance(p, dict):
        raise Invalid("patient must be an object")
    age = p.get("age")
    if age is not None and (not isinstance(age, (int, float)) or not 0 < age <= 120):
        raise Invalid("bad age")
    patient = {
        "age": int(age) if age is not None else None,
        "sex": p.get("sex") if p.get("sex") in SEXES else None,
        "pregnancy": p.get("pregnancy") if p.get("pregnancy") in PREGNANCY else None,
    }
    if p.get("medications"):
        patient["medications"] = _text(p["medications"])
    answers = {}
    raw_answers = raw.get("answers") or {}
    if not isinstance(raw_answers, dict) or len(raw_answers) > MAX_ITEMS:
        raise Invalid("bad answers")
    for fid, a in raw_answers.items():
        if not isinstance(a, dict) or a.get("source") not in PATIENT_SOURCES:
            continue
        if a.get("value") not in (True, False, None):
            raise Invalid("bad answer value")
        answers[_id(fid)] = {"value": a.get("value"), "source": a["source"], "quote": _text(a.get("quote"))}
    flags = []
    for f in (raw.get("flags") or [])[:50]:
        if isinstance(f, dict):
            flags.append({k: _text(f.get(k), 500) for k in ("id", "category", "gloss_en", "verbatim_he") if f.get(k) is not None})
    transcript = []
    for t in (raw.get("transcript") or [])[:MAX_ITEMS]:
        if isinstance(t, dict) and t.get("role") in ("patient", "system"):
            item = {"role": t["role"], "text": _text(t.get("text"))}
            for k in ("context", "feature"):
                if t.get(k):
                    item[k] = _text(t[k], 80)
            transcript.append(item)
    asked = [_id(x) for x in (raw.get("asked") or [])[:MAX_ITEMS]]
    adaptive = raw.get("adaptiveAsked") or 0
    if not isinstance(adaptive, int) or not 0 <= adaptive <= MAX_ITEMS:
        raise Invalid("bad adaptiveAsked")
    return {
        "patient": patient, "answers": answers, "asked": asked, "adaptiveAsked": adaptive,
        "flags": flags, "halted": bool(raw.get("halted")),
        "tongueObserved": False, "pulseObserved": False, "transcript": transcript,
    }


# Free text that may name or describe the person, and so stays inside the clinic.
FREE_TEXT_KEYS = {"transcript", "quote", "verbatim_he", "medications", "medications_he", "note_he",
                  "notes_he", "clinician_note_he", "text_he", "identity"}


def scrub(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in FREE_TEXT_KEYS:
                continue
            if k == "age" and isinstance(v, (int, float)):
                lo = int(v) // 10 * 10
                out["age_band"] = f"{lo}-{lo + 9}"
                continue
            out[k] = scrub(v)
        return out
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def export(store, keep_ids=False):
    """Clinical documents with free text removed, ages in ten-year bands, no identity, and (unless
    keep_ids) a fresh random id per record that is not stored anywhere."""
    alias = {}
    out = {}
    for rid, kind, doc in store.all_docs():
        if rid not in alias:
            alias[rid] = rid if keep_ids else "X-" + secrets.token_hex(5).upper()
        rec = out.setdefault(alias[rid], {"record": alias[rid]})
        rec.setdefault(kind, []).append({"version": doc["version"], "created_at": doc["created_at"], "data": scrub(doc["data"])})
    # Practice data that carries no free text: MYMOP scores (not the symptom names) and visit counts.
    with store.db() as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name = 'pm_outcomes'").fetchone():
            for r in c.execute("SELECT record_id, at, source, s1, s2, activity, wellbeing FROM pm_outcomes ORDER BY at"):
                if r["record_id"] not in alias:
                    alias[r["record_id"]] = r["record_id"] if keep_ids else "X-" + secrets.token_hex(5).upper()
                rec = out.setdefault(alias[r["record_id"]], {"record": alias[r["record_id"]]})
                rec.setdefault("mymop", []).append({k: r[k] for k in ("at", "source", "s1", "s2", "activity", "wellbeing")})
            for r in c.execute("SELECT record_id, status, COUNT(*) AS n FROM pm_appointments WHERE record_id IS NOT NULL GROUP BY record_id, status"):
                if r["record_id"] in alias:
                    out[alias[r["record_id"]]].setdefault("visits", {})[r["status"]] = r["n"]
    return {"schema_version": "deidentified_export.v1", "free_text_removed": sorted(FREE_TEXT_KEYS),
            "records": list(out.values())}
