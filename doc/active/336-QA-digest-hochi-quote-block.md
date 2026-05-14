# 336-QA digest body に報知引用 block 追加(報知優先・模倣しない)

## meta

- ticket: 336-QA-digest-hochi-quote-block
- owner: Claude Code
- status: DESIGN_LOCKED / BLOCKED_BY_335-QA_RAW_HTML_FIX
- priority: P1(digest 体験の核、334-QA 完成度向上)
- created: 2026-05-14
- numbering reserved: README で追加予定
- depends_on: 引用 block raw_html fetch 修復(現在 1b1b8d4 で diagnostic log deploy 済、11:00 fire log 待ち)
- related memory: `project_multi_source_digest_subtype` / `feedback_title_no_ai` / `feedback_title_clickable_descriptive`

## user intent(2026-05-14 chat lock)

「**digest 記事に報知の引用 block を入れたい、報知優先だが報知に似せたくない**」

つまり報知を **一次 source(literal 引用 token のみ)** として使い、編集 framing は yoshilover original を維持。

## scope

334-QA digest の body renderer を拡張し、cluster 内に報知 source が存在する場合、`<aside class="nomotoke-source-excerpt">` block(66824 と同 pattern)を embed する。報知の raw_html から 600字 literal を抜き出して挿入、AI / LLM 一切なし。

## design lock: 「引用するが模倣しない」

| 構成要素 | source | yoshilover original な部分 |
|---|---|---|
| title | 報知本文から literal selfie + event token | 組み立て format `選手名「セリフ」イベント` (のもとけ風) |
| body 冒頭 opener | 報知の long quote 80-150字 literal | 「」枠 + 選手名 prepend |
| 地の文 3-5 行 | 報知 body の literal sentences | sentence 区切り display |
| **📖 報知 本文抜粋 block (本 ticket で追加)** | 報知 raw_html から 600字 literal | section heading + 出典明示 + CSS 太字 (既に 335-QA で適用済) |
| 🌐 各社が伝える | 子媒体の見出し抜粋 literal | 並べる構造 (yoshilover 独自) |
| 📣 公式が発表 | 巨人公式 / NPB 公式 literal | hub 構造 (yoshilover 独自) |

報知の **narrative / 論調 / 並び順は模倣しない**(rewrite 禁止 + section heading 違い + 多媒体 hub 化で区別)。

## clustering 優先順位 lock(報知優先、parent 選択 override)

既存 parent 選択は「本文最長 + tiebreaker (source_trust → published 早)」だが、本 ticket で **報知優先 rule を上書き** する:

```
親候補 選択優先順:
  1. cluster 内に 報知 (hochi family) があれば → 報知を 親 に固定
  2. 無ければ既存 logic (本文最長) に fall-through
```

理由:
- 報知の literal を title selfie + event + body excerpt の全てに使うため、cluster 内に報知あれば親に固定するのが一貫性が出る
- 報知優先 rule で digest の `📖 本文抜粋 block` の source URL も title source URL と一致

## body structure(D 追加後)

```
[選手名]「[親=報知のセリフ 20-40字]」[event]            ← title source = 報知
(地の文 3-5行、報知 body から literal)

📖 報知 本文抜粋
<aside class="nomotoke-source-excerpt">
  <span class="nomotoke-source-excerpt__label">📖 本文抜粋</span>
  <blockquote class="nomotoke-source-excerpt__body">
    <p>(報知 raw_html から 600字 literal、335-QA で太字適用済)</p>
  </blockquote>
  <p class="nomotoke-source-excerpt__attr">— スポーツ報知</p>
</aside>

【🌐 各社が伝える】
▼ サンスポ:「短い見出し or 抜粋 (literal 30-50字)」 → 元記事リンク
▼ 日刊スポーツ:「...」 → 元記事リンク
▼ デイリー:「...」 → 元記事リンク
▼ 東スポ:「...」 → 元記事リンク

【📣 公式が発表】
▼ 巨人公式X:「公式 post literal」 → リンク
▼ NPB公式:「公式 release literal」 → リンク
```

## phase 分割

### Phase 1: clusterer の報知優先 + 報知 raw_html 同梱

- `src/player_voice_digest_clusterer.py` の `_pick_parent` を「報知優先」に変更
- DigestCluster に `hochi_raw_html_excerpt: str = ""` field 追加
- cluster 検出時、報知 candidate が存在すれば raw_html を fetch + 600字 excerpt 抽出して payload に同梱
- 報知が cluster に無い場合は空文字、Section X omit
- +60 行程度 + tests

### Phase 2: body renderer に excerpt block 描画

- `src/player_voice_digest_body_renderer.py` で payload.hochi_raw_html_excerpt が空でなければ section 描画
- 既存 `nomotoke-source-excerpt` HTML 構造 + 335-QA CSS 太字を再利用(新規 CSS 不要)
- 出典 attribution は「— スポーツ報知」固定
- +40 行程度 + tests

### Phase 3: rss_fetcher 接続(自動)

- Phase 2c の `_aggregate_player_voice_digest_candidates` で payload 構築する際に Phase 1 の hochi excerpt も含める
- 既存 mutation flow に payload field 追加するだけ、+10 行

### Phase 4: live canary

- 翌朝 06:00 fire(overnight 媒体集中)で digest 発火、報知引用 block 含む article が draft 化されるか観察
- noindex / X OFF 維持

## 不可触リスト

- AI / LLM call を新 path に持ち込まない(`feedback_title_no_ai` 継承)
- 既存 published 記事の遡及修正なし(forward-only)
- 報知 narrative / 並び順を rewrite しない(literal 600字のみ、改変なし)
- 335-QA CSS(太字) を改変しない(再利用のみ)
- 既存 334-QA digest path / 単記事 path への影響 0(additive)
- publish / mail / scheduler / env(`ENABLE_PLAYER_VOICE_DIGEST_DETECTION` 維持) は本 ticket scope 外

## success criteria

- Phase 1: clusterer test +5 件、報知優先 + raw_html excerpt 抽出確認
- Phase 2: body renderer test +5 件、HTML 中に `nomotoke-source-excerpt__body` 出現
- Phase 3: integration test +3 件、payload field 流通確認
- Phase 4 canary: 朝 06:00 fire で digest 1 本以上が draft 化、引用 block 含む、太字 live

## next action

**BLOCKED until 335-QA raw_html fetch 修復**。Cloud Run で hochi.news / その他 news サイトの raw_html が空返却される問題が解決した時点で、本 ticket Phase 1 から narrow PR で着手。
