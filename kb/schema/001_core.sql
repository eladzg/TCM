-- Canonical knowledge-base tables (architecture doc, section 4.1).
-- Every clinical row carries kb_version, a review status and field-level source refs.

CREATE TABLE sources (
    source_id      text PRIMARY KEY,
    title          text NOT NULL,
    edition        text,
    url            text,
    license        text NOT NULL,
    license_class  text NOT NULL CHECK (license_class IN
                     ('public_domain', 'open', 'attribution', 'non_commercial', 'internal_only', 'prohibited')),
    retrieved_at   date,
    sha256         text
);

CREATE TYPE review_status AS ENUM ('draft', 'reviewed', 'approved');

CREATE TABLE regions (
    region_code       text PRIMARY KEY,           -- e.g. HEAD.TEMPORAL
    name_en           text NOT NULL,
    name_he           text,
    laterality_allowed boolean NOT NULL DEFAULT true,
    status            review_status NOT NULL DEFAULT 'draft',
    kb_version        text NOT NULL
);

CREATE TABLE channels (
    channel_id     text PRIMARY KEY,              -- e.g. CH.GB
    name_en        text NOT NULL,
    name_pinyin    text NOT NULL,
    name_zh        text,
    name_he        text,
    paired_organ   text,
    six_channel_layer text,
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL
);

CREATE TABLE channel_trajectory (
    channel_id   text NOT NULL REFERENCES channels,
    seq          integer NOT NULL,
    region_code  text NOT NULL REFERENCES regions,
    PRIMARY KEY (channel_id, seq)
);

CREATE TABLE points (
    point_id       text PRIMARY KEY,              -- WHO code without hyphen, e.g. LR3
    channel_id     text REFERENCES channels,      -- null for extra points
    name_pinyin    text NOT NULL,
    name_zh        text,
    name_en        text,
    name_he        text,
    location       text,
    actions        text,
    indications    text,
    needling_notes text,
    cautions       text,
    classical      text,                          -- original-language passage (e.g. Zhenjiu Dacheng)
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL
);

CREATE TABLE manifestations (
    manifestation_id text PRIMARY KEY,            -- e.g. MAN.HEADACHE
    term_en        text NOT NULL,
    term_zh        text,
    definition     text,
    kind           text NOT NULL CHECK (kind IN ('symptom', 'sign', 'tongue', 'pulse')),
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL
);

CREATE TABLE syndromes (
    syndrome_id    text PRIMARY KEY,              -- e.g. SYN.LR.YANG_RISING
    name_en        text NOT NULL,
    name_pinyin    text,
    name_zh        text,
    name_he        text,
    category       text,                          -- WHO 2022 pattern group, e.g. Patterns of the liver system
    presentation   text,                          -- "Characterized by ..." clinical picture
    aetiology      text,
    tongue         text,
    pulse          text,
    treatment_principle text,
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL
);

CREATE TABLE syndrome_manifestation (
    syndrome_id      text NOT NULL REFERENCES syndromes,
    manifestation_id text NOT NULL REFERENCES manifestations,
    weight           numeric NOT NULL CHECK (weight > 0),
    essential        boolean NOT NULL DEFAULT false,
    PRIMARY KEY (syndrome_id, manifestation_id)
);

CREATE TABLE herbs (
    herb_id        text PRIMARY KEY,              -- e.g. HERB.GAN_CAO
    name_pinyin    text NOT NULL,
    name_zh        text,
    name_latin     text,
    name_he        text,
    nature         text,
    flavour        text,
    channels_entered text[],
    actions        text,
    dose_min_g     numeric,
    dose_max_g     numeric,
    pregnancy_caution text,
    classical      text,                          -- original-language entry (e.g. Bencao Beiyao)
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL,
    CHECK (dose_min_g IS NULL OR dose_max_g IS NULL OR dose_min_g <= dose_max_g)
);

CREATE TABLE formulas (
    formula_id     text PRIMARY KEY,              -- e.g. FORM.GUI_ZHI_TANG
    name_pinyin    text NOT NULL,
    name_zh        text,
    name_en        text,
    indications    text,
    modifications  text,
    classical      text,                          -- preparation and administration as written
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL
);

CREATE TABLE formula_herb (
    formula_id     text NOT NULL REFERENCES formulas,
    herb_id        text NOT NULL REFERENCES herbs,
    dose_original  text,                          -- as written in the source, e.g. 三兩
    dose_min_g     numeric,
    dose_max_g     numeric,
    PRIMARY KEY (formula_id, herb_id)
);

CREATE TABLE syndrome_point   (syndrome_id text REFERENCES syndromes, point_id text REFERENCES points,     PRIMARY KEY (syndrome_id, point_id));
CREATE TABLE syndrome_formula (syndrome_id text REFERENCES syndromes, formula_id text REFERENCES formulas, PRIMARY KEY (syndrome_id, formula_id));

CREATE TABLE safety_rules (
    rule_id        text PRIMARY KEY,
    condition      text NOT NULL CHECK (condition IN ('pregnancy', 'anticoagulant', 'device', 'age', 'other')),
    entity_ids     text[] NOT NULL,
    severity       text NOT NULL CHECK (severity IN ('contraindicated', 'caution')),
    note           text,
    status         review_status NOT NULL DEFAULT 'draft',
    kb_version     text NOT NULL
);

CREATE TABLE lexicon_he_en (
    lexicon_id       text PRIMARY KEY,
    term_he          text NOT NULL,
    synonyms_he      text[] NOT NULL DEFAULT '{}',
    manifestation_id text REFERENCES manifestations,
    default_region   text REFERENCES regions,
    status           review_status NOT NULL DEFAULT 'draft',
    kb_version       text NOT NULL
);

-- Field-level provenance: which source backs which field of which row.
CREATE TABLE source_refs (
    entity_id   text NOT NULL,
    field       text NOT NULL,
    source_id   text NOT NULL REFERENCES sources,
    locator     text NOT NULL,                    -- page, chapter or section
    quote       text,                             -- original-language passage
    PRIMARY KEY (entity_id, field, source_id, locator)
);

CREATE TABLE external_ids (
    entity_id   text NOT NULL,
    system      text NOT NULL,                    -- ICD11, SNOMEDCT, SYMMAP, WHO2022
    code        text NOT NULL,
    PRIMARY KEY (entity_id, system)
);

CREATE TABLE chunks (
    chunk_id    text PRIMARY KEY,                 -- sha256(entity_id|facet|text), first 16 hex chars
    entity_id   text NOT NULL,
    facet       text NOT NULL,
    text        text NOT NULL,
    source_ids  text[] NOT NULL,
    kb_version  text NOT NULL
);
