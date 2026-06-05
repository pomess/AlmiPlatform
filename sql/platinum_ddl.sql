-- Disease360 Atlas — Platinum Layer DDL
-- Catalog: {env}_gold_commercial  (dev_gold_commercial | tst_gold_commercial | gold_commercial)
-- Schema:  genai_mcm_d360
--
-- These tables sit on top of existing Gold tables. They are refreshed by Lakeflow Jobs.
-- Run with: SET catalog = dev_gold_commercial; before executing in dev.

-- =============================================================================
-- 1. platinum_graph_nodes
-- Consolidated entity graph: companies, drugs, indications, mechanisms, KOLs, etc.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ${catalog}.genai_mcm_d360.platinum_graph_nodes (
    node_id         STRING      NOT NULL COMMENT 'Deterministic UUID: md5(node_type || canonical_name)',
    node_type       STRING      NOT NULL COMMENT 'company | drug | indication | mechanism | trial | kol | institution | regulatory_body',
    name            STRING      NOT NULL COMMENT 'Canonical display name',
    aliases         ARRAY<STRING>        COMMENT 'Alternative names from GlobalData + EMA + FDA',
    properties      MAP<STRING, STRING>  COMMENT 'Type-specific key-value pairs (phase, status, moa, hq_country, etc.)',
    source_tables   ARRAY<STRING>        COMMENT 'Gold tables this node was derived from',
    updated_at      TIMESTAMP   NOT NULL COMMENT 'Last refresh timestamp'
)
USING DELTA
COMMENT 'Knowledge graph nodes — consolidated from all Gold tables'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- =============================================================================
-- 2. platinum_graph_edges
-- Relationships between nodes, extracted via joins across Gold tables.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ${catalog}.genai_mcm_d360.platinum_graph_edges (
    edge_id             STRING      NOT NULL COMMENT 'UUID',
    source_node         STRING      NOT NULL COMMENT 'FK → platinum_graph_nodes.node_id',
    target_node         STRING      NOT NULL COMMENT 'FK → platinum_graph_nodes.node_id',
    relation_type       STRING      NOT NULL COMMENT 'develops | treats | competes_with | sponsors_trial | evaluates | investigates | affiliated_with | approved_for | targets_mechanism | partners_with',
    confidence          FLOAT       NOT NULL COMMENT '1.0 = structured source, 0.7-0.9 = inferred',
    evidence_sources    ARRAY<STRING>        COMMENT 'Table+row references supporting this edge',
    properties          MAP<STRING, STRING>  COMMENT 'start_date, end_date, phase, geography, etc.',
    updated_at          TIMESTAMP   NOT NULL COMMENT 'Last refresh timestamp'
)
USING DELTA
COMMENT 'Knowledge graph edges — relationships between entities'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- =============================================================================
-- 3. platinum_news_events
-- Unified event timeline from GlobalData catalysts, news, RSS, EMA/FDA approvals.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ${catalog}.genai_mcm_d360.platinum_news_events (
    event_id        STRING      NOT NULL COMMENT 'UUID',
    event_date      DATE        NOT NULL COMMENT 'Date of the event',
    source          STRING      NOT NULL COMMENT 'globaldata_news | globaldata_catalysts | ema | fda | rss_fiercepharma | rss_stat | etc.',
    category        STRING      NOT NULL COMMENT 'approval | trial_readout | partnership | regulatory | publication | catalyst | news',
    title           STRING      NOT NULL COMMENT 'Clean title',
    summary         STRING               COMMENT '2-3 line summary',
    url             STRING               COMMENT 'Original source URL',
    entities        ARRAY<STRUCT<name: STRING, type: STRING, node_id: STRING>> COMMENT 'Mentioned entities linked to graph',
    relevance_score FLOAT                COMMENT '0-1: relevance to Almirall derm franchise',
    sentiment       STRING               COMMENT 'positive | negative | neutral',
    tags            ARRAY<STRING>        COMMENT 'Free-form tags',
    ingested_at     TIMESTAMP   NOT NULL COMMENT 'When this row was created'
)
USING DELTA
PARTITIONED BY (source)
COMMENT 'Unified pharma event timeline for the news panel and notifications'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- =============================================================================
-- 4. platinum_bullseye
-- Competitive positioning: drugs and companies by ring/segment with threat scores.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ${catalog}.genai_mcm_d360.platinum_bullseye (
    entity_id           STRING      NOT NULL COMMENT 'FK → platinum_graph_nodes.node_id',
    entity_name         STRING      NOT NULL COMMENT 'Denormalized display name',
    entity_type         STRING      NOT NULL COMMENT 'company | drug',
    ring                INT         NOT NULL COMMENT '1=Almirall core, 2=direct competitor, 3=adjacent, 4=peripheral',
    segment             STRING      NOT NULL COMMENT 'AD | HS | Psoriasis | Immunology',
    threat_score        FLOAT                COMMENT '0-1: competitive threat level',
    opportunity_score   FLOAT                COMMENT '0-1: partnership/white-space opportunity',
    pipeline_summary    ARRAY<STRUCT<drug: STRING, phase: STRING, indication: STRING>> COMMENT 'Pipeline snapshot',
    last_event          STRUCT<date: DATE, title: STRING, category: STRING>             COMMENT 'Most recent platinum_news_events entry',
    updated_at          TIMESTAMP   NOT NULL COMMENT 'Last refresh timestamp'
)
USING DELTA
COMMENT 'Bullseye competitive positioning chart data'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- =============================================================================
-- 5. platinum_kols
-- Enriched KOL profiles cross-referencing minutes + trials.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ${catalog}.genai_mcm_d360.platinum_kols (
    kol_id          STRING      NOT NULL COMMENT 'FK → platinum_graph_nodes.node_id',
    name            STRING      NOT NULL,
    institution     STRING               COMMENT 'Primary affiliation',
    country         STRING,
    specialties     ARRAY<STRING>        COMMENT 'Disease areas from KOL minutes',
    trials_involved INT                  COMMENT 'Count of clinical_trials where this KOL is PI',
    minutes_count   INT                  COMMENT 'Number of internal KOL meeting minutes',
    influence_score FLOAT                COMMENT 'Composite: recency-weighted minutes + trials + publications',
    recent_topics   ARRAY<STRING>        COMMENT 'Topics from most recent minutes',
    updated_at      TIMESTAMP   NOT NULL
)
USING DELTA
COMMENT 'KOL influence profiles for the cockpit'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- =============================================================================
-- 6. platinum_trials
-- Enriched clinical trials with graph node linkage and relevance scoring.
-- =============================================================================
CREATE TABLE IF NOT EXISTS ${catalog}.genai_mcm_d360.platinum_trials (
    nct_id                  STRING      NOT NULL COMMENT 'ClinicalTrials.gov ID',
    title                   STRING      NOT NULL,
    status                  STRING               COMMENT 'RECRUITING | NOT_YET_RECRUITING | COMPLETED | TERMINATED | etc.',
    phase                   STRING               COMMENT 'Phase 1 | Phase 2 | Phase 3 | Phase 4 | N/A',
    sponsor                 STRING,
    sponsor_node_id         STRING               COMMENT 'FK → platinum_graph_nodes.node_id',
    indications             ARRAY<STRING>,
    drugs                   ARRAY<STRUCT<name: STRING, node_id: STRING>>,
    start_date              DATE,
    primary_completion_date DATE,
    enrollment              INT,
    relevance_to_almirall   FLOAT                COMMENT '0-1: same indication + geography scoring',
    updated_at              TIMESTAMP   NOT NULL
)
USING DELTA
COMMENT 'Enriched clinical trials linked to the knowledge graph'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
