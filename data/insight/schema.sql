-- INSIGHT-001 schema (SQLite, data/insight/insight.db)
--
-- 設計方針:
--  * 1 game = 1 unit。冪等 upsert (INSERT OR REPLACE) で再 ETL 可能。
--  * player_canonical = config/giants_roster.json の name 列に揃える。
--    fixture HTML では surname のみのこともあるので、ETL 側で正規化する。
--  * "_logs" は per-game 行、検出ロジックは多 game を joining して算出する。
--  * article_candidates は run 単位で挿入、status を更新で進める。
--
-- 関連: doc/active/INSIGHT-001-data-analysis-pipeline.md

PRAGMA foreign_keys = ON;

-- ─── games ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,         -- e.g. "2026-05-10:d-g-08"
    game_date TEXT NOT NULL,          -- ISO date
    opponent TEXT NOT NULL,           -- 中日, 阪神, ...
    home_away TEXT NOT NULL,          -- home | away | unknown
    giants_score INTEGER,
    opp_score INTEGER,
    result TEXT,                      -- win | loss | draw | unknown
    league_label TEXT,                -- 「セ・リーグ 7回戦」
    one_line_summary TEXT,
    winning_pitcher TEXT,
    losing_pitcher TEXT,
    save_pitcher TEXT,
    source_url TEXT,
    source_kind TEXT,                 -- "npb_box" | "yahoo_box" | "fixture"
    ingested_at TEXT NOT NULL         -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_games_opp ON games(opponent);

-- ─── inning_scores ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inning_scores (
    game_id TEXT NOT NULL,
    team_role TEXT NOT NULL,          -- giants | opponent
    inning_json TEXT NOT NULL,        -- ["0","1","0","2",...] JSON-encoded
    total INTEGER NOT NULL,
    PRIMARY KEY (game_id, team_role),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

-- ─── batting_logs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS batting_logs (
    game_id TEXT NOT NULL,
    team_role TEXT NOT NULL,          -- giants | opponent
    slot_order INTEGER,               -- 打順 (substitutions = same slot)
    position TEXT,                    -- 「二」「中」など
    player_display TEXT NOT NULL,     -- fixture 表示名 (姓のみのことあり)
    player_canonical TEXT,            -- roster 正規名 (joinable, NULL 許容)
    is_sub INTEGER NOT NULL DEFAULT 0,
    AB INTEGER, R INTEGER, H INTEGER, RBI INTEGER, SB INTEGER,
    atbats_json TEXT,                 -- per-PA result list JSON
    PRIMARY KEY (game_id, team_role, slot_order, player_display),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_batting_player_canon
    ON batting_logs(player_canonical, game_id);

-- ─── pitching_logs ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pitching_logs (
    game_id TEXT NOT NULL,
    team_role TEXT NOT NULL,
    appearance_order INTEGER NOT NULL,
    player_display TEXT NOT NULL,
    player_canonical TEXT,
    result_mark TEXT,                 -- 勝 / 敗 / S / H / 空
    pitches INTEGER, BF INTEGER,
    IP REAL,                          -- 投球回 5.1 → 5.333
    H_allowed INTEGER, HR_allowed INTEGER,
    BB INTEGER, HBP INTEGER, K INTEGER,
    WP INTEGER, BK INTEGER,
    R INTEGER, ER INTEGER,
    PRIMARY KEY (game_id, team_role, appearance_order, player_display),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pitching_player_canon
    ON pitching_logs(player_canonical, game_id);

-- ─── lineups (predicted future use) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS lineups (
    game_id TEXT NOT NULL,
    team_role TEXT NOT NULL,
    slot_order INTEGER NOT NULL,
    player_display TEXT NOT NULL,
    player_canonical TEXT,
    position TEXT,
    batting_side TEXT,                -- L / R / S / NULL
    PRIMARY KEY (game_id, team_role, slot_order, player_display),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

-- ─── fielding_logs (NPB 公式に出れば埋める、当面空でも OK) ────────────────
CREATE TABLE IF NOT EXISTS fielding_logs (
    game_id TEXT NOT NULL,
    team_role TEXT NOT NULL,
    player_display TEXT NOT NULL,
    player_canonical TEXT,
    position TEXT,
    innings REAL,
    PO INTEGER, A INTEGER, E INTEGER, DP INTEGER,
    PRIMARY KEY (game_id, team_role, player_display, position),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

-- ─── standings_snapshots ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS standings_snapshots (
    snap_date TEXT NOT NULL,
    team TEXT NOT NULL,
    rank INTEGER, W INTEGER, L INTEGER, T INTEGER,
    games_behind TEXT,
    PRIMARY KEY (snap_date, team)
);

-- ─── insight_runs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS insight_runs (
    run_id TEXT PRIMARY KEY,
    run_ts TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    n_candidates INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

-- ─── article_candidates ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS article_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    game_id TEXT,                     -- single-game origin (nullable for cross-game)
    player_canonical TEXT,            -- nullable for team-level signals
    player_display TEXT,
    signal_type TEXT NOT NULL,        -- hot_streak / cold_streak / batting_anomaly / ...
    magnitude REAL,
    baseline_value TEXT,
    current_value TEXT,
    window_label TEXT,
    comparison_target TEXT,
    evidence_json TEXT,
    priority INTEGER DEFAULT 3,       -- 1=high, 5=low
    status TEXT DEFAULT 'NEW',        -- NEW / REVIEWED / DRAFTED / PUBLISHED / DROPPED
    created_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (run_id) REFERENCES insight_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_candidates_status
    ON article_candidates(status, run_id);
CREATE INDEX IF NOT EXISTS idx_candidates_player
    ON article_candidates(player_canonical, signal_type);

-- ─── INSIGHT-007 additive tables (multi-team + advanced metrics) ──────────
-- INSIGHT-001 で開いた schema を破壊せず、新規 table のみ足す。既存
-- batting_logs / pitching_logs はそのまま使い続け、team_name 列だけを
-- additive に追加 (ALTER TABLE で初回 migration 時のみ実行、後続は no-op)。

CREATE TABLE IF NOT EXISTS teams (
    team_code TEXT PRIMARY KEY,          -- 'g','t','s','c','db','d','f','b','h','l','e','m'
    team_name TEXT NOT NULL,             -- '巨人','阪神','ヤクルト',...
    league TEXT NOT NULL,                -- 'central' | 'pacific'
    home_park TEXT
);

CREATE TABLE IF NOT EXISTS players (
    player_canonical TEXT PRIMARY KEY,   -- '吉川尚輝','岡本和真',...
    team_code TEXT,                      -- 'g' for Giants, 'd' for Dragons, ...
    primary_position TEXT,               -- '内野手','外野手','投手','捕手','監督','コーチ' or specific
    role TEXT,                           -- 'player' | 'manager' | 'coach' | 'pitcher' | 'fielder'
    jersey_number TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (team_code) REFERENCES teams(team_code)
);

CREATE INDEX IF NOT EXISTS idx_players_team_position
    ON players(team_code, primary_position);

-- 守備機会 (打球方向×位置×試合 単位)。UZR ではなく Range Factor 代理用
CREATE TABLE IF NOT EXISTS defense_opportunities (
    game_id TEXT NOT NULL,
    team_code TEXT NOT NULL,             -- 守備側
    position TEXT NOT NULL,              -- '一','二','三','遊','左','中','右','投','捕'
    player_canonical TEXT,               -- いるなら
    opportunities INTEGER NOT NULL DEFAULT 0,  -- 打球方向 == position の打球数
    converted_outs INTEGER NOT NULL DEFAULT 0, -- そのうち out になった数
    hits_allowed INTEGER NOT NULL DEFAULT 0,   -- 安打を許した数
    errors INTEGER NOT NULL DEFAULT 0,         -- 失策数 (atbats text に '失' marker があれば)
    PRIMARY KEY (game_id, team_code, position, player_canonical),
    FOREIGN KEY (game_id) REFERENCES games(game_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_defense_player_position
    ON defense_opportunities(player_canonical, position);

-- 計算済み advanced metrics のスナップショット (週次/月次)
CREATE TABLE IF NOT EXISTS advanced_metric_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,         -- ISO date
    scope TEXT NOT NULL,                 -- 'season' | 'last_7d' | 'last_30d' | 'last_5_games'
    player_canonical TEXT,               -- nullable for team/league aggregates
    team_code TEXT,
    position TEXT,
    metric_name TEXT NOT NULL,           -- 'OPS','wOBA','FIP','RF_proxy', ...
    metric_value REAL,
    sample_size INTEGER,                 -- PA / IP / opportunities 等
    league_rank INTEGER,                 -- 12 球団内 rank (NULL なら未計算)
    league_total INTEGER,                -- 比較対象人数
    position_rank INTEGER,               -- 同 position 内 rank
    position_total INTEGER,
    extra_json TEXT                      -- 計算根拠の自由領域
);

CREATE INDEX IF NOT EXISTS idx_snap_player_metric
    ON advanced_metric_snapshots(player_canonical, metric_name, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snap_metric_scope
    ON advanced_metric_snapshots(metric_name, scope, snapshot_date);
