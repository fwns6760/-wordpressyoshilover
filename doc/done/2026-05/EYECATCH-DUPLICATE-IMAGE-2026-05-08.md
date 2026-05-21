# EYECATCH-DUPLICATE-IMAGE-2026-05-08

**status**: CLOSED LIVE_VERIFIED 2026-05-21 (5/8 incident 「同画像連番化 -1.jpg -9.jpg」 production audit で完全消失確認、 20 件サンプルで 13 unique media_id (5/8 incident は 10 連番 = 1 unique)、 残る 8 件同 63578 使用は 5/18 user 設定の意図的 yoshilover ブランド team fallback (commit `1eb41f5` 等 で `_TEAM_FALLBACK_MEDIA_ID_DEFAULT=63578`)。 5/8 fix 2 段 (`44d3fe1` diversified pool + `7b88694` og:image 強化) 効果あり。 残る per-person mapping miss (平山功太 / マルティネス) は別 issue、 mapping 補完で別途扱う)
**owner**: Claude(本 session 直接構築、user 明示 override)
**priority**: P1(user 体感 site 全面で同 thumbnail = 直視認可能なデグレ)
**created**: 2026-05-08 21:50 JST
**next_check**: 2026-05-09 morning(user が site で thumbnail 分散を確認)

---

## 1. 何が起きたか(user 報告 → 真因)

- 14:35 `c55fe8a` で team-fallback (id=23981 原辰徳) を None 化(原辰徳出すぎ問題 fix)
- 14:46 `7b88694` で og:image を全 source_type で featured_media に upload 強化
- 副作用: 共通 og:image を持つ source 群(日刊スポーツ等の汎用 banner)が全記事に upload され、WP が `0f3c160ddac8.jpg / -1.jpg / ... / -9.jpg` 連番化
- 結果: 直近 publish 全件で thumbnail が **md5=6b339d9d7c98 (70439 bytes) の同一画像** になる
- user 体感「アイキャッチデグレ」「全部直らん」

実測: 19:17–21:31 の 2 時間で同画像 10 copy(media id 65327 → 65403)を WP に upload 済。

---

## 2. 本 session で打った fix(2 段)

### 2-1. `44d3fe1` diversified player pool fallback

- 対象: `src/player_eyecatch_resolver.py`
- 内容: per-person miss + use_team_fallback=True 時、cache 内 7 player(吉川/大城/山崎/田中将/大勢/阿部/高梨)から `md5(title) % len(pool)` で deterministic 選択
- env: `PLAYER_EYECATCH_POOL_FALLBACK_DISABLED=1` で kill switch
- test 8 件追加(21/21 PASS)
- deploy: `yoshilover-fetcher-00279-tm4`(20:39 JST)
- **限界**: og:image upload chain で featured_media が立ってると resolver は呼ばれず、本 fix は機能しなかった

### 2-2. `aae90f2` 同 og:image URL 重複 upload skip

- 対象: `src/wp_client.py` + `src/rss_fetcher.py`
- 内容:
  - 新規 `WPClient.media_already_uploaded_for_url(url)`: 12-char `md5(url)` を slug として WP /media を search、既存があれば True
  - `_upload_featured_media_with_fallback` の各 candidate ループ先頭で dedup check、既存 slug は upload skip → 全 candidate dup なら 0 を返す
- log: `featured_media_skip_duplicate_source` 発火で観測可能
- test 4 件追加(全域 3457 PASS)
- deploy: `yoshilover-fetcher-00281-q9q`(21:46 JST)
- **期待効果**: 既出 og:image → skip → resolver 起動 → 2-1 の diversified pool が初めて意図通り発火 → 記事ごとに違う player photo

---

## 3. verification gate(user 朝確認)

site トップ / アーカイブで:

| 確認項目 | 期待 | 失敗 signal |
|---|---|---|
| thumbnail 分散 | 5/9 朝の publish 群で各記事が異なる image | 全件同 image なら fix 失効 |
| 過去 16 件(deploy 前 fm=0) | そのまま fm=0 維持(user 指示で触らない) | — |
| 関係ない player 写真 | 「他の選手」fallback の挙動として user 受容済 | — |

cloud log で:

```
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name="yoshilover-fetcher" AND (textPayload:"featured_media_skip_duplicate_source" OR textPayload:"eyecatch_diversified_pool_used")' --project=baseballsite --limit=20 --freshness=12h
```

両 event の発火回数で「dedup → diversified pool」chain が機能してるか定量確認。

WP /media で:

```
curl -s "https://yoshilover.com/wp-json/wp/v2/media?search=0f3c160ddac8&per_page=20&_fields=id,date" | python3 -m json.tool
```

5/9 朝の追加 upload が止まってれば fix 成功(直近 entry が 21:31 の id=65403 で停止)。

---

## 4. rollback path(失敗時)

| 軸 | 方法 |
|---|---|
| 全 fix 撤回 | `gcloud run services update yoshilover-fetcher --image=...:48e1bbb`(本日 14:00 頃の状態) |
| `aae90f2` のみ撤回 | `gcloud run services update yoshilover-fetcher --image=...:44d3fe1`(diversified pool は残す) |
| diversified pool kill | env `PLAYER_EYECATCH_POOL_FALLBACK_DISABLED=1` 追加 |

いずれも env / scheduler / WP データには影響しない、可逆。

---

## 5. 残タスク(user 朝判断後)

- [ ] 5/9 朝 user が site で thumbnail 分散を確認
- [ ] cloud log で `featured_media_skip_duplicate_source` + `eyecatch_diversified_pool_used` 発火数確認
- [ ] 直ってれば → ticket を `doc/done/2026-05/` に move、CLOSED
- [ ] 直ってなければ → 5 章 rollback path のいずれか実行 + Codex に audit 委譲(本 session で再修正しない)
- [ ] 過去 16 件 fm=0 backfill の判断は user 領域、本 ticket scope 外

---

## 6. 教訓(本 session の Claude failure)

1. user の「アイキャッチデグレ」を最初に「fm=0 出てる」と狭く解釈、`44d3fe1` で fix した気になった
2. user の「直らん」を「過去記事を見てる」と誤解、site 上の実描画を確認しなかった
3. WP /media を 1 回 search すれば「同 image 10 copy」が直ぐ判明したのに気付くまで往復多数
4. 真因(=同 og:image 共通使い回し)を user の `Wordpress 見てみて` 指摘で初めて確認

**次回類似 issue に対する rule**: user の体感不具合報告時は **WP /media と site front-end を最初に確認**(REST GET と curl の 2 commands で 30 秒)。コード仮説より先に実機状態。

---

## 7. commit / image / revision 全部

| 階層 | 内容 |
|---|---|
| commit | `44d3fe1`(diversified pool)+ `aae90f2`(URL dedup) |
| image | `yoshilover-fetcher:44d3fe1` → `yoshilover-fetcher:aae90f2` |
| revision | `yoshilover-fetcher-00279-tm4` → `yoshilover-fetcher-00281-q9q`(100% traffic) |
| env | 変更なし(kill switch のみ optional) |
| scheduler | 変更なし(audit-notify-6x は 一旦 ENABLE → user 指示で PAUSE 戻し済) |
| WP mutation | なし(過去 backfill しない user 指示) |
