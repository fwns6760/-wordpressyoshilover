# 458 DATA-SITE 専用layout + トピッククラスタ三方向導線

- **種別**: 実装 / **priority**: P1(設計の核) / **effort**: M
- **親**: 443 / 設計: `455...md` §2(導線)/ §9(実装規約)/ §7(コンポーネント) / GH: #122
- **status**: READY

## 背景(深掘り 1次source)

- 選手 pillar は WP標準記事テンプレ流用で、**関連記事がデータより上に来る逆転構造**。データ section が主役になっていない。
- トピクラが**片方向**:索引→選手 ◯ / 選手→関連記事 ◯ だが、**通常記事→選手データの逆リンク ×**(通常記事 `/74462` 実取得で `/data/` link 0)、**同ポジ横リンク ×**、**記事単位SNSシェア ×**。

## ゴール

1. **データ上・記事下**の専用 layout(pillar/cluster/team で記事テンプレ脱却)。
2. **三方向内部リンク**:
   - ① 記事→pillar: 通常記事(postgame/lineup/data)本文に登場選手の `📊{選手名}のデータ→/data/{slug}/` を entity→slug マップ(`config/npb_12team_roster.json` 系)で自動挿入。**未解決 entity は出さない**。
   - ② pillar→記事: 関連記事を**データ section より下**に固定。
   - ③ pillar⇄pillar: 同ポジション/当日対戦相手の横リンク(サイドバー)。
3. 全 data ページに**パンくず + 更新日バッジ(generation時刻) + 記事単位SNSシェア**(X/LINE)。

## 対象

- 記事テンプレ層(entity→slug 挿入): 既存記事生成 path のうち data-site連携部分のみ。**publish/mail/X 本体ロジックは不可触**。
- `src/data_site_template_pillar.py` / `data_site_template_cluster.py`: layout・横リンク・SNS・更新日。
- entity→slug マップ: 既存 roster 再利用。

## やる / やらない

- やる: 三方向リンク自動生成、専用layout、パンくず/更新日/SNS、test。
- やらない: publish/mail/X lane の挙動変更、新カテゴリ、既存記事の一括書き換え(forward-only)。

## 成功条件

- postgame 記事に登場選手の `📊データ→` が入り pillar へ遷移できる(①、誤リンク0)。
- pillar でデータが上・関連記事が下。同ポジ横リンクが機能。
- 全 data ページにパンくず+更新日+SNSシェア。
- targeted pytest green、live で1記事→pillar 往復 verify。

## 依存

弱: 456/457(split が増えると pillar の「データ上」の中身が厚くなる)。並行可。
