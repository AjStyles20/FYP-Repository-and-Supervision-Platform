-- =====================================================================
-- Baze Project Hub - reference database design (MySQL 8, InnoDB)
-- Version 0.1 - 2026-10-03
--
-- PURPOSE
--   Reference schema for drawing the ER diagram in MySQL Workbench and for
--   guiding the Django models. Django models are the SOURCE OF TRUTH for the
--   real database; do not edit tables in Workbench and in Django at the same
--   time or migrations will drift.
--
-- CONVENTIONS
--   * utf8mb4 everywhere. All tables InnoDB.
--   * is_demo = 1 marks seed/demo rows so they can be purged in one query.
--   * History is preserved: supervisor changes, status changes and edits
--     create new rows. They do not overwrite old values.
--   * audit_log is append-only (triggers at the bottom + restricted grants).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS baze_projecthub
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE baze_projecthub;

-- ---------------------------------------------------------------------
-- 1. Academic structure: University -> Faculty -> Department -> Programme
-- ---------------------------------------------------------------------
CREATE TABLE faculties (
  faculty_id   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(150) NOT NULL UNIQUE,
  is_demo      TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB;

CREATE TABLE departments (
  department_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  faculty_id    INT UNSIGNED NOT NULL,
  name          VARCHAR(150) NOT NULL,
  is_demo       TINYINT(1) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_dept (faculty_id, name),
  CONSTRAINT fk_dept_faculty FOREIGN KEY (faculty_id) REFERENCES faculties (faculty_id)
) ENGINE=InnoDB;

CREATE TABLE programmes (
  programme_id  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  department_id INT UNSIGNED NOT NULL,
  name          VARCHAR(150) NOT NULL,                 -- e.g. Computer Science
  degree_type   VARCHAR(20)  NOT NULL,                 -- e.g. BSc, MSc, LLB (verify real list with Baze)
  is_demo       TINYINT(1) NOT NULL DEFAULT 0,
  UNIQUE KEY uq_prog (department_id, name, degree_type),
  CONSTRAINT fk_prog_dept FOREIGN KEY (department_id) REFERENCES departments (department_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. People and roles
--    NOTE: with Django, authentication fields live in Django's user model.
--    This table shows the logical content only.
-- ---------------------------------------------------------------------
CREATE TABLE users (
  user_id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email         VARCHAR(190) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name     VARCHAR(150) NOT NULL,
  role          ENUM('student','supervisor','coordinator','hod','admin') NOT NULL,
  department_id INT UNSIGNED NULL,
  is_active     TINYINT(1) NOT NULL DEFAULT 1,
  is_demo       TINYINT(1) NOT NULL DEFAULT 0,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_user_dept FOREIGN KEY (department_id) REFERENCES departments (department_id)
) ENGINE=InnoDB;

CREATE TABLE students (
  user_id         INT UNSIGNED PRIMARY KEY,
  student_number  VARCHAR(30) NOT NULL UNIQUE,         -- staff-only visibility in the UI
  programme_id    INT UNSIGNED NOT NULL,
  enrolment_year  SMALLINT UNSIGNED NULL,
  student_status  ENUM('current','fyp_completed','graduated') NOT NULL DEFAULT 'current',
  graduation_year SMALLINT UNSIGNED NULL,
  contact_email   VARCHAR(190) NULL,
  contact_consent TINYINT(1) NOT NULL DEFAULT 0,       -- contact shown publicly ONLY if 1
  CONSTRAINT fk_student_user FOREIGN KEY (user_id) REFERENCES users (user_id),
  CONSTRAINT fk_student_prog FOREIGN KEY (programme_id) REFERENCES programmes (programme_id)
) ENGINE=InnoDB;

CREATE TABLE supervisors (
  user_id       INT UNSIGNED PRIMARY KEY,
  department_id INT UNSIGNED NOT NULL,
  title         VARCHAR(30) NULL,                      -- Dr., Mrs., Prof.
  is_active     TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_sup_user FOREIGN KEY (user_id) REFERENCES users (user_id),
  CONSTRAINT fk_sup_dept FOREIGN KEY (department_id) REFERENCES departments (department_id)
) ENGINE=InnoDB;

-- Each supervisor chooses how they approve projects (no fixed criteria).
CREATE TABLE approval_policies (
  policy_id     INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  supervisor_id INT UNSIGNED NOT NULL,
  mode          ENUM('topic_only','literature_review','working_project') NOT NULL,
  notes         VARCHAR(500) NULL,
  effective_from DATE NOT NULL,
  CONSTRAINT fk_policy_sup FOREIGN KEY (supervisor_id) REFERENCES supervisors (user_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. Projects (one table for current AND archived projects)
-- ---------------------------------------------------------------------
CREATE TABLE projects (
  project_id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  title         VARCHAR(255) NOT NULL,
  description   TEXT NULL,
  project_type  ENUM('undergraduate_fyp','masters_project','dissertation','other') NOT NULL DEFAULT 'undergraduate_fyp',
  programme_id  INT UNSIGNED NOT NULL,
  student_id    INT UNSIGNED NOT NULL,
  status        ENUM('proposed','supervisor_accepted','approved','in_progress',
                     'submitted','defended','corrections_required','completed','archived')
                NOT NULL DEFAULT 'proposed',
  continues_project_id INT UNSIGNED NULL,              -- project this one extends (gap continuation)
  gap_summary   TEXT NULL,                             -- documented gap / future work, captured at HOD sign-off
  proposed_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_at   DATETIME NULL,
  submitted_at  DATETIME NULL,
  defended_at   DATETIME NULL,
  completed_at  DATETIME NULL,
  archived_at   DATETIME NULL,
  is_demo       TINYINT(1) NOT NULL DEFAULT 0,
  FULLTEXT KEY ft_projects (title, description, gap_summary),
  KEY ix_projects_status (status),
  KEY ix_projects_prog (programme_id),
  CONSTRAINT fk_proj_prog    FOREIGN KEY (programme_id) REFERENCES programmes (programme_id),
  CONSTRAINT fk_proj_student FOREIGN KEY (student_id)   REFERENCES students (user_id),
  CONSTRAINT fk_proj_cont    FOREIGN KEY (continues_project_id) REFERENCES projects (project_id)
) ENGINE=InnoDB;

-- Supervisor history: a row per assignment. A change ends one row and adds another.
CREATE TABLE project_supervisors (
  assignment_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id    INT UNSIGNED NOT NULL,
  supervisor_id INT UNSIGNED NOT NULL,
  start_date    DATE NOT NULL,
  end_date      DATE NULL,
  change_reason VARCHAR(255) NULL,
  assigned_by   INT UNSIGNED NOT NULL,                 -- coordinator
  current_flag  TINYINT GENERATED ALWAYS AS (IF(end_date IS NULL, 1, NULL)) STORED,
  UNIQUE KEY uq_one_current (project_id, current_flag),  -- at most ONE current supervisor per project
  KEY ix_ps_sup (supervisor_id),
  CONSTRAINT fk_ps_proj FOREIGN KEY (project_id)    REFERENCES projects (project_id),
  CONSTRAINT fk_ps_sup  FOREIGN KEY (supervisor_id) REFERENCES supervisors (user_id),
  CONSTRAINT fk_ps_by   FOREIGN KEY (assigned_by)   REFERENCES users (user_id)
) ENGINE=InnoDB;

CREATE TABLE project_status_history (
  history_id  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id  INT UNSIGNED NOT NULL,
  from_status VARCHAR(30) NULL,
  to_status   VARCHAR(30) NOT NULL,
  changed_by  INT UNSIGNED NOT NULL,
  reason      VARCHAR(500) NULL,
  changed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_hist_proj (project_id, changed_at),
  CONSTRAINT fk_hist_proj FOREIGN KEY (project_id) REFERENCES projects (project_id),
  CONSTRAINT fk_hist_by   FOREIGN KEY (changed_by) REFERENCES users (user_id)
) ENGINE=InnoDB;

-- Digital replacement for the paper approval form.
CREATE TABLE project_approvals (
  approval_id   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id    INT UNSIGNED NOT NULL,
  stage         ENUM('supervisor_acceptance','coordinator_record','defence_record','hod_signoff') NOT NULL,
  policy_mode   ENUM('topic_only','literature_review','working_project') NULL,  -- supervisor's method at the time
  decision      ENUM('accepted','revision_requested','rejected','recorded','signed') NOT NULL,
  decided_by    INT UNSIGNED NOT NULL,
  comments      VARCHAR(1000) NULL,
  decided_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_appr_proj FOREIGN KEY (project_id) REFERENCES projects (project_id),
  CONSTRAINT fk_appr_by   FOREIGN KEY (decided_by) REFERENCES users (user_id)
) ENGINE=InnoDB;

CREATE TABLE project_documents (
  document_id   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id    INT UNSIGNED NOT NULL,
  uploaded_by   INT UNSIGNED NOT NULL,
  doc_type      ENUM('proposal','report','source_code','slides','other') NOT NULL DEFAULT 'report',
  original_name VARCHAR(255) NOT NULL,
  storage_path  VARCHAR(500) NOT NULL,                 -- file lives on disk, NOT in the database
  mime_type     VARCHAR(100) NOT NULL,
  size_bytes    BIGINT UNSIGNED NOT NULL,
  visibility    ENUM('private','staff','baze_users') NOT NULL DEFAULT 'staff',
  uploaded_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  is_demo       TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_doc_proj FOREIGN KEY (project_id)  REFERENCES projects (project_id),
  CONSTRAINT fk_doc_by   FOREIGN KEY (uploaded_by) REFERENCES users (user_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. Supervision: availability, meetings, records, notices
-- ---------------------------------------------------------------------
CREATE TABLE availability_slots (
  slot_id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  supervisor_id INT UNSIGNED NOT NULL,
  starts_at     DATETIME NOT NULL,
  ends_at       DATETIME NOT NULL,
  venue         VARCHAR(150) NULL,
  status        ENUM('open','booked','cancelled') NOT NULL DEFAULT 'open',
  KEY ix_slot_sup (supervisor_id, starts_at),
  CONSTRAINT fk_slot_sup FOREIGN KEY (supervisor_id) REFERENCES supervisors (user_id),
  CONSTRAINT ck_slot_time CHECK (ends_at > starts_at)
) ENGINE=InnoDB;

CREATE TABLE meetings (
  meeting_id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  project_id    INT UNSIGNED NOT NULL,
  supervisor_id INT UNSIGNED NOT NULL,
  student_id    INT UNSIGNED NOT NULL,
  slot_id       INT UNSIGNED NULL,
  scheduled_at  DATETIME NOT NULL,
  venue         VARCHAR(150) NULL,
  status        ENUM('requested','scheduled','held','missed','cancelled') NOT NULL DEFAULT 'requested',
  requested_by  INT UNSIGNED NOT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_meet_proj (project_id, scheduled_at),
  CONSTRAINT fk_meet_proj FOREIGN KEY (project_id)    REFERENCES projects (project_id),
  CONSTRAINT fk_meet_sup  FOREIGN KEY (supervisor_id) REFERENCES supervisors (user_id),
  CONSTRAINT fk_meet_stu  FOREIGN KEY (student_id)    REFERENCES students (user_id),
  CONSTRAINT fk_meet_slot FOREIGN KEY (slot_id)       REFERENCES availability_slots (slot_id),
  CONSTRAINT fk_meet_req  FOREIGN KEY (requested_by)  REFERENCES users (user_id)
) ENGINE=InnoDB;

-- What happened at a meeting. Both parties can confirm or dispute it.
CREATE TABLE meeting_records (
  record_id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  meeting_id           INT UNSIGNED NOT NULL UNIQUE,
  student_attended     TINYINT(1) NOT NULL,
  last_discussed       VARCHAR(1000) NULL,
  corrections          VARCHAR(1000) NULL,             -- what the student must fix
  project_stage_note   VARCHAR(255) NULL,              -- where the student is in the project
  created_by           INT UNSIGNED NOT NULL,
  created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  student_confirmed_at DATETIME NULL,
  supervisor_confirmed_at DATETIME NULL,
  disputed             TINYINT(1) NOT NULL DEFAULT 0,
  dispute_note         VARCHAR(500) NULL,
  CONSTRAINT fk_rec_meet FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id),
  CONSTRAINT fk_rec_by   FOREIGN KEY (created_by) REFERENCES users (user_id)
) ENGINE=InnoDB;

-- Every edit to a record keeps the old text (edit history with dates).
CREATE TABLE meeting_record_versions (
  version_id   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  record_id    INT UNSIGNED NOT NULL,
  version_no   INT UNSIGNED NOT NULL,
  last_discussed VARCHAR(1000) NULL,
  corrections    VARCHAR(1000) NULL,
  edited_by    INT UNSIGNED NOT NULL,
  edited_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_rec_ver (record_id, version_no),
  CONSTRAINT fk_ver_rec FOREIGN KEY (record_id) REFERENCES meeting_records (record_id),
  CONSTRAINT fk_ver_by  FOREIGN KEY (edited_by) REFERENCES users (user_id)
) ENGINE=InnoDB;

-- Announcements (resources, venue or time changes) with proof of who saw them.
CREATE TABLE notices (
  notice_id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  author_id    INT UNSIGNED NOT NULL,
  project_id   INT UNSIGNED NULL,                      -- NULL = for all of the author's students
  kind         ENUM('update','resource','venue_change','meeting') NOT NULL DEFAULT 'update',
  title        VARCHAR(200) NOT NULL,
  body         TEXT NULL,
  event_at     DATETIME NULL,
  venue        VARCHAR(150) NULL,
  posted_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_notice_author FOREIGN KEY (author_id)  REFERENCES users (user_id),
  CONSTRAINT fk_notice_proj   FOREIGN KEY (project_id) REFERENCES projects (project_id)
) ENGINE=InnoDB;

CREATE TABLE notice_acknowledgements (
  notice_id       INT UNSIGNED NOT NULL,
  user_id         INT UNSIGNED NOT NULL,
  first_seen_at   DATETIME NULL,
  acknowledged_at DATETIME NULL,
  PRIMARY KEY (notice_id, user_id),
  CONSTRAINT fk_ack_notice FOREIGN KEY (notice_id) REFERENCES notices (notice_id),
  CONSTRAINT fk_ack_user   FOREIGN KEY (user_id)   REFERENCES users (user_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 5. Audit log (append-only)
-- ---------------------------------------------------------------------
CREATE TABLE audit_log (
  audit_id    BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  actor_id    INT UNSIGNED NULL,
  action      VARCHAR(60)  NOT NULL,                   -- e.g. project.status_changed
  entity_type VARCHAR(40)  NOT NULL,
  entity_id   VARCHAR(40)  NOT NULL,
  old_value   JSON NULL,
  new_value   JSON NULL,
  ip_address  VARCHAR(45) NULL,
  created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY ix_audit_entity (entity_type, entity_id, created_at),
  KEY ix_audit_actor (actor_id, created_at)
) ENGINE=InnoDB;

DELIMITER $$
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE ON audit_log
FOR EACH ROW BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is append-only';
END$$
CREATE TRIGGER trg_audit_no_delete BEFORE DELETE ON audit_log
FOR EACH ROW BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log is append-only';
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- 6. Least-privilege account for the web application (run as root/admin)
--    The app user can read and insert audit rows but cannot change or delete them.
--    Replace the password and host before use.
-- ---------------------------------------------------------------------
-- CREATE USER 'projecthub_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON baze_projecthub.* TO 'projecthub_app'@'localhost';
-- REVOKE UPDATE, DELETE ON baze_projecthub.audit_log FROM 'projecthub_app'@'localhost';
-- (Django also needs CREATE/ALTER for migrations: use a separate migration user.)

-- ---------------------------------------------------------------------
-- 7. Useful queries
-- ---------------------------------------------------------------------
-- Remove all demo data before the school loads real records:
--   DELETE FROM project_documents WHERE is_demo = 1;  -- then projects, users, etc. (child tables first)
-- Full-text search of the repository:
--   SELECT project_id, title FROM projects
--   WHERE MATCH(title, description, gap_summary) AGAINST ('library catalogue' IN NATURAL LANGUAGE MODE);
-- Supervisor counters (supervising / approved / defended):
--   SELECT ps.supervisor_id,
--          SUM(p.status IN ('proposed','supervisor_accepted','approved','in_progress','submitted')) AS supervising,
--          SUM(p.status IN ('approved','in_progress','submitted','defended','completed','archived')) AS approved,
--          SUM(p.status IN ('defended','completed','archived')) AS defended
--   FROM project_supervisors ps JOIN projects p USING (project_id)
--   WHERE ps.current_flag = 1 OR p.status IN ('completed','archived')
--   GROUP BY ps.supervisor_id;
