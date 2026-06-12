# 2026-06-12 年俸ページ OB 拡張 (前セッション切断分の再開)

- 前提: 午前に /data/salary 一覧+現役105選手を公開済 (`19bbd6bc` + `568be9a4`)。
  OB 拡張 (template OB 対応 + collector --ob モード) のコード途中でセッション切断、
  `/tmp/ob_urls.json` (OB URL 調査結果) 未作成のまま停止していた。
- 再開内容:
  - 週べONLINE `pid=db_search` (引退選手対応) で OB roster 47名を全probe。
    年俸データあり=27名 (うち岡本和真・長野久義は現役分として収録済 → 新規25名)。
    値が全欠測=20名 (王貞治/長嶋茂雄/金田正一 等レジェンド層、週べに行はあるが金額なし)。
  - nenshuu.net は現役 1049 名のみで OB ページ自体なし (sitemap404 + index実取得で確認)。
    → OB は週べ単独ソース。検証ポリシー通り、取れないレジェンド20名は bake しない。
  - parse_shube_salary_page 修正: 旧レイアウト ([年,'-',球団] + [年,金額,''] の2行分割、
    江川卓のページ等) を年単位マージで吸収。MLB 年は球団名に漢字なしの heuristic で
    league=MLB 判定 (棒グラフ色・注記が変わる)。
  - collect_ob: urls.json の kana fallback 追加 (週べプロフィールから検証した読みを
    沢村拓一=さわむら ひろかず 等3名分補完)。
  - template OB 文言: 「現役時代（1993〜2002年）」→「現役時代の推定年俸推移（掲載期間 …）」。
    松井秀喜は週べに NPB 年のみ (MLB 2003-2012 欠測) で、現役期間と誤読されるため。
- 着地: OB 25名 bake (計130選手) + 公開 26/26 ok (一覧更新 90667 + 新規 90799-90823)。
  一覧に「OB・歴代選手の年俸推移」節 (通算順、最高年俸/掲載期間付き)。live verify 200。
- 残: レジェンド20名 (王/長嶋/原/堀内/柴田 等) は機械可読ソースなし。
  別ソース (書籍/記事の個別検証) が取れた時に giants_salary.json へ手動追記すれば
  ページは自動で増える。

## 追記 (同日)
- 梶原昂希 gate skip は正当と確定 (2026-06 現在も DeNA、NPB.jp/nenshuu で確認)。現役は 105/105 で完了
- /data ハブ特集 nav に 💰年俸ランキング追加 (template `17552b25` + live WP REST patch page 73526)。トップページのデータチップには既に salary あり

## 追記2 (同日 トピクラ横リンク)
- 縦(hub→一覧→選手、パンくず、WP親子)は当初から接続済み。横(pillar↔salary)が双方向未接続だったため接続
- salary→pillar: pillar実在slug(90/130)のみ成績ページへリンク、再公開131/131 ok
- pillar→salary: _build_salary_link_html追加(a75b83f1)、image salary-crosslink-a75b83f1 build+job update+実行(qk6sf成功)
- live verify: 田中/坂本/松井/阿部=💰リンクあり、王貞治(salaryページなし)=リンクなし(gate正常)
