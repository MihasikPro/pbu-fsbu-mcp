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

CREATE TABLE mapping (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    clause_id    TEXT NOT NULL REFERENCES clause(id),
    config       TEXT NOT NULL,
    version_from TEXT,
    kind         TEXT NOT NULL,
    object_ref   TEXT NOT NULL,
    note         TEXT,
    confidence   INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100)
);

CREATE INDEX idx_mapping_clause ON mapping(clause_id);
CREATE INDEX idx_mapping_object ON mapping(config, object_ref);

CREATE TABLE its_link (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    clause_id TEXT NOT NULL REFERENCES clause(id),
    its_id    TEXT NOT NULL,
    title     TEXT NOT NULL,
    summary   TEXT NOT NULL
);

CREATE INDEX idx_its_clause ON its_link(clause_id);

CREATE TABLE crosslink (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_clause TEXT NOT NULL REFERENCES clause(id),
    to_clause   TEXT NOT NULL REFERENCES clause(id),
    kind        TEXT NOT NULL CHECK (kind IN ('заменён', 'аналог', 'отсылка'))
);

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
