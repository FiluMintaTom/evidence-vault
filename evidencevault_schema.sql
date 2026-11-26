-- Evidence Vault - database schema (SQLite)
-- Based on the ER diagram in the DBMS project deck (slide 12).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
    case_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    case_name    TEXT NOT NULL,
    case_type    TEXT,
    description  TEXT,
    date_opened  DATE NOT NULL,
    date_closed  DATE,
    status       TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Closed'))
);

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id          INTEGER NOT NULL REFERENCES cases(case_id),
    name             TEXT NOT NULL,
    email            TEXT,
    phone            TEXT,
    role             TEXT NOT NULL CHECK (role IN ('Investigator', 'Analyst', 'Admin')),
    description      TEXT,
    start_date       DATE,
    end_date         DATE,
    status           TEXT NOT NULL CHECK (status IN ('Active', 'Inactive', 'Completed'))
);

CREATE TABLE IF NOT EXISTS evidence_types (
    evidence_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name        TEXT NOT NULL UNIQUE CHECK (type_name IN ('File', 'Image', 'Video', 'Log', 'Device')),
    description      TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id          INTEGER NOT NULL REFERENCES cases(case_id),
    investigation_id INTEGER NOT NULL REFERENCES investigations(investigation_id),
    evidence_type_id INTEGER NOT NULL REFERENCES evidence_types(evidence_type_id),
    file_name        TEXT NOT NULL,
    description      TEXT,
    hash_value       TEXT,
    date_collected   DATE NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('Collected', 'Under Examination', 'Analysed', 'Archived'))
);

-- Storage is 1:1 with evidence in the first version (UNIQUE enforces it).
CREATE TABLE IF NOT EXISTS storage (
    storage_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id   INTEGER NOT NULL UNIQUE REFERENCES evidence(evidence_id),
    location      TEXT NOT NULL,
    storage_type  TEXT NOT NULL CHECK (storage_type IN ('Server', 'Cloud', 'Local')),
    access_status TEXT NOT NULL DEFAULT 'Available' CHECK (access_status IN ('Available', 'Restricted'))
);

CREATE TABLE IF NOT EXISTS chain_of_custody (
    custody_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id      INTEGER NOT NULL REFERENCES evidence(evidence_id),
    investigation_id INTEGER NOT NULL REFERENCES investigations(investigation_id),
    action           TEXT NOT NULL CHECK (action IN ('Collected', 'Transferred', 'Examined', 'Stored')),
    date_time        TEXT NOT NULL,
    remarks          TEXT
);
