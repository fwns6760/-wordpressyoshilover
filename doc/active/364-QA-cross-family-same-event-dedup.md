# 364-QA 媒体違いの同じ巨人ニュース重複を止める

## meta

- status: READY
- priority: high
- owner: Codex
- lane: B
- created: 2026-05-16
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/33
- trigger: user asked whether past duplicate-news handling existed, and whether it was not working for Hochi / Sponichi / Daily style repeated Giants news

## 何が起きているか

報知 / スポニチ / デイリー / 東スポなどが、同じ巨人ニュースを別タイトル・別URLで出すことがある。
今の仕組みは同一URLや同一タイトルには強くなってきたが、媒体ごとに少し違うタイトルになると「別記事」として通りやすい。

その結果、読者から見ると「同じ話題の記事が連続している」状態になる。

## 過去にやったことと、残っている穴

現物確認した記録では、過去対策はある。ただし対象が狭い。

- `319-QA-fetcher-topic-dedup-and-slot-fill`
  - 同一話題 dedup は入っているが、主に「同一選手の頭部/ヘルメット + バット接触」事故系に限定。
  - 一般的な試合結果、選手コメント、登録抹消、昇格などの媒体違い重複までは潰さない。
- `339-INGEST` / `ENABLE_SAME_FAMILY_X_WEB_DEDUP`
  - 同じ媒体 family の X 速報 + Web 記事を束ねる仕組み。
  - 報知 X + 報知 Web には効くが、報知 Web + スポニチ Web のような媒体違いには効かない。
  - env flag は default OFF。
- `334-QA-player-voice-multi-source-digest-subtype`
  - 3媒体以上が同じ選手発言を報じたときに digest 化する設計。
  - 3媒体未満では発火しない。
  - 選手発言 digest 専用なので、試合結果や通常ニュース全般の重複抑止ではない。
- `363-QA-same-fire-cross-source-title-duplicate-stop`
  - 同じ実行内で「別URLだが生成タイトルが同じ」場合だけ止める。
  - タイトルが少し違う媒体違い重複には効かない。

つまり、過去対策は「効いていない」のではなく、誤判定を避けるために狭く作られている。
今回残っている穴は、**2媒体以上の同じ出来事を、別タイトルでも同一ニュースとして扱う層**である。

## 直す方針

いきなり全文類似やAI判定でまとめない。
まず source / metadata / title literal から作れる、機械的な `event_key` で安全な範囲だけ止める。

最初の対象:

- 同一日または同一試合
- 同じ選手名が明確
- 同じ出来事 token が明確
- 2媒体以上
- source family が別

対象にする出来事 token の例:

- `サヨナラホームラン`
- `逆転3ラン`
- `300号`
- `昇格`
- `登録抹消`
- `抹消`
- `途中交代`
- `負傷交代`
- `スタメン`
- `先発`
- `完封`
- `7回1失点`

初回実装では、曖昧な「勝利」「敗戦」「好投」「活躍」だけでは重複扱いしない。
別角度の記事を落としすぎるため。

## 難しい点と扱い

同じ試合でも、試合直後と翌日ではニュースの意味が変わる。
また、X 速報と Web 記事は役割が違うため、同じ URL ではなくても単純に全部を重複扱いすると落としすぎる。
一方で、新聞各紙が同じ事実を書くのは自然なので、同じ phase の同じ出来事を全部別記事にすると読者には重複に見える。

そのため、`event_key` だけでなく `phase_key` も持つ。

phase の初期案:

- `same_day_postgame`: 試合直後の結果 / 速報
- `next_day_deep_recap`: 翌日の振り返り / 朝記事 / 追加談話 / 背景整理
- `player_quote`: 選手本人コメント
- `manager_quote`: 監督コメント
- `roster_status`: 昇格 / 抹消 / 登録
- `injury_status`: 途中交代 / 負傷 / 状態確認
- `record_milestone`: 300号 / 通算記録 / 節目
- `lineup`: スタメン / 先発

同じ `game/date + player + event` でも `phase_key` が違う場合は、原則として別記事として残す。
たとえば「試合直後の勝利記事」と「翌朝の選手コメント記事」は潰さない。
特に `same_day_postgame` と `next_day_deep_recap` は、読者にとって役割が違うため dedup 対象外にする。

逆に、同じ `phase_key` の中で同じ `player + event` なら重複候補にする。
たとえば、同じ翌朝に報知とスポニチが「坂本勇人 300号サヨナラホームラン」を出した場合は 1本に絞る。

## 新聞各紙が同じことを書く前提の扱い

媒体違いの同一ニュースは、単に 2本目を捨てるだけでは情報価値が落ちる。
方針は「記事は 1本、他紙は本文内の出典リンクとして束ねる」。

初期実装の理想形:

- 親記事を 1本だけ作る。
- 親は source priority と本文/summary量で選ぶ。
- 2本目以降の媒体は `related_sources` として保持する。
- 本文に `他紙も報じています` のような短い出典リンク欄を追加できるようにする。
- ただし、既存 publish 済み記事を自動で書き換えるのは初回 scope 外。

つまり `skip` は「無視」ではなく「別記事としては作らず、同じ話題の補足 source として扱う」意味にする。
初回で本文統合まで危ない場合でも、少なくとも log / summary には kept source と skipped source を残す。

## X と Web の扱い

X と Web は同じ情報源でも役割が違うため、媒体違い Web 記事と同じルールにしない。

- 同一媒体の X + Web
  - 既存 `339-INGEST` の領域。
  - 原則 Web を親にして、X は補足素材にする。
- 公式 X + 媒体 Web
  - 公式 X は一次情報として価値があるため、すぐ捨てない。
  - 同じ event の Web 記事がある場合は、Web 記事を本文主役にし、公式 X は補足候補にする。
- 媒体違い Web + Web
  - 本 ticket の主対象。
  - 同じ phase / player / event なら 1本に絞る。
- X だけ複数
  - 初回では強く潰さない。
  - X は短文で event token が弱いことが多く、誤判定しやすいため。

## 翌日ニュースの扱い

翌日ニュースは「前日の焼き直し」もあれば「新しい談話・状態・記録の整理」もある。
そのため、翌日というだけで重複扱いしない。
むしろ翌日記事は、試合直後より深い記事になりやすいので、直後記事とは別価値として扱う。

残す条件:

- 新しい選手コメントがある
- 監督コメントが主題
- 登録 / 抹消 / 状態確認など新しい事実がある
- 記録達成の整理など、`record_milestone` として主題が明確
- 前日試合の背景整理、起用理由、本人談話、監督談話が増えている

止める条件:

- 同じ phase
- 同じ選手
- 同じ強い event token
- 別媒体だが主題が同じ
- 新しい fact token が見つからない
- 翌日記事同士で、どちらも同じ浅い焼き直しに見える

## 期待する挙動

同じ実行内で以下のような候補が来た場合、2本目以降を作らない。

- 報知: `坂本勇人が通算300号、劇的サヨナラ弾`
- スポニチ: `巨人・坂本勇人、300号サヨナラホームラン`

この場合は `player=坂本勇人`、`event=300号サヨナラホームラン`、`date/game` が一致するため同一ニュースとして扱う。

一方、以下は落としすぎる危険があるため初回では止めない。

- 報知: `巨人がDeNAに勝利`
- スポニチ: `阿部監督が試合後にコメント`

同じ試合でも、記事の主語と出来事が違うため別記事として残す。

## 実装スコープ

触ってよい:

- `src/rss_fetcher.py`
- 必要なら duplicate / event key helper module
- `tests/test_duplicate_prevention_golden.py`
- 必要なら新規 `tests/test_cross_family_same_event_dedup.py`
- 本チケット
- `doc/README.md`
- `doc/active/assignments.md`

触らない:

- Scheduler
- Cloud Run env
- Secrets
- WP 既存記事の修正 / 削除
- X / SNS 投稿
- publish 条件
- mail 条件
- source 追加
- 既存 334 digest の仕様変更

## 実装案

1. candidate から `cross_family_event_key` を作る。
   - 日付または game_id
   - Giants player literal
   - event token literal
   - subtype
2. 同じ run 内で `cross_family_event_key` が一致し、source family が違う場合は 2本目以降を skip。
3. skip 時は silent skip しない。
   - `cross_family_same_event_duplicate_skip` の構造化ログを出す。
   - skip reason に source family / kept URL / skipped URL / event key を残す。
4. どちらを残すかは source priority で決める。
   - 初期案: 報知 > 日刊 > スポニチ > サンスポ > デイリー > 東スポ > その他
   - 同順位なら本文/summary が長い方、さらに同じなら早い方。
5. 2本目以降は `related_sources` payload に残す。
6. `event_key` が弱い場合は skip しない。

## 受け入れ条件

- 報知 + スポニチの同一選手・同一出来事・同一日候補は 1本だけ通る。
- デイリー + 東スポの同一選手・同一出来事・同一日候補は 1本だけ通る。
- 2本目以降の媒体 URL / 見出し / source family は `related_sources` または構造化ログに残る。
- 同じ試合でも player または event token が違う候補は両方残る。
- 同じ試合でも phase が違う候補は原則両方残る。
- 「勝利」「敗戦」「活躍」だけの弱い token では dedup しない。
- 公式 X は媒体 Web と同じ扱いで即捨てず、補足素材として残す余地を持つ。
- skip は構造化ログに残り、silent skip にならない。
- 既存の同一URL dedup、同一タイトル dedup、same-family X+Web dedup の回帰がない。
- Scheduler / env / Secret / WP既存記事 / X / SNS / mail 条件を変更しない。

## 検証予定

- 新規 fixture test:
  - cross-family same player same event -> second candidate skipped
  - cross-family same game different player/event -> both kept
  - weak event token -> both kept
  - source priority keeps stronger family
- 関連テスト:
  - `python3 -m py_compile src/rss_fetcher.py tests/test_duplicate_prevention_golden.py`
  - `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_reliability_2026_05_08.py -q`
  - 追加 test file があればそれも実行

## 完了条件

- 実装 diff がある。
- 上記テストが PASS している。
- deploy する場合は Cloud Build / Cloud Run revision / `/health` の証跡を残す。
- 本番 log で `cross_family_same_event_duplicate_skip` または自然 fire での対象なしを確認する。
- GitHub Issue を完了証跡つきで close する。

## STOP条件

- AI が本文意味を推測して event key を作らないと判定できない。
- 弱い token まで止めないと効果が出ない。
- 2媒体ではなく 3媒体 digest の仕様変更に広がる。
- publish / mail / scheduler / env 変更が必要になる。
- 同じ試合の別角度記事まで落ちる fixture が出る。
