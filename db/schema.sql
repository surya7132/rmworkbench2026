-- =====================================================================
-- Compass prototype: database schema (SQLite)
-- 17 tables = 12 CORE (RM workbench) + 5 KG ADD-ON (knowledge graph),
-- plus 1 tiny key-value table (app_meta) for the demo clock.
-- Money is stored in INR crore (1 crore = 10,000,000) unless a column
-- name says otherwise. Timestamps are ISO-8601 text with +05:30 offset.
-- JSON columns hold small lists/objects and are checked with json_valid().
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- META
CREATE TABLE app_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- ===================================================== CORE (12 tables)
-- 1. People who log in or own work
CREATE TABLE app_user (
  id            TEXT PRIMARY KEY,                 -- u_rohan
  employee_id   TEXT NOT NULL UNIQUE,             -- RBL-style staff id, e.g. RBL104532
  name          TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE,
  role          TEXT NOT NULL,                    -- Relationship manager, Team lead, Specialist...
  function      TEXT NOT NULL,                    -- RM, Team, Trade and Guarantees, Credit Risk...
  initials      TEXT NOT NULL,
  username      TEXT UNIQUE,                      -- NULL = cannot log in (owner only)
  password_hash TEXT,                             -- pbkdf2_sha256$iterations$salt$hash
  can_login     INTEGER NOT NULL DEFAULT 0 CHECK (can_login IN (0,1)),
  reports_to    TEXT REFERENCES app_user(id)
);

-- 2. One row per client group
CREATE TABLE client_group (
  id               TEXT PRIMARY KEY,              -- g_vantage
  name             TEXT NOT NULL,
  short_name       TEXT NOT NULL,
  primary_node_id  TEXT,                          -- the primary borrower (node)
  segment          TEXT NOT NULL,
  sector           TEXT NOT NULL,
  tier             INTEGER NOT NULL CHECK (tier IN (1,2,3)),
  rm_id            TEXT NOT NULL REFERENCES app_user(id),
  relationship_since INTEGER NOT NULL,            -- year
  sanctioned_cr    REAL NOT NULL,                 -- sum of facilities
  outstanding_cr   REAL NOT NULL,
  deposits_cr      REAL NOT NULL DEFAULT 0,
  internal_rating  TEXT,                          -- RBL internal grade
  external_rating  TEXT,                          -- agency + grade + outlook
  rating_trend     TEXT CHECK (rating_trend IN ('up','flat','down')),
  watch_flag       TEXT NOT NULL DEFAULT 'None' CHECK (watch_flag IN ('None','P1','P2','P3')),
  cadence_days     INTEGER NOT NULL,              -- target gap between contacts
  last_contact     TEXT,
  review_due       TEXT,
  flow_level       TEXT,                          -- High / Medium / Low transaction flows
  has_detail       INTEGER NOT NULL DEFAULT 0 CHECK (has_detail IN (0,1))
);
CREATE INDEX ix_group_rm ON client_group(rm_id);

-- 3. Every statement stored once, with its source
CREATE TABLE fact (
  id               TEXT PRIMARY KEY,              -- F-1001
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  node_id          TEXT,                          -- the entity the fact is about
  statement        TEXT NOT NULL,
  value_num        REAL,
  unit             TEXT,
  source_name      TEXT NOT NULL,                 -- Core banking, MCA charge filing...
  source_ref       TEXT,                          -- CHG id, rating ref, meeting id...
  source_date      TEXT NOT NULL,
  effective_date   TEXT,
  evidence_label   TEXT NOT NULL CHECK (evidence_label IN
                    ('int','ext','client','rm','model','ind','need','blk','sup','miu')),
  shareability     TEXT NOT NULL CHECK (shareability IN ('internal','discuss','confirmed')),
  match_confidence REAL NOT NULL DEFAULT 1.0 CHECK (match_confidence BETWEEN 0 AND 1),
  superseded_by    TEXT REFERENCES fact(id),
  connector        TEXT NOT NULL
);
CREATE INDEX ix_fact_group ON fact(client_group_id);
CREATE INDEX ix_fact_node  ON fact(node_id);

-- 4. Limits and exposure by product
CREATE TABLE facility (
  id               TEXT PRIMARY KEY,
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  facility_type    TEXT NOT NULL,                 -- Term Loan, Cash Credit, Bank Guarantee...
  account_ref      TEXT,                          -- masked: XXXXXX4821
  sanctioned_cr    REAL NOT NULL,
  outstanding_cr   REAL NOT NULL CHECK (outstanding_cr <= sanctioned_cr + 0.0001),
  maturity         TEXT,
  pricing          TEXT,
  security         TEXT,
  coverage         TEXT,
  covenants        TEXT,
  approval_authority TEXT,
  review_date      TEXT,
  status           TEXT NOT NULL DEFAULT 'Standard'
);
CREATE INDEX ix_facility_group ON facility(client_group_id);

-- 5. What a client needs (commercial case). Also a node in the graph.
CREATE TABLE need (
  id               TEXT PRIMARY KEY,              -- opp_v1
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  node_id          TEXT,                          -- the need's node in the graph
  name             TEXT NOT NULL,
  product          TEXT NOT NULL,
  product_family   TEXT NOT NULL,                 -- Lending, Trade, Treasury...
  stage            TEXT NOT NULL,                 -- Signal ... Decision (9 stages)
  need_status      TEXT NOT NULL,                 -- Hypothesis, Client-stated, Client-confirmed
  stakeholder_node_id TEXT,
  specialist_id    TEXT REFERENCES app_user(id),
  reviewer_id      TEXT REFERENCES app_user(id),  -- credit reviewer if a credit case is open
  origin           TEXT NOT NULL,                 -- Event: debt maturity (F-1001)
  origin_source    TEXT NOT NULL,                 -- meeting note | filings | account data | news ...
  description      TEXT NOT NULL,
  timeline         TEXT,
  incumbent        TEXT,
  value_lo_cr      REAL,                          -- annual revenue range to the bank
  value_hi_cr      REAL,
  value_basis      TEXT,                          -- base x factor x rate, in words
  fact_ids         TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(fact_ids)),
  next_action      TEXT CHECK (next_action IS NULL OR json_valid(next_action)),
  canvas           TEXT CHECK (canvas IS NULL OR json_valid(canvas)),   -- credit deal canvas
  target_decision  TEXT,
  status           TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX ix_need_group ON need(client_group_id);

-- 6. Meetings, calls, emails
CREATE TABLE meeting (
  id               TEXT PRIMARY KEY,
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  meeting_type     TEXT NOT NULL CHECK (meeting_type IN ('meeting','call','email')),
  title            TEXT NOT NULL,
  starts_at        TEXT NOT NULL,
  duration_min     INTEGER,
  location         TEXT,
  attendee_node_ids TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(attendee_node_ids)),
  status           TEXT NOT NULL CHECK (status IN ('scheduled','held','notes_pending','cancelled')),
  prep_status      TEXT,
  objective        TEXT,
  success_criteria TEXT,
  agenda           TEXT CHECK (agenda IS NULL OR json_valid(agenda)),
  outcome          TEXT,
  source           TEXT NOT NULL,                 -- rm | calendar | outlook-detected
  logged           INTEGER NOT NULL DEFAULT 1 CHECK (logged IN (0,1)),
  need_id          TEXT REFERENCES need(id)
);
CREATE INDEX ix_meeting_group ON meeting(client_group_id);

-- 7. The single task model: commitments, requests, clarifications, alerts, follow-ups
CREATE TABLE work_item (
  id               TEXT PRIMARY KEY,              -- W-2001
  title            TEXT NOT NULL,
  work_type        TEXT NOT NULL,
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  case_ref         TEXT,                          -- need id, meeting id, alert id
  owner_id         TEXT NOT NULL REFERENCES app_user(id),
  requester_id     TEXT NOT NULL REFERENCES app_user(id),
  created_at       TEXT NOT NULL,
  due_at           TEXT NOT NULL,
  client_deadline  TEXT,
  consequence      TEXT,
  state            TEXT NOT NULL CHECK (state IN
                    ('Open','Accepted','In progress','Needs information','Done','Cancelled')),
  completion_condition TEXT,
  depends_on       TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(depends_on)),
  escalation_level INTEGER NOT NULL DEFAULT 0 CHECK (escalation_level BETWEEN 0 AND 5),
  visibility       TEXT NOT NULL CHECK (visibility IN ('internal','client')),
  sla              TEXT,
  counterpart_label TEXT,                         -- e.g. "Rajiv Mehta (client)"
  source_event_id  TEXT,                          -- set when a market event created it
  why_path         TEXT CHECK (why_path IS NULL OR json_valid(why_path)),  -- graph path shown to the user
  version          INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_work_owner ON work_item(owner_id, state);
CREATE INDEX ix_work_group ON work_item(client_group_id);

-- 8. Messages and history on a work item
CREATE TABLE work_thread (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  work_item_id TEXT NOT NULL REFERENCES work_item(id),
  at           TEXT NOT NULL,
  by_user      TEXT NOT NULL REFERENCES app_user(id),
  kind         TEXT NOT NULL CHECK (kind IN ('message','system','ladder')),
  text         TEXT NOT NULL
);
CREATE INDEX ix_thread_item ON work_thread(work_item_id, at);

-- 9. Files (annual reports, statements, rating rationales)
CREATE TABLE document (
  id               TEXT PRIMARY KEY,
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  name             TEXT NOT NULL,
  doc_type         TEXT NOT NULL,                 -- Annual report, Stock statement, Rating rationale
  fiscal_year      TEXT,                          -- FY2025-26
  period_end       TEXT,
  basis            TEXT,                          -- Consolidated / Standalone
  unit             TEXT,                          -- INR crore
  version          INTEGER NOT NULL DEFAULT 1,
  source           TEXT NOT NULL,                 -- Client upload, MCA, Rating agency
  storage_path     TEXT,                          -- relative path; NULL = metadata only
  page_count       INTEGER,
  status           TEXT NOT NULL,                 -- Received, Spread in progress, Spread confirmed
  uploaded_at      TEXT NOT NULL
);

-- 10. Extracted financial values (what the RM reviews and confirms)
CREATE TABLE spread_line (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id      TEXT NOT NULL REFERENCES document(id),
  line_code        TEXT NOT NULL,                 -- L01..L18
  label            TEXT NOT NULL,
  statement        TEXT NOT NULL,                 -- P&L, Balance sheet, Current liabilities, Cash flow, Notes
  fy_current       REAL,                          -- extracted value, latest year
  fy_prior1        REAL,
  fy_prior2        REAL,
  printed_current  REAL,                          -- what the page actually prints (ground truth)
  page_ref         TEXT NOT NULL,                 -- printed folio, e.g. p. 84
  pdf_page         INTEGER,                       -- physical page in the PDF
  confidence       INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
  status           TEXT NOT NULL DEFAULT 'extracted' CHECK (status IN ('extracted','confirmed','corrected')),
  note_ref_label   TEXT,
  note_ref_value   REAL,
  note_ref_page    TEXT,
  UNIQUE (document_id, line_code)
);

-- 11. Early-warning and external alerts
CREATE TABLE alert (
  id               TEXT PRIMARY KEY,
  client_group_id  TEXT NOT NULL REFERENCES client_group(id),
  title            TEXT NOT NULL,
  category         TEXT NOT NULL,
  ews_code         TEXT,                          -- EWS-WC-03 style trigger code
  sma_class        TEXT CHECK (sma_class IS NULL OR sma_class IN ('SMA-0','SMA-1','SMA-2')),
  source           TEXT NOT NULL,
  detected_at      TEXT NOT NULL,
  severity         TEXT NOT NULL CHECK (severity IN ('High','Medium','Low')),
  exposure_cr      REAL NOT NULL,
  blocks_credit    INTEGER NOT NULL DEFAULT 0 CHECK (blocks_credit IN (0,1)),
  covenant_breach  INTEGER NOT NULL DEFAULT 0 CHECK (covenant_breach IN (0,1)),
  review_days_left INTEGER,
  state            TEXT NOT NULL CHECK (state IN ('New','Under review','Responded','Resolved')),
  context          TEXT,
  required_action  TEXT,
  dedupe_key       TEXT,                          -- same real-world event, different feed
  source_event_id  TEXT,
  fact_ids         TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(fact_ids)),
  resolution_reason TEXT,
  resolved_by      TEXT REFERENCES app_user(id),
  resolved_at      TEXT
);
CREATE INDEX ix_alert_group ON alert(client_group_id, state);

-- 12. Append-only log of every confirmed change
CREATE TABLE audit_log (
  txn_id   TEXT PRIMARY KEY,                      -- TXN-000001
  at       TEXT NOT NULL,
  user_id  TEXT NOT NULL REFERENCES app_user(id),
  action   TEXT NOT NULL,
  summary  TEXT NOT NULL,
  before_json TEXT CHECK (before_json IS NULL OR json_valid(before_json)),
  after_json  TEXT CHECK (after_json  IS NULL OR json_valid(after_json)),
  affected    TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(affected))
);

-- ================================================ KG ADD-ON (5 tables)
-- 13. Things in the graph
CREATE TABLE node (
  id        TEXT PRIMARY KEY,                     -- e_steel, p_rajiv, s_steel, N-...
  node_type TEXT NOT NULL CHECK (node_type IN
             ('client_group','company','person','bank','sector','product_family','need','rbl_user')),
  name      TEXT NOT NULL,
  client_group_id TEXT REFERENCES client_group(id),   -- group the node belongs to, if any
  attrs     TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attrs)) -- CIN, PAN, LEI, DIN, role...
);
CREATE INDEX ix_node_type ON node(node_type);
CREATE INDEX ix_node_group ON node(client_group_id);

-- 14. Lines between things
CREATE TABLE edge (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  from_node      TEXT NOT NULL REFERENCES node(id),
  to_node        TEXT NOT NULL REFERENCES node(id),
  edge_type      TEXT NOT NULL,                   -- supplies_to, owns, member_of, has_need, handled_by...
  attrs          TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attrs)),  -- pct, role, volume...
  source_fact_id TEXT REFERENCES fact(id),
  confidence     REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  valid_from     TEXT,
  valid_to       TEXT,
  UNIQUE (from_node, to_node, edge_type)
);
CREATE INDEX ix_edge_from ON edge(from_node, edge_type);
CREATE INDEX ix_edge_to   ON edge(to_node, edge_type);

-- 15. News, filings, rating actions, sector moves
CREATE TABLE market_event (
  id            TEXT PRIMARY KEY,                 -- ME-1101
  event_type    TEXT NOT NULL,                    -- Plant incident, Charge registered, Rating action...
  headline      TEXT NOT NULL,
  summary       TEXT NOT NULL,
  source_name   TEXT NOT NULL,                    -- MCA21, BSE Reg 30, Rating agency, News feed
  source_ref    TEXT,                             -- charge id, filing no., article id
  published_at  TEXT NOT NULL,
  severity      TEXT NOT NULL CHECK (severity IN ('High','Medium','Low')),
  sector        TEXT,
  entity_names  TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(entity_names)),  -- raw names as printed
  cluster_key   TEXT,                             -- same real-world incident across feeds
  status        TEXT NOT NULL CHECK (status IN ('pending','processed')),
  processed_at  TEXT,
  is_hero       INTEGER NOT NULL DEFAULT 0 CHECK (is_hero IN (0,1))
);

-- 16. Which things an event touched, and why
CREATE TABLE event_impact (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id      TEXT NOT NULL REFERENCES market_event(id),
  node_id       TEXT NOT NULL REFERENCES node(id),
  client_group_id TEXT REFERENCES client_group(id),
  hops          INTEGER NOT NULL CHECK (hops >= 0),
  path          TEXT NOT NULL CHECK (json_valid(path)),   -- ordered node ids and edge types
  reason        TEXT NOT NULL,
  impact_level  TEXT NOT NULL CHECK (impact_level IN ('High','Medium','Low')),
  match_confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX ix_impact_event ON event_impact(event_id);

-- 17. Who gets what when an event lands
CREATE TABLE routing_rule (
  id             TEXT PRIMARY KEY,                -- RR-01
  sort_order     INTEGER NOT NULL,
  name           TEXT NOT NULL,
  applies_to     TEXT NOT NULL,                   -- event types / conditions in words
  condition_json TEXT NOT NULL CHECK (json_valid(condition_json)),
  recipient      TEXT NOT NULL,                   -- client_rm | need_specialist | credit_reviewer | team_lead | function
  task_type      TEXT NOT NULL,
  due_in_hours   INTEGER NOT NULL,
  title_template TEXT NOT NULL,
  why_template   TEXT NOT NULL,
  merge_by       TEXT NOT NULL DEFAULT 'recipient',  -- one task per recipient per incident
  active         INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);
