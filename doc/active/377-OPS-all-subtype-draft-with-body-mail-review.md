# 377-OPS 全 subtype draft 化 + 本文付き mail で user 手動公開フロー

## meta

- status: DESIGN_LOCKED / READY_FOR_IMPL
- priority: P1 (事故防止 + SEO 品質担保)
- owner: Claude
- created: 2026-05-17
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/51

## user intent (2026-05-17 chat lock)

- 「今公開状態にしている。 ただ、 事故が起きるから下書きにして mail を送ってもらう。 それで判断して公開ボタンを押したものを公開にしたい」
- 「本文を読みたい」(mail 内で内容判断したい)
- 「お金はかからないなら全部がいいよね。 いずれ SEO 考えても」 → **全 subtype draft** 採用

## scope

publish 経路の全自動公開を停止し、 user 手動公開フローへ移行する。

1. **全 subtype draft 強制**:
   - 既存 `RUN_DRAFT_ONLY` env flag を `True` に切替 (or 同等の固定 gate)
   - subtype 例外なし (lineup / postgame / 公示 / news / x_short / 社会 / data-insight / YouTube 等 全部)
2. **mail に本文を埋め込む**:
   - 既存 `publish_notice_email_sender.py` の template を拡張
   - 各 draft 1 件あたり: **title (40 字) + 本文サマリ 600-1000 字 + 出典 URL + wp-admin edit link**
   - mail 1 通に複数 draft を list 形式で集約 (既存 batch 設計を踏襲)
3. **mail trigger を draft 作成時に変更**:
   - 既存 `publish_notice_scanner` は publish 時に発火 → draft 作成時に変更
   - 朝 (06:30 JST) / 昼 (12:00) / 夕 (17:30) / 夜 (22:00) の 4 便 (既存 Scheduler 流用)
   - draft 0 件なら mail 送信 skip
4. **wp-admin edit link**:
   - mail 内 link: `https://yoshilover.com/wp-json/wp/v2/posts/<id>?context=edit` ではなく `https://yoshilover.com/wp-admin/post.php?post=<id>&action=edit`
   - user が WP login 済 cookie ある状態でクリック → 編集画面 → 「公開」ボタン

## 不可触

- 既存 publish 済記事 (retroactive 変更なし、 forward-only)
- X / SNS 自動投稿 (既に OFF 維持、 状況不変)
- wp-admin / WP plugin 構成 (login 経路は user 既存)
- env / Secret は最小変更 (RUN_DRAFT_ONLY=True のみ追加)
- Scheduler は既存 publish-notice trigger 流用 (新規 trigger 追加なし)
- 公示の subtype 検出 logic (377 とは独立、 376 / 069144 chain 別軸)

## flow 図

```
[既存]
fetch → article 生成 → publish (auto) → mail 通知 (publish 後)

[377 後]
fetch → article 生成 → draft 確定 →
  → 4 便 mail (本文付き list)
  → user mail で内容判断
  → OK なら mail 内 admin link click
  → WP 編集画面で「公開」ボタン
```

## 改修対象 file (想定)

| file | 変更内容 |
|---|---|
| Cloud Run env (`yoshilover-fetcher`) | `RUN_DRAFT_ONLY=True` 追加 |
| `src/wp_client.py` | RUN_DRAFT_ONLY=True 時 全 create_post を status=draft に強制 (既存 logic 拡張) |
| `src/publish_notice_scanner.py` | trigger を「publish 検出」→「draft 検出」に変更、 24h window 内の draft list 生成 |
| `src/publish_notice_email_sender.py` | mail template に本文サマリ (600-1000 字、 first H2 抜粋) + wp-admin edit link + 出典 URL を追加 |
| `src/publish_notice_scanner.py` の subtype filter | 全 subtype を mail 通知対象に (現状 一部限定なら) |
| tests/test_*_draft_mode.py / tests/test_publish_notice_email_*.py | 新規 mail 本文 / draft mode test |

## 成功条件

1. fetcher が新規記事を作る時、 全 subtype が `status="draft"` で WP に landed
2. 既存 publish 済記事は変更なし
3. 朝/昼/夕/夜 の publish-notice trigger 発火時、 24h window 内の draft list mail が送信される
4. mail 本文に **title + 本文サマリ 600-1000 字 + wp-admin edit link** が含まれる
5. wp-admin link クリックで user が WP 編集画面に到達 → 「公開」ボタンで publish 可能
6. X / SNS / Scheduler / Secret / WP既存記事 は不変

## risk + 対処

| risk | 対処 |
|---|---|
| 試合スタメンが時刻通り公開されない (試合前に user が承認しないと表示されない) | user lock 「全 subtype OK」を尊重、 user 朝/昼 mail check で対応 |
| mail サイズ膨張 (本文 1000 字 × N 件) | 1 mail 上限 5-10 件、 N 件超は次便繰越 or summary 化 |
| wp-admin link が expired / cookie 切れ | user は WP に login し直し |
| 既存 publish lane の test が draft 化で fail | draft 期待値の test 修正 (期待値を draft に変更) |
| Cloud Run env 変更 (RUN_DRAFT_ONLY=True) で他 lane に副作用 | RUN_DRAFT_ONLY は server.py で参照済、 wp_client 側で full enforce 形に拡張 |

## cost

- 全部 ¥0 (env flag 切替、 mail 既存 SMTP 流用、 Cloud Run free tier 内)
- LLM 不使用 (memory rule [[feedback_title_no_ai]] 維持)

## phase (2026-05-17 PM 改訂、 risk 明示版)

### Phase 1A (着地済 commit bdcf185)

- src/wp_client.py: RUN_DRAFT_ONLY=True 時 publish→draft 強制
- pytest 4 件、 backward compat 確認済

### Phase 1B (着地済 commit 2035c6b)

- PublishNoticeRequest に body_excerpt / admin_edit_url field 追加
- build_body_text が両 field を表示
- pytest 6 件、 minimal body mode 不変確認済

### Phase 1C (未着手、 次 session)

scanner / runner を改修して body_excerpt + admin_edit_url を populate。
**risk が複数あるため事前に inventory 必要**:

1. **PublishNoticeRequest 構築箇所の inventory** (5 箇所以上、 全部 grep で洗い出す)
   - scanner: scan_guarded_publish_history / scan_post_gen_validate_history / scan_preflight_skip_history / _scan_direct_publish_phase / _scan_review_phase
   - 各箇所で body_excerpt + admin_edit_url を populate する必要あり (silent skip した箇所は古い mail のまま)

2. **body 抜粋の source 決定** (3 option):
   - (a) guarded_publish JSONL に body 追記 → runner 改修必要、 historical data 互換性
   - (b) WP REST で post_id から body fetch → latency +200ms / fail mode +1
   - (c) candidate row.body から直接取得 → guarded_publish_runner で既に in-memory ある場合
   - 推奨: (c) → (b) fallback。 (c) でほとんどカバー、 残りは REST で取り直し

3. **admin_edit_url の builder**:
   - format: `{wp_base_url}/wp-admin/post.php?post={post_id}&action=edit`
   - wp_base_url は env WP_URL から (既存)
   - canonical_url から post_id 抽出 helper (既に存在? grep verify 必要)

4. **excerpt 化** (600-1000 字):
   - HTML strip + whitespace collapse
   - 既存 helper (_strip_html / _normalize_summary 等) 流用検討
   - 「📌 関連ポスト」「💬 ファンの声」section は除外 (X embed が visual ノイズになる)

### Phase 2 (env apply)

- Cloud Run yoshilover-fetcher env に RUN_DRAFT_ONLY=True 追加
- 自然 fire で mail 受信 verify
- 既存 publish 済記事の non-mutation 確認

## risk + 対処 (再定義)

| risk | 影響 | 対処 |
|---|---|---|
| scanner 3000+ 行で改修箇所 silent skip | mail の一部だけ body 出る、 一貫性無 | Phase 1C-1 で全 PublishNoticeRequest 構築箇所を grep で洗い出し、 改修対象を確定してから着手 |
| guarded_publish JSONL に body 未格納 | (c) option 失敗 | (b) WP REST fallback で救う、 fail-open (body 空のまま mail 送る) |
| WP REST fetch の latency / fail | scanner 遅延 / mail 遅延 | timeout 5s + fail-open (body 空) + log warning |
| 既存 mail の minimal body mode に副作用 | publish 通知が冗長になる | body_excerpt None 時は minimal body 不変 (Phase 1B で verify 済) |
| RUN_DRAFT_ONLY=True で試合スタメンも draft | 試合前の即時公開できない | user lock 「全 subtype OK」 (2026-05-17、 SEO 考慮) で受容、 朝 mail で対応 |
| 試合中の live_update も draft | 試合速報の即時性消える | user lock 受容。 必要なら個別 subtype に exception flag 追加 (Phase 3) |
| WP login cookie 切れで admin link click 失敗 | user が WP login し直し必要 | 既存 WP 動作、 範囲外 |
| 既存 publish 済記事への retroactive 影響 | 公開済記事が draft 化される | wp_client は status downgrade しない (existing post の status は触らない logic)、 forward-only |
| mail サイズ膨張 (本文 1000 字 × N 件 = 数 KB) | SMTP 無料枠の制限 | 1 mail 上限 5-10 件、 N 件超は次便繰越 (既存 batch 設計) |

## rollback plan

- Cloud Run env `RUN_DRAFT_ONLY=False` (1 toggle) → 即座 publish 経路復活
- code 自体は backward compat (両 field None で minimal body 不変)、 revert 不要
- 既存 publish 済記事は不変、 ロールバック後の publish も従来通り

## 着手前の pre-flight checklist (Phase 1C 開始時)

- [ ] PublishNoticeRequest 構築箇所を `grep -n "PublishNoticeRequest(" src/`で全 site 抽出
- [ ] 各 site の caller flow を 1 つずつ trace (silent skip しない)
- [ ] guarded_publish_runner が JSONL に body を書いてるか実 file で verify (memory rule)
- [ ] _strip_html / _normalize_summary 等の既存 helper の挙動を sample data で verify
- [ ] admin URL builder の format を 既存 WP_URL config から正確に組み立て (env mismatch 無)
- [ ] dry-run mail 1 件で body / admin link / 本文長 を実 mail に出して目視 verify
- [ ] pytest 全 publish_notice 系 + 関連 wp_client / scanner test pass
- [ ] Cloud Logging で env apply 前の base line 取得 (mail 件数 / 失敗率)

## 完了条件 (再定義)

1. 全 subtype が `status="draft"` で WP に着地 (Phase 1A 着地済)
2. 既存 publish 済記事は変更なし (forward-only)
3. mail に title + 本文サマリ 600-1000 字 + wp-admin edit link が含まれる (Phase 1B + 1C)
4. user が WP login 済状態で admin link → 編集画面到達 → 「公開」 publish 可能
5. X / SNS / Scheduler / Secret は不変
6. mail 1 通あたりサイズ < 50 KB
7. dry-run で実 mail を目視確認、 受け入れ後 env apply
8. rollback 手順 (env=False) を 1 step で実行可能

## next action

次 session で Phase 1C-1 (PublishNoticeRequest 構築箇所の inventory) から開始。
全 inventory 完了 → 改修対象確定 → 7 点提示 → user GO で実装。

---

## 🛑 次 session 開始時の必須 verify protocol (AI 事故源 対策)

memory rule: **AI は「記憶から再構成」「silent skip」「自己評価 OK」が最大の事故源。**
ticket と commit message を読んだ「気になる」状態で着手しない。 以下を **コピペで実行** し、 1 次 source で **現在状態** を確認してから判断する。

### 1. 現在の deploy 状態を image tag で verify (記憶ではなく gcloud で確認)

```bash
gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite --format='value(spec.template.spec.containers[0].image)'
```

期待: tag に `377-phase1ab-` が含まれているか、 もしくはそれ以降の commit hash。
含まれていない場合: Phase 1A / 1B の deploy が rollback されたか、 別 image に上書きされた。 ticket の「着地済」記述を **信じず**、 git log で commit が remote にあるか check。

### 2. Phase 1A wp_client draft 強制が実際に効いているか実コードで grep

```bash
grep -n "RUN_DRAFT_ONLY" src/wp_client.py
```

期待: `create_post` 内に `RUN_DRAFT_ONLY` を見て publish→draft 降格する block がある。
無ければ: commit が revert された。 1A から再着手。

### 3. Phase 1B PublishNoticeRequest field の存在確認

```bash
grep -n "body_excerpt\|admin_edit_url" src/publish_notice_email_sender.py
```

期待: dataclass 定義に両 field、 `build_body_text` 内で minimal body mode 内に両 field を展開する block。
無ければ: revert された。 1B から再着手。

### 4. env RUN_DRAFT_ONLY の現状 (Cloud Run env、 production)

```bash
gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite --format='value(spec.template.spec.containers[0].env)' | tr ';' '\n' | grep -i "RUN_DRAFT_ONLY"
```

期待: 空 (= env 未設定 = default False) もしくは `name=RUN_DRAFT_ONLY value=False`。
**True になっていたら**: Phase 2 が既に apply 済。 即座に Cloud Logging で publish 状態を verify (本当に draft 化されているか実 post で確認) してから次に進む。

### 5. Phase 1C 着手前の inventory (PublishNoticeRequest 構築箇所全部)

```bash
grep -n "PublishNoticeRequest(" src/publish_notice_scanner.py src/publish_notice_email_sender.py src/guarded_publish_runner.py
```

期待: 5-7 箇所 hit。 各箇所の関数名を **書き出してから** 改修対象を決める。
**「主要な X 箇所だけやれば良い」と判断しない**。 全箇所 reviewer 視点で trace。

### 6. guarded_publish_runner の JSONL に body が含まれるか実 file で verify

```bash
ls -lt /tmp/guarded_publish*.jsonl 2>&1 | head -3  # local sample
# または production:
gsutil ls gs://yoshilover-publish-history/ 2>&1 | head -5
```

期待: JSONL 1 件読んで、 entry 内に `body` または `content` field があるか確認。
無ければ: Phase 1C で body fetch source を (c) candidate row ではなく (b) WP REST fallback に決める根拠になる。

### 7. WP REST で post body 取得の sample 確認

```bash
python3 -c "
import os, urllib.request, base64, json
from dotenv import load_dotenv; load_dotenv()
u=os.getenv('WP_USER'); p=os.getenv('WP_APP_PASSWORD')
auth=base64.b64encode(f'{u}:{p}'.encode()).decode()
# 直近 draft 1 件を取得 (status=draft で filter)
url='https://yoshilover.com/wp-json/wp/v2/posts?status=draft&per_page=1&_fields=id,title,content,link&context=edit'
req=urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
r=json.loads(urllib.request.urlopen(req, timeout=20).read())
print(json.dumps(r[:1], ensure_ascii=False, indent=2)[:1500])
"
```

期待: 既に draft が WP に存在し、 body が取れる。 取れたら excerpt 化 helper の design に進める。

---

## 🚫 次 session で **やってはいけない** こと (silent skip / 記憶再構成 対策)

### NG 1: ticket の「着地済」だけ見て Phase 1C に着手

→ deploy 状態 / commit 状態を **gcloud + git で 1 次 source 確認** してから着手。 image tag が違ったら別問題 (rollback / 上書き) を先に解決。

### NG 2: 「PublishNoticeRequest 構築箇所は主要な 1-2 箇所」と決め打ち

→ grep で 全箇所 inventory、 各箇所の caller flow を **trace してから** 改修対象を確定。 「他の箇所は影響しないはず」は silent skip。

### NG 3: WP REST で body 取れると仮定して latency 見積もり

→ verify protocol #7 を実行して、 sample で body 取れるか確認。 timeout / error rate を base line として記録してから設計。

### NG 4: 「既存 test 通れば OK」で deploy

→ dry-run で実 mail body を **目視 verify** (本文抜粋 / admin link / サイズ / 改行) してから env apply。 SMTP が来ない / 文字化け / link 切れ は test だけでは検出不能。

### NG 5: 「env apply は 1 toggle なので safe」と楽観

→ apply 後の 1 fire (朝 06:30 JST or 手動 trigger) を待って publish 数 / draft 数 / mail 件数を Cloud Logging で **数値で verify**。 「動いてるはず」は事故源。

### NG 6: 「Phase 1A + 1B 着地済の前提が崩れた時の handling」を未定義のまま進める

→ verify protocol #1-3 で前提崩れを検出した場合の手順を 先に決める。 「revert された / image 上書き」のリカバリ手順は本 ticket に明記してない (今後追記)。

---

## 📝 着手 commit に必ず書く内容 (将来の自分への申し送り)

各 Phase 1C / 2 commit message に以下を含める:

```
# verify 実施 (本 commit 着手前)
- gcloud run services describe ... → image tag: ...
- grep RUN_DRAFT_ONLY src/wp_client.py → present at line ...
- PublishNoticeRequest 構築箇所 inventory: 5 件 (line ..., ...)
- WP REST sample fetch → body 取得 OK (latency Xms)
- dry-run mail body サイズ X KB / 内容目視 verify pass

# 改修 scope
- 触る file: ...
- 触らない file: ...

# rollback
- env RUN_DRAFT_ONLY=False で 1 toggle 復旧
```

これで次 session 以降も「記憶」「silent skip」「自己評価」を回避できる。

---

## 📌 user GO 待ち事項 (現時点 open)

- なし (Phase 1A + 1B 着地済、 env apply は Phase 1C 完了後)

## 📌 user 操作待ち事項

- WP login (cookie 保持) → Phase 2 env apply 直前
- 翌日朝 mail check → Phase 3 受け入れ判断

## 関連 ticket / memory

- `[[feedback_title_no_ai]]` (LLM 不使用)
- `[[feedback_publish_forward_must_check_gate_reason]]` (公開境界、 X 投稿 user 手動)
- `[[feedback_publish_vs_xpost_3_gate]]` (公開と SNS 分離)
- 344-INGEST Phase 1a-7 (YouTube 経路は既に draft 化、 force-draft revert され auto-publish 戻ったが、 本 377 で再び draft 化される)
- 376-QA-person-tag-routing-and-noindex (人物タグ noindex 進行中)

## next action

着手前 7 点を user に提示 → user GO 後 Phase 1 から narrow PR で実装。
