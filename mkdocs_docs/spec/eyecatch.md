# :material-image-frame: アイキャッチ (featured_media)

!!! info "これは何"

    WordPress 記事の「アイキャッチ画像」 をどう決めるかのルール。
    記事のサムネイル / OGP 画像として表示される画像の選び方。

## :material-ladder: 3 段 fallback ルール

優先順位は ==上から== 試して、 該当が無ければ次に進む。

!!! success "① 元記事のアイキャッチ"

    元記事 (報知 / サンスポなど) の og:image / featured media を取得できれば最優先で採用。
    最も文脈の合ったビジュアルになる。

!!! note "② 保存済みの選手写真"

    ①が無い、 かつタイトルに巨人選手 1 人が確定するなら、 その選手の保存写真を使う。

    !!! example "kill switch"

        env `EYECATCH_PLAYER_PRIORITY_DISABLED=1` で無効化可能。

!!! warning "③ 巨人チームマーク (固定)"

    ①②どちらも該当しないとき、 ==巨人マーク (固定 media_id `63578`)== を使う。
    空アイキャッチは絶対に出さない。

    実装場所: `src/player_eyecatch_resolver.py:98` の `PLAYER_EYECATCH_TEAM_FALLBACK_ID` (env) または default `63578` を当てる。

## :material-code-tags: 実装

```
ファイル: src/rss_fetcher.py の 28200 行目付近
コメント: 「2026-05-13 user-requested order: ① source og:image → ② 保存選手写真 → ③ team fallback (巨人マーク)」
```

## :material-shield-alert: kill switch (env)

| env | 効果 | yoshilover-fetcher 実値 (2026-05-27) |
| --- | --- | --- |
| `EYECATCH_DEDUPE_RECENT_DISABLED` | 直近 1 時間以内に同じ画像を使った dedup を無効化 | 1 |
| `EYECATCH_PLAYER_PRIORITY_DISABLED` | ②保存選手写真の経路を無効化 (①と③のみ) | 1 |
| `PLAYER_EYECATCH_TEAM_FALLBACK_ID` | ③の固定 media_id を上書き (default `63578`) | (未設定 = default) |
| `PLAYER_EYECATCH_POOL_FALLBACK_DISABLED` | name pool fallback (②と③の中間) を無効化 | (未設定) |
| `PLAYER_EYECATCH_MAP_PATH` | 選手写真 map ファイルのパス上書き | (未設定 = default `config/player_eyecatch_map.json`) |

## :material-magnify: 提案 / 変更時の確認手順

!!! danger "user 確認の前に必ず実行"

    handoff doc 間で矛盾していることがあるので、 ==canonical は実コード + commit message を grep== する。

    ```bash
    cd /home/fwns6/code/wordpressyoshilover
    git log --grep=eyecatch --oneline | head -5
    grep -n "user-requested order" src/rss_fetcher.py
    ```

    過去 (2026-05-26 user 指摘) に「rule を知らずに handoff doc 矛盾を user に確認しようとして叱責」 事例あり。
    必ずコードを 1 次 source として確認すること。
