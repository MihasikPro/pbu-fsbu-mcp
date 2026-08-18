PRAGMA foreign_keys = ON;

CREATE TABLE standard (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL CHECK (kind IN ('ФСБУ', 'ПБУ')),
    number         TEXT NOT NULL,
    year           INTEGER NOT NULL,
    title          TEXT NOT NULL,
    order_date     TEXT NOT NULL,
    order_no       TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to   TEXT,
    superseded_by  TEXT,
    source_url     TEXT NOT NULL
);

CREATE TABLE edition (
    id             TEXT PRIMARY KEY,
    standard_id    TEXT NOT NULL REFERENCES standard(id),
    edition_no     INTEGER NOT NULL,
    amending_order TEXT,
    effective_from TEXT NOT NULL,
    UNIQUE (standard_id, edition_no)
);

CREATE TABLE clause (
    id          TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL REFERENCES standard(id),
    edition_id  TEXT NOT NULL REFERENCES edition(id),
    path        TEXT NOT NULL,
    parent_path TEXT,
    heading     TEXT,
    text        TEXT NOT NULL,
    UNIQUE (edition_id, path)
);

CREATE INDEX idx_clause_edition ON clause(edition_id);
CREATE INDEX idx_edition_standard ON edition(standard_id, effective_from);

-- mapping / its_link / crosslink key on (standard_id, clause_path) rather than
-- clause.id (which embeds the edition, e.g. `fsbu-6-2020@1#12`). A projection is
-- a statement about the norm, not about one edition's wording: it must keep
-- resolving after an amendment creates a fresh set of clause rows, instead of
-- silently going dark because the edition-qualified id it pointed at is gone.
-- `edition_from` is the earliest edition (by `edition.edition_no`) the row applies
-- to; NULL means "since the standard's first edition". There is no `edition_to` -
-- a later override is expressed as a second row with a later `edition_from`.
CREATE TABLE mapping (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_id  TEXT NOT NULL REFERENCES standard(id),
    clause_path  TEXT NOT NULL,
    edition_from INTEGER,
    config       TEXT NOT NULL,
    version_from TEXT,
    kind         TEXT NOT NULL,
    object_ref   TEXT NOT NULL,
    note         TEXT,
    confidence   INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    -- 0 until a human reviewer edits the source YAML by hand; the builder never
    -- writes 1 on its own. DEFAULT 0 so a hand-crafted INSERT that omits the
    -- column (as tests do) still lands on the safe "unverified" side.
    verified     INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1))
);

CREATE INDEX idx_mapping_clause ON mapping(standard_id, clause_path);
CREATE INDEX idx_mapping_object ON mapping(config, object_ref);

-- Catalogue of 1C configuration objects a mapping row may reference, mirrored
-- from `data/sources/objects/<config>.yaml` (see `pbu_fsbu_mcp.objects`) so
-- that resolving a human-readable presentation at query time needs no access
-- to the YAML sources - the SQLite file is the corpus's only runtime input.
-- Keyed on (config, ref) rather than ref alone: `mapping.config` already
-- shows the catalogue is per-configuration, and two configurations are free
-- to reuse the same object reference for unrelated objects.
CREATE TABLE config_object (
    config       TEXT NOT NULL,
    ref          TEXT NOT NULL,
    kind         TEXT NOT NULL,
    presentation TEXT NOT NULL,
    PRIMARY KEY (config, ref)
);

CREATE TABLE its_link (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_id  TEXT NOT NULL REFERENCES standard(id),
    clause_path  TEXT NOT NULL,
    edition_from INTEGER,
    its_id       TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    -- Same rule as mapping.verified above.
    verified     INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1))
);

CREATE INDEX idx_its_clause ON its_link(standard_id, clause_path);

CREATE TABLE crosslink (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    from_standard     TEXT NOT NULL REFERENCES standard(id),
    from_clause_path  TEXT NOT NULL,
    from_edition_from INTEGER,
    to_standard       TEXT NOT NULL REFERENCES standard(id),
    to_clause_path    TEXT NOT NULL,
    to_edition_from   INTEGER,
    kind              TEXT NOT NULL CHECK (kind IN ('заменён', 'аналог', 'отсылка'))
);

CREATE INDEX idx_crosslink_from ON crosslink(from_standard, from_clause_path);
CREATE INDEX idx_crosslink_to ON crosslink(to_standard, to_clause_path);

CREATE TABLE standard_crosslink (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_standard  TEXT NOT NULL REFERENCES standard(id),
    to_standard    TEXT NOT NULL REFERENCES standard(id),
    kind           TEXT NOT NULL CHECK (kind IN ('заменён', 'аналог', 'отсылка'))
);

CREATE INDEX idx_standard_crosslink_from ON standard_crosslink(from_standard);

CREATE TABLE corpus_meta (
    built_at             TEXT NOT NULL,
    registry_hash        TEXT NOT NULL,
    source_snapshot_date TEXT NOT NULL
);

CREATE VIRTUAL TABLE clause_fts USING fts5(
    clause_id UNINDEXED,
    lemmas,
    tokenize = 'unicode61'
);
