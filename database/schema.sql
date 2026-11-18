-- PostgreSQL 14+
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE exam_status   AS ENUM ('draft', 'published', 'archived');
CREATE TYPE scan_status   AS ENUM ('received', 'graded', 'needs_review', 'failed');
CREATE TYPE mark_status   AS ENUM ('blank', 'single', 'multiple', 'ambiguous');
CREATE TYPE answer_source AS ENUM ('omr', 'human');

CREATE TABLE teachers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  name          text NOT NULL,
  password_hash text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE classes (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  name       text NOT NULL,
  year       int
);

CREATE TABLE students (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  class_id   uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  name       text NOT NULL,
  enrollment text,                                   -- matrícula
  UNIQUE (class_id, enrollment)
);

CREATE TABLE exams (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  title      text NOT NULL,
  status     exam_status NOT NULL DEFAULT 'draft',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Cada versão é um SNAPSHOT IMUTÁVEL depois de impressa: o QR aponta para (exam_id, version).
CREATE TABLE exam_versions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_id     uuid NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  version     int  NOT NULL,
  content     jsonb NOT NULL,        -- questões, alternativas, imagens (saída do editor WYSIWYG)
  style       jsonb NOT NULL,        -- fontes, colunas, espaçamentos (só afeta as páginas da prova)
  grid_spec   jsonb NOT NULL,        -- AnswerGridSpec do cartão-resposta
  answer_key  jsonb NOT NULL,        -- {"1":"B","2":["A","C"],"3":null}  (null = questão anulada)
  weights     jsonb,                 -- {"1":2.0}  (padrão 1.0)
  exam_pdf_url text,
  locked_at   timestamptz,           -- preenchido na 1ª impressão
  UNIQUE (exam_id, version)
);

CREATE FUNCTION forbid_locked_version_update() RETURNS trigger AS $$
BEGIN
  IF OLD.locked_at IS NOT NULL AND (NEW.grid_spec IS DISTINCT FROM OLD.grid_spec
       OR NEW.answer_key IS DISTINCT FROM OLD.answer_key OR NEW.content IS DISTINCT FROM OLD.content) THEN
    RAISE EXCEPTION 'exam_version % is locked; create a new version', OLD.id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_lock_version BEFORE UPDATE ON exam_versions
  FOR EACH ROW EXECUTE FUNCTION forbid_locked_version_update();

-- Imagens das questões (enviadas pelo editor do painel).
CREATE TABLE exam_assets (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_id    uuid NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  mime       text NOT NULL,
  url        text NOT NULL,          -- object storage
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Um cartão impresso por aluno por versão.
CREATE TABLE sheets (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_version_id uuid NOT NULL REFERENCES exam_versions(id) ON DELETE CASCADE,
  student_id      uuid NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  printed_at      timestamptz,
  UNIQUE (exam_version_id, student_id)
);

CREATE TABLE scans (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sheet_id    uuid REFERENCES sheets(id) ON DELETE SET NULL,
  image_url   text NOT NULL,         -- foto original no object storage (S3/GCS)
  status      scan_status NOT NULL DEFAULT 'received',
  quality     jsonb,                 -- nitidez, brilho, avisos
  error_code  text,                  -- markers_not_found, qr_not_found, ...
  is_current  boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_scans_current_per_sheet ON scans(sheet_id) WHERE is_current;

CREATE TABLE scan_answers (
  scan_id         uuid NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
  question_number int  NOT NULL,
  status          mark_status NOT NULL,
  fills           real[] NOT NULL,   -- escurecimento medido de cada bolha (auditoria)
  marked          text[] NOT NULL DEFAULT '{}',
  final_answer    text,              -- NULL = em branco/indeciso
  source          answer_source NOT NULL DEFAULT 'omr',
  needs_review    boolean NOT NULL DEFAULT false,
  crop_url        text,              -- recorte da linha mostrado no painel de revisão
  reviewed_by     uuid REFERENCES teachers(id),
  PRIMARY KEY (scan_id, question_number)
);
CREATE INDEX idx_scan_answers_review ON scan_answers(scan_id) WHERE needs_review;

CREATE TABLE grades (
  scan_id    uuid PRIMARY KEY REFERENCES scans(id) ON DELETE CASCADE,
  points     numeric(8,2) NOT NULL,
  max_points numeric(8,2) NOT NULL,
  pending    int NOT NULL DEFAULT 0,  -- questões aguardando revisão
  published  boolean NOT NULL DEFAULT false
);
