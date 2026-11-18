-- Versão SQLite (desenvolvimento local). A versão de produção é schema.sql (PostgreSQL).
CREATE TABLE IF NOT EXISTS teachers (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL, password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')));

CREATE TABLE IF NOT EXISTS classes (
  id TEXT PRIMARY KEY, teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE, name TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  name TEXT NOT NULL, enrollment TEXT, UNIQUE (class_id, enrollment));

CREATE TABLE IF NOT EXISTS exams (
  id TEXT PRIMARY KEY, teacher_id TEXT NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  title TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')));

CREATE TABLE IF NOT EXISTS exam_versions (
  id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  content TEXT NOT NULL DEFAULT '{}',      -- editor WYSIWYG (futuro)
  style TEXT NOT NULL DEFAULT '{}',
  grid_spec TEXT NOT NULL, answer_key TEXT NOT NULL, weights TEXT,
  locked_at TEXT,                          -- preenchido na 1ª impressão do cartão
  UNIQUE (exam_id, version));

CREATE TABLE IF NOT EXISTS scans (
  id TEXT PRIMARY KEY, exam_version_id TEXT NOT NULL REFERENCES exam_versions(id) ON DELETE CASCADE,
  student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  is_current INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT (datetime('now')));

CREATE TABLE IF NOT EXISTS scan_answers (
  scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE, question_number INTEGER NOT NULL,
  status TEXT NOT NULL, fills TEXT NOT NULL, marked TEXT NOT NULL DEFAULT '[]',
  final_answer TEXT, source TEXT NOT NULL DEFAULT 'omr', needs_review INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0, crop_path TEXT, reviewed_by TEXT,
  PRIMARY KEY (scan_id, question_number));

-- Imagens das questões (enviadas pelo editor). O arquivo fica em DATA_DIR/assets/<exam_id>/<id>.<ext>
CREATE TABLE IF NOT EXISTS exam_assets (
  id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  mime TEXT NOT NULL, path TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')));
