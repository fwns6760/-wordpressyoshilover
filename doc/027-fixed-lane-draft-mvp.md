# 027 — 固定版レーン MVP の Draft 作成経路を実装

**フェーズ：** 固定版レーンの Draft 供給復旧  
**担当：** Codex A  
**依存：** 011, 014, 019

---

## 概要

- 固定版レーン 4 型を対象に、`source -> 固定版生成 -> WordPress Draft POST(status=draft)` の最短経路を通す MVP を定義する。
- 現行の `quality-monitor` / `quality-gmail` / `draft-body-editor` は監視・通知・既存 Draft 編集のみで、新規 Draft 作成経路は本 ticket で初めて固定する。
- 実装は別便とし、本便は設計固定だけを行う。
- 正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §5 / §9。親は `doc/011` (`4dc0b2b`) / `doc/014` (`2d92405`) / `doc/019` (`07e5279`)。

## 対象 4 型

- 対象境界:
  4 型は A4 `CORE_SUBTYPES` の `fact_notice / pregame / farm` に収め、`postgame` と `live_anchor` は本 MVP で扱わない。
- 番組情報:
  `subtype=fact_notice`、category=`その他`、タグ `番組` 必須とする。カード仕様は `doc/019` 準拠で固定版レーンに流す。
- 公示:
  `subtype=fact_notice`、category=`選手情報`、タグ `公示` 必須とする。カード仕様は `doc/019` 準拠で固定する。
- 予告先発:
  `subtype=pregame`、category=`試合結果`、タグ `予告先発` 必須とする。固定版カードは `doc/019` 準拠とする。
- 二軍成績:
  `subtype=farm`、category=`試合結果`、タグ `ファーム` 必須とする。`doc/011` の固定版 6 型と `doc/021` の二軍・若手ループに整合させる。

## source trust 条件

- 基本条件:
  `source_trust=primary tier` のみ採用する。`secondary tier` は補強だけに使い、`doc/022` の merge 原則と同じく本文の事実核には使わない。
- 除外条件:
  `rumor` / `unknown` 単独は採用禁止とする。`rumor` が混入した候補は MVP では破棄し、固定版レーンにも AIエージェント版 にも流さない。
- primary tier の代表 source:
  番組情報は放送局公式番組表、`giants.jp` お知らせを例示する。公示は `npb.jp` 公示、`giants.jp` お知らせを例示する。
- primary tier の代表 source 続き:
  予告先発は `npb.jp` 予告先発、`giants.jp` 試合情報を例示する。二軍成績は `giants.jp` 二軍試合情報、二軍順位を例示する。

## Draft POST の条件

- POST 先:
  WordPress REST `POST /wp-json/wp/v2/posts` のみを使い、`status=draft` 固定で投げる。`status=publish` を書く経路は本便でも実装便でも作らない。
- metadata:
  `subtype / category / tags / candidate_id / game_id(該当時) / source_trust=primary` を metadata として付与する。`published` 更新用の metadata は持たない。
- 失敗時:
  失敗時の retry は 1 回のみに制限する。2 回目も失敗した候補は破棄し、重複投稿リスクを避ける。

## duplicate 回避条件

- 一意キー:
  `candidate_id = {source_id}:{article_type}:{YYYYMMDD}` を一意キーに使う。形式は `doc/024` の JSONL 側とそろえる。
- 再生成防止:
  同一 `candidate_id` が WordPress 上に draft または `published` として存在する場合は再生成しない。
- 検出方針:
  重複検出は `GET /posts?status=draft,publish&meta_key=candidate_id&meta_value=...` を第一候補とし、必要なら別 index file 管理へ逃がす。実装は別便で確定する。

## canary 条件

- 初回投入:
  初回 canary は 1 subtype × 1 件のみとする。成功条件は `status=draft` で WordPress に到達し、meta が反映されること。
- 観測期間:
  直後 24 時間は手動確認だけを行い、自動拡大しない。`quality-monitor` / `quality-gmail` は既存監視のまま参照だけに使う。
- 拡大条件:
  問題が無ければ 4 型全体へ広げるが、日次上限は MVP 規定内に抑える。急な多投はしない。
- 停止条件:
  失敗検知時は即停止し、追加 retry や自動復旧は行わない。user 判断待ちに戻す。

## 非機能制約

- published 不可触:
  `published` には触らない。既存 post の修正も自動 publish も scope 外とする。
- 既存 automation 不可触:
  `quality-monitor` / `quality-gmail` / `draft-body-editor` の automation は触らない。監視・通知・既存 Draft 編集の役割分離を維持する。
- mail / 設定不可触:
  Gmail送信経路、宛先、prompt、scheduler、env、secret は触らない。`automation.toml` や cron も scope 外とする。
- Batch API 不使用:
  `023-026` の Batch API はまだ使わない。MVP は同期 `status=draft` POST のみで完結させる。
- 他ループの本格化なし:
  `020` の `postgame` 連鎖と `021` の farm 3 ループ本格化はしない。固定版レーンの Draft 作成経路だけを先に通す。
- AIエージェント版 不使用:
  本 MVP は固定版レーン専用とし、AIエージェント版 への routing は作らない。

## TODO

【×】4 型の Draft 作成経路を定義した(番組 / 公示 / 予告先発 / 二軍成績)  
【×】source_trust を primary tier に固定した  
【×】`status=draft` のみで WP POST することを明記した  
【×】duplicate 回避条件(candidate_id 一意キー)を定義した  
【×】canary 条件(1 subtype × 1 件 + 24h 手動確認)を定義した  
【×】published に触らないことを明記した  
【×】mail / automation / env / secret 不可触を明記した  
【×】Batch API(023-026) と postgame 連鎖(020) / farm 3 ループ(021) を本便では扱わないことを明記した  
【×】AIエージェント版レーンに流さないことを明記した  

## 成功条件

- 4 型すべてで Draft 作成経路が定義されている  
- published には触らない  
- rumor 除外と duplicate 回避が入っている  
- canary 実行条件が明確  
- Codex A が後続の実装便にそのまま進める粒度になっている  
