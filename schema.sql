-- LUMORA database schema (MySQL 8)
-- Run with:  python -m scripts.init_db

CREATE DATABASE IF NOT EXISTS lumora_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lumora_db;

-- ---------- Organisation and people ----------

CREATE TABLE IF NOT EXISTS companies (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS users (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  company_id INT UNSIGNED NOT NULL,
  employee_id VARCHAR(30) NOT NULL,
  full_name VARCHAR(150) NOT NULL,
  email VARCHAR(190) NOT NULL,
  role ENUM('employee','hr') NOT NULL DEFAULT 'employee',
  status ENUM('active','inactive') NOT NULL DEFAULT 'active',
  password_hash VARCHAR(255) NULL,          -- demo login only; never a Google password
  idp_subject VARCHAR(255) NULL,            -- Google/identity provider subject (Phase 7)
  session_version INT UNSIGNED NOT NULL DEFAULT 0,  -- raise it to log a user out everywhere
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_users_email (email),
  UNIQUE KEY uq_users_company_empid (company_id, employee_id),
  UNIQUE KEY uq_users_idp_subject (idp_subject),
  KEY idx_users_role_status (role, status),
  CONSTRAINT fk_users_company FOREIGN KEY (company_id) REFERENCES companies(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS teams (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  company_id INT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  UNIQUE KEY uq_teams_company_name (company_id, name),
  CONSTRAINT fk_teams_company FOREIGN KEY (company_id) REFERENCES companies(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS team_memberships (
  user_id INT UNSIGNED NOT NULL,
  team_id INT UNSIGNED NOT NULL,
  PRIMARY KEY (user_id, team_id),
  CONSTRAINT fk_tm_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_tm_team FOREIGN KEY (team_id) REFERENCES teams(id)
) ENGINE=InnoDB;

-- ---------- Competencies and scenarios ----------

CREATE TABLE IF NOT EXISTS competencies (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  company_id INT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  description TEXT NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_comp_company_name (company_id, name),
  CONSTRAINT fk_comp_company FOREIGN KEY (company_id) REFERENCES companies(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scenarios (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  company_id INT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL,
  scenario_text TEXT NOT NULL,
  instructions TEXT NOT NULL,
  status ENUM('draft','published','archived') NOT NULL DEFAULT 'draft',
  version INT UNSIGNED NOT NULL DEFAULT 1,
  previous_version_id INT UNSIGNED NULL,    -- published scenarios are never edited; a new version is made
  created_by INT UNSIGNED NOT NULL,
  is_demo TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  published_at TIMESTAMP NULL,
  KEY idx_scenarios_status (company_id, status),
  CONSTRAINT fk_sc_company FOREIGN KEY (company_id) REFERENCES companies(id),
  CONSTRAINT fk_sc_creator FOREIGN KEY (created_by) REFERENCES users(id),
  CONSTRAINT fk_sc_prev FOREIGN KEY (previous_version_id) REFERENCES scenarios(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scenario_competencies (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  scenario_id INT UNSIGNED NOT NULL,
  competency_id INT UNSIGNED NOT NULL,
  rubric TEXT NOT NULL,                     -- the explicit rubric used for this scenario version
  UNIQUE KEY uq_sc_comp (scenario_id, competency_id),
  CONSTRAINT fk_scc_scenario FOREIGN KEY (scenario_id) REFERENCES scenarios(id),
  CONSTRAINT fk_scc_comp FOREIGN KEY (competency_id) REFERENCES competencies(id)
) ENGINE=InnoDB;

-- ---------- Assignments and responses ----------

CREATE TABLE IF NOT EXISTS assignments (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  scenario_id INT UNSIGNED NOT NULL,
  assigned_by INT UNSIGNED NOT NULL,
  deadline DATE NULL,
  allow_reassessment TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_as_scenario FOREIGN KEY (scenario_id) REFERENCES scenarios(id),
  CONSTRAINT fk_as_by FOREIGN KEY (assigned_by) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS assignment_recipients (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  assignment_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  status ENUM('assigned','submitted','analysed') NOT NULL DEFAULT 'assigned',
  UNIQUE KEY uq_recipient (assignment_id, user_id),   -- stops duplicate assignments
  KEY idx_recipient_user (user_id, status),
  CONSTRAINT fk_ar_assignment FOREIGN KEY (assignment_id) REFERENCES assignments(id),
  CONSTRAINT fk_ar_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS responses (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  recipient_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  attempt_no INT UNSIGNED NOT NULL DEFAULT 1,
  response_text TEXT NOT NULL,              -- original text, never edited
  submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_response_attempt (recipient_id, attempt_no),   -- stops duplicate submissions
  KEY idx_response_user (user_id),
  CONSTRAINT fk_resp_recipient FOREIGN KEY (recipient_id) REFERENCES assignment_recipients(id),
  CONSTRAINT fk_resp_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ---------- AI analysis and findings ----------

CREATE TABLE IF NOT EXISTS assessments (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  response_id INT UNSIGNED NOT NULL,
  analysis_status ENUM('pending','processing','completed','failed') NOT NULL DEFAULT 'pending',
  analysis_mode ENUM('mock','live') NOT NULL DEFAULT 'mock',   -- mock results are labelled as demo
  model_name VARCHAR(100) NULL,
  limitations TEXT NULL,
  error_message VARCHAR(255) NULL,          -- short safe message only
  attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL,
  UNIQUE KEY uq_assessment_response (response_id),   -- one analysis per response
  CONSTRAINT fk_asm_response FOREIGN KEY (response_id) REFERENCES responses(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS competency_findings (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  assessment_id INT UNSIGNED NOT NULL,
  competency_id INT UNSIGNED NOT NULL,
  finding TEXT NOT NULL,
  evidence TEXT NULL,                       -- must come from the real response
  development_area TEXT NULL,
  recommendation TEXT NULL,
  confidence ENUM('low','moderate','high') NOT NULL DEFAULT 'low',
  status ENUM('completed','insufficient_evidence') NOT NULL DEFAULT 'completed',
  UNIQUE KEY uq_finding (assessment_id, competency_id),
  CONSTRAINT fk_cf_assessment FOREIGN KEY (assessment_id) REFERENCES assessments(id),
  CONSTRAINT fk_cf_comp FOREIGN KEY (competency_id) REFERENCES competencies(id)
) ENGINE=InnoDB;

-- ---------- Learning ----------

CREATE TABLE IF NOT EXISTS training_activities (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  company_id INT UNSIGNED NOT NULL,
  competency_id INT UNSIGNED NOT NULL,
  title VARCHAR(200) NOT NULL,
  description TEXT NOT NULL,
  learning_objective TEXT NOT NULL,
  resource_type VARCHAR(50) NOT NULL DEFAULT 'exercise',
  resource_url VARCHAR(500) NULL,
  is_demo_resource TINYINT(1) NOT NULL DEFAULT 1,   -- clearly labelled demo content
  duration_minutes INT UNSIGNED NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  KEY idx_ta_comp (competency_id),
  CONSTRAINT fk_ta_company FOREIGN KEY (company_id) REFERENCES companies(id),
  CONSTRAINT fk_ta_comp FOREIGN KEY (competency_id) REFERENCES competencies(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS recommendations (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  finding_id INT UNSIGNED NOT NULL,
  activity_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_reco (finding_id, activity_id),
  KEY idx_reco_user (user_id),
  CONSTRAINT fk_rc_finding FOREIGN KEY (finding_id) REFERENCES competency_findings(id),
  CONSTRAINT fk_rc_activity FOREIGN KEY (activity_id) REFERENCES training_activities(id),
  CONSTRAINT fk_rc_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS learning_progress (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  recommendation_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  status ENUM('not_started','in_progress','completed') NOT NULL DEFAULT 'not_started',
  completed_at TIMESTAMP NULL,
  UNIQUE KEY uq_progress (recommendation_id),
  CONSTRAINT fk_lp_reco FOREIGN KEY (recommendation_id) REFERENCES recommendations(id),
  CONSTRAINT fk_lp_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ---------- Reviews and governance ----------

CREATE TABLE IF NOT EXISTS review_requests (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  finding_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  concern TEXT NOT NULL,
  status ENUM('open','under_review','resolved','declined') NOT NULL DEFAULT 'open',
  outcome TEXT NULL,
  reviewed_by INT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TIMESTAMP NULL,
  KEY idx_review_status (status),
  KEY idx_review_user (user_id),
  CONSTRAINT fk_rr_finding FOREIGN KEY (finding_id) REFERENCES competency_findings(id),
  CONSTRAINT fk_rr_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_rr_reviewer FOREIGN KEY (reviewed_by) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS hr_role_history (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id INT UNSIGNED NOT NULL,
  old_role ENUM('employee','hr') NULL,
  new_role ENUM('employee','hr') NOT NULL,
  changed_by INT UNSIGNED NULL,
  reason VARCHAR(255) NULL,
  changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_rh_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_rh_by FOREIGN KEY (changed_by) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS account_status_history (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id INT UNSIGNED NOT NULL,
  old_status ENUM('active','inactive') NULL,
  new_status ENUM('active','inactive') NOT NULL,
  changed_by INT UNSIGNED NULL,
  reason VARCHAR(255) NULL,
  changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_ash_user (user_id),
  CONSTRAINT fk_ash_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_ash_by FOREIGN KEY (changed_by) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_logs (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  actor_user_id INT UNSIGNED NULL,
  action VARCHAR(80) NOT NULL,
  target_type VARCHAR(50) NULL,
  target_id INT UNSIGNED NULL,
  details JSON NULL,                        -- never store passwords, tokens or full responses
  ip_address VARCHAR(45) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_audit_actor (actor_user_id),
  KEY idx_audit_action (action),
  KEY idx_audit_created (created_at),
  CONSTRAINT fk_audit_actor FOREIGN KEY (actor_user_id) REFERENCES users(id)
) ENGINE=InnoDB;

-- ---------- Security ----------

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id INT UNSIGNED NOT NULL,
  token_hash CHAR(64) NOT NULL,             -- only the hash is stored
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,                    -- set on use, so a token works once
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_reset_hash (token_hash),
  KEY idx_reset_user (user_id),
  CONSTRAINT fk_prt_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS login_attempts (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(190) NOT NULL,
  ip_address VARCHAR(45) NULL,
  was_successful TINYINT(1) NOT NULL DEFAULT 0,
  attempted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_la_email_time (email, attempted_at),
  KEY idx_la_ip_time (ip_address, attempted_at)
) ENGINE=InnoDB;
