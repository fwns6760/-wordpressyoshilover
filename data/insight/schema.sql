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
