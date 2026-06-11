-- Meta-Learning Engine Schema
-- SQLite 3.x
-- 7 张表：users, tracks, knowledge_nodes, review_history, assessment_log, learning_journal, node_dependencies

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. Users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    display_name TEXT    NOT NULL DEFAULT '',
    config       TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(config)),
    created_at   TEXT    NOT NULL DEFAULT (date('now')),
    updated_at   TEXT    NOT NULL DEFAULT (date('now'))
);

-- ============================================================
-- 2. Learning Tracks (学习路线)
-- ============================================================
CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    target_type     TEXT    NOT NULL CHECK (target_type IN ('exam', 'applied', 'interest')),
    status          TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'archived')),
    priority        INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    current_state   TEXT    NOT NULL DEFAULT 'init' CHECK (current_state IN ('init', 'diagnosis', 'teaching', 'assessment', 'practice', 'completed')),
    workflow_context TEXT   NOT NULL DEFAULT '{}' CHECK (json_valid(workflow_context)),
    created_at      TEXT    NOT NULL DEFAULT (date('now')),
    updated_at      TEXT    NOT NULL DEFAULT (date('now'))
);
CREATE INDEX IF NOT EXISTS idx_tracks_user_status ON tracks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tracks_user_priority ON tracks(user_id, priority);

-- ============================================================
-- 3. Knowledge Nodes (知识节点)
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id      INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    parent_id     INTEGER REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    name          TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    importance    INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    current_level INTEGER NOT NULL DEFAULT 1 CHECK (current_level BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending', 'mastered', 'archived')),
    ef            REAL    NOT NULL DEFAULT 2.5 CHECK (ef >= 1.3),
    interval      INTEGER NOT NULL DEFAULT 0 CHECK (interval >= 0),
    repetitions   INTEGER NOT NULL DEFAULT 0 CHECK (repetitions >= 0),
    next_review   TEXT,
    created_at    TEXT    NOT NULL DEFAULT (date('now')),
    updated_at    TEXT    NOT NULL DEFAULT (date('now'))
);
CREATE INDEX IF NOT EXISTS idx_nodes_track_status ON knowledge_nodes(track_id, status);
CREATE INDEX IF NOT EXISTS idx_nodes_next_review ON knowledge_nodes(next_review);

-- ============================================================
-- 4. Review History (复习历史)
-- ============================================================
CREATE TABLE IF NOT EXISTS review_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    quality         INTEGER NOT NULL CHECK (quality BETWEEN 0 AND 5),
    ef_after        REAL    NOT NULL CHECK (ef_after >= 1.3),
    interval_after  INTEGER NOT NULL CHECK (interval_after >= 0),
    reviewed_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_node ON review_history(node_id);
CREATE INDEX IF NOT EXISTS idx_reviews_date ON review_history(reviewed_at);

-- ============================================================
-- 5. Assessment Log (评估记录)
-- ============================================================
CREATE TABLE IF NOT EXISTS assessment_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    track_id        INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    node_id         INTEGER REFERENCES knowledge_nodes(id) ON DELETE SET NULL,
    level_before    INTEGER NOT NULL CHECK (level_before BETWEEN 1 AND 5),
    level_after     INTEGER NOT NULL CHECK (level_after BETWEEN 1 AND 5),
    methods         TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(methods)),
    duration_minutes INTEGER DEFAULT 0,
    fake_signals    TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(fake_signals)),
    notes           TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_assessment_user_track ON assessment_log(user_id, track_id);
CREATE INDEX IF NOT EXISTS idx_assessment_date ON assessment_log(created_at);

-- ============================================================
-- 6. Learning Journal (学习日志)
-- ============================================================
CREATE TABLE IF NOT EXISTS learning_journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            TEXT    NOT NULL,
    focus_minutes   INTEGER NOT NULL DEFAULT 0 CHECK (focus_minutes >= 0),
    diffuse_minutes INTEGER NOT NULL DEFAULT 0 CHECK (diffuse_minutes >= 0),
    topics          TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(topics)),
    methods         TEXT    NOT NULL DEFAULT '[]' CHECK (json_valid(methods)),
    track_minutes   TEXT    NOT NULL DEFAULT '{}' CHECK (json_valid(track_minutes)),
    highlights      TEXT    NOT NULL DEFAULT '',
    struggles       TEXT    NOT NULL DEFAULT '',
    tomorrow_plan   TEXT    NOT NULL DEFAULT '',
    UNIQUE(user_id, date)
);

-- ============================================================
-- 7. Node Dependencies (节点依赖)
-- ============================================================
CREATE TABLE IF NOT EXISTS node_dependencies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id       INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    depends_on_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    relation_type TEXT    NOT NULL DEFAULT 'prerequisite' CHECK (relation_type IN ('prerequisite', 'related', 'reference')),
    UNIQUE(node_id, depends_on_id)
);
CREATE INDEX IF NOT EXISTS idx_deps_node ON node_dependencies(node_id);
CREATE INDEX IF NOT EXISTS idx_deps_depends ON node_dependencies(depends_on_id);

-- ============================================================
-- 8. FTS5 Full-Text Search (external content table)
-- ============================================================
-- Note: The underlying columns (content, tags) are added by migration in database.py.
-- This FTS table is created after columns exist.

-- FTS virtual table (created after migration ensures columns exist)
-- CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
--     name, content, tags, source_title,
--     content='knowledge_nodes',
--     content_rowid='id',
--     tokenize='unicode61'
-- );
--
-- Triggers to keep FTS in sync with knowledge_nodes:
-- CREATE TRIGGER IF NOT EXISTS knowledge_fts_insert AFTER INSERT ON knowledge_nodes BEGIN
--     INSERT INTO knowledge_fts(rowid, name, content, tags, source_title)
--     VALUES (new.id, new.name, new.content, new.tags, new.source_title);
-- END;
--
-- CREATE TRIGGER IF NOT EXISTS knowledge_fts_delete AFTER DELETE ON knowledge_nodes BEGIN
--     INSERT INTO knowledge_fts(knowledge_fts, rowid, name, content, tags, source_title)
--     VALUES ('delete', old.id, old.name, old.content, old.tags, old.source_title);
-- END;
--
-- CREATE TRIGGER IF NOT EXISTS knowledge_fts_update AFTER UPDATE ON knowledge_nodes BEGIN
--     INSERT INTO knowledge_fts(knowledge_fts, rowid, name, content, tags, source_title)
--     VALUES ('delete', old.id, old.name, old.content, old.tags, old.source_title);
--     INSERT INTO knowledge_fts(rowid, name, content, tags, source_title)
--     VALUES (new.id, new.name, new.content, new.tags, new.source_title);
-- END;
