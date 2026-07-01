<?php
/**
 * Plugin Name: Yoshilover Data Noindex
 * Description: /data 選手ページのうち、無名・引退・成績僅少・関連ニュース無しの選手だけ noindex,follow を付与する。現役・首脳陣・主要OB(通算80試合以上)・外国人・2016年以降出場・関連ニュース有りは対象外(index維持)。follow は残すのでクロール導線は殺さない。有効化で即反映。削除すれば全ページ index に戻る(可逆)。
 * Version: 1.0
 * Author: yoshihiro
 *
 * 生成根拠 (2026-07-01): config/data_site_player_slugs.json を基に判定。
 *   保護(index維持) = 巨人名簿 / 首脳陣 / prosports関連ニュース有り / 外国人 /
 *                      通算80試合以上 / 2016年以降に出場 のいずれか。
 *   それ以外の「成績データ有り・全年度2015年以前・80試合未満・ニュース0」のみ noindex。
 *   成績データ欠損の選手は誤爆回避のため対象外(触らない)。
 * Cost: zero。純 wp_robots フィルタ。外部通信なし。DBマイグレーション無し。
 */

if ( ! defined( 'ABSPATH' ) ) { exit; }

function yoshilover_data_noindex_slugs() {
    return array(
        'abe-shigeki', // 阿部茂樹
        'aida-yushi', // 会田有志2026年
        'akamine-kenyuu', // 赤嶺賢勇
        'ando-motohiro', // 安藤元博
        'aoki-hiroaki', // 青木宥明
        'aoki-minoru', // 青木稔
        'arakawa-iwao', // 荒川厳
        'arita-fumio', // 有田二三男
        'baba-syohei', // 馬場正平
        'chiang', // 姜建銘
        'doki-michio', // 土岐道雄
        'eda-koichi', // 江田幸一
        'eguchi-yukio', // 江口行雄
        'enoki-yasuhiro', // 榎康弘
        'fujimoto-kenji', // 藤本健治
        'fujimoto-kensaku', // 藤本健作
        'fujimoto-shigeki', // 藤本茂喜
        'fujioka-hiroki', // 藤岡寛生
        'fujishiro-kazuaki', // 藤城和明
        'fujiwara-toshimi', // 藤原利美
        'fukamachi-ryosuke', // 深町亮介
        'fukata-takuya', // 深田拓也
        'fukumoto-atsushi', // 福元淳史
        'furukawa-yuki', // 古川祐樹
        'furuya-takeo', // 古家武夫
        'gotoh-mitsutaka', // 後藤光貴
        'hanekawa-ryu', // 羽根川竜
        'hara-syunsuke', // 原俊介
        'harada-akihiro', // 原田明広
        'hashimoto-keiji', // 橋本敬司
        'hayashi-chiyosaku', // 林千代作
        'hei-michio', // 屏道夫
        'hiraoka-masaki', // 平岡政樹
        'hirose-syuichi', // 広瀬習一
        'hoshino-masumi', // 星野真澄
        'hotta-akira', // 堀田明
        'igarashi-tatsuma', // 五十嵐辰馬
        'imaizumi-katsuyoshi', // 今泉勝義
        'inoue-yasuo', // 井上安雄
        'inoue-yoshihiro', // 井上嘉弘
        'inzen-tomoya', // 隠善智也
        'ishihara-sekio', // 石原碩夫
        'ishikawa-atsushi', // 石川厚
        'ishikawa-masami', // 石川雅実
        'itoh-hiroyasu', // 伊藤博康
        'itoh-takahide', // 伊藤隆偉
        'iwagoh-yasuhiro', // 岩郷泰博
        'iwao-takayuki', // 岩尾孝幸
        'izumida-kiyoshi', // 泉田喜義
        'kaburaki-yoshizumi', // 鏑木悦純
        'kachi-kenzaburo', // 加地健三郎
        'kada-tsugio', // 加田次男
        'kamogawa-shigeharu', // 加茂川重治
        'kaneyoshi-hiroshi', // 兼吉寛
        'kasahara-masayuki', // 笠原正行
        'kataoka-setsujiro', // 片岡節次郎
        'katoh-katsumi', // 加藤克巳
        'katoh-makoto', // 河東真
        'kawabe-tadayoshi', // 川辺忠義
        'kawatoh-ryunosuke', // 川藤竜之輔
        'kawauchi-kazutomi', // 川内雄富
        'kimura-syota', // 木村正太
        'kimura-yoshio', // 木村由夫
        'kitsugi-fumio', // 木次文夫
        'kobayashi-satoshi', // 小林聡
        'koga-hidehiko', // 古賀英彦
        'koharazawa-shigeyori', // 小原沢重頼
        'kohsaka-hidenori', // 香坂英典
        'kojima-keiichi', // 小島圭市
        'komatsu-toshihiro', // 小松俊広
        'kondoh-kingo', // 近藤金吾
        'kondoh-takamasa', // 近藤隆正
        'kuboki-kiyoshi', // 久保木清
        'kudoh-masaaki', // 工藤正明
        'kumabe-ichiro', // 隈部一郎
        'kume-yuki', // 久米勇紀
        'kura-nobuo', // 倉信雄
        'kuroda-yoshihiro', // 黒田能弘
        'maekawa-hachiro', // 前川八郎
        'maki-masaki', // 真木将樹
        'marumo-kenichi', // 丸毛謙一
        'masuda-akinori', // 益田明典
        'matsubara-yasushi', // 松原靖
        'matsuo-teruyoshi', // 松尾輝義
        'matsuoka-mitsuo', // 松岡光雄
        'matsushita-hidefumi', // 松下秀文
        'matsutani-ryujiro', // 松谷竜二郎
        'miki-hitoshi', // 三木均
        'minami-kazuaki', // 南和彰
        'minami-shinichiro', // 南真一郎
        'mino-katsuhiro', // 三野勝大
        'miyake-sogen', // 三宅宗源
        'miyazaki-kazuaki', // 宮﨑一彰
        'miyoshi-chikara', // 三好主
        'mizuno-tadahiko', // 水野忠彦
        'monna-tetsuhiro', // 門奈哲寛
        'moritani-akira', // 森谷昭
        'motohara-masaharu', // 本原正治
        'munesue-susumu', // 棟居進
        'murase-hiromoto', // 村瀬広基
        'nagahara-koji', // 長原孝治
        'nagai-yojiro', // 永井洋二郎
        'nagata-masahiro', // 長田昌浩
        'nakahama-hiroyuki', // 中濱裕之
        'nakajima-hiroto', // 中島浩人
        'nakajyo-yoshinobu', // 中条善伸
        'nakamura-hayato', // 中村隼人
        'nakamura-kunio', // 中村国雄
        'nakamura-masami', // 中村政美
        'nakamura-tsunetoshi', // 中村常寿
        'nakatsukasa-tokuzo', // 中司得三
        'nakayama-takeshi', // 中山武
        'nakayama-toshiyuki', // 中山俊之
        'nakazato-atsushi', // 中里篤史
        'nakazawa-hiroki', // 仲澤広基
        'nanamori-yoshiyasu', // 七森由康
        'nasu-shizuo', // 那須静雄
        'nishimoto-kazumi', // 西本和美
        'nishiyama-masami', // 西山正已
        'noguchi-katsuharu', // 野口勝治
        'noguchi-motozo', // 野口元三
        'nogusa-yoshiteru', // 野草義輝
        'ogawa-seiichi', // 小川清一
        'ogino-kazuo', // 萩野一雄
        'ogiwara-mitsuru', // 荻原満
        'ogoh-hiroshi', // 淡河弘
        'ohhashi-tomohisa', // 大橋智干
        'ohkita-toshihiro', // 大北敏博
        'ohno-kazuya', // 大野和哉
        'ohno-rin', // 大野倫
        'ohsuga-makoto', // 大須賀允
        'ohta-koji', // 太田幸司
        'ohtake-kenji', // 大竹憲治
        'ohya-katsumi', // 大屋克己
        'okamoto-koh', // 岡本光
        'okuma-nobuyuki', // 大熊伸行
        'ono-go', // 小野剛
        'ono-hitoshi', // 小野仁
        'orita-jyunya', // 織田淳哉
        'ozawa-kouichi', // 小沢浩一
        'saisyo-toshiro', // 才所俊郎
        'saitoh-masahiro', // 斎藤勝博
        'saitoh-seiji', // 斎藤誠二
        'sakaemura-tadahiro', // 栄村忠広
        'sakaguchi-masaki', // 坂口真規
        'sakai-jyunya', // 酒井純也
        'sakomaru-kousyo', // 迫丸金次郎
        'sano-motokuni', // 佐野元国
        'santa-masao', // 三田政夫
        'sasaki-akiyoshi', // 佐々木明義
        'sasaki-isao', // 佐々木勲
        'satoh-hiroshi99', // 佐藤宏志
        'satoh-hiroyuki', // 佐藤裕幸
        'satoh-masao', // 佐藤政夫
        'sawamura-eizi', // 沢村栄治
        'sekiguchi-masami', // 関口正巳
        'seo-yoshihiro', // 背尾伊洋
        'shibata-sakio', // 柴田崎雄
        'shimano-osamu', // 島野修
        'shimizu-yoshiaki', // 清水善秋
        'shiotsuki-katsuyoshi', // 塩月勝義
        'soejima-tokito', // 添島時人
        'sogawa-takatomi', // 十川孝富
        'sogawa-yuji', // 十川雄二
        'sugie-shigeo', // 杉江繁雄
        'sugiyama-shigeru', // 杉山茂
        'suzuki-kouki', // 鈴木弘規
        'suzuki-minoru', // 鈴木実
        'suzuki-nobuyoshi', // 鈴木伸良
        'suzuki-nozomu', // 鈴木望
        'suzukida-tomaru', // 鈴木田登満留
        'tajiri-shigetoshi', // 田尻茂敏
        'takahashi-eiji', // 高橋英二
        'takahashi-koh', // 髙橋洸
        'takahashi-masakatsu', // 高橋正勝
        'takami-masahiro', // 高見昌宏
        'takano-shinobu', // 高野忍
        'takaoka-eiji', // 高岡英司
        'takeda-kazuhiro', // 武田一浩
        'takeshita-koji', // 竹下浩二
        'tamai-nobuhiro', // 玉井信博
        'tamura-isao', // 田村勲
        'tamura-mikio', // 田村幹雄
        'tanaka-daijiro', // 田中大二郎
        'tani-hiroya', // 谷浩弥
        'taniguchi-kineji', // 谷口紀念治
        'taniguchi-kouichi', // 谷口功一
        'taniyama-takaaki', // 谷山高明
        'teramoto-tetsuji', // 寺本哲治
        'toda-kichizo', // 戸田吉蔵
        'togano-masafumi', // 栂野雅史
        'tohyama-takao', // 遠山隆男
        'tsuburaya-hidetoshi', // 円谷英俊
        'tsuchimoto-kyohei', // 土本恭平
        'tsutsui-osamu', // 筒井修
        'uchida-keiichi', // 内田圭一
        'uchizono-naoki', // 内薗直樹
        'ueno-takahisa', // 上野貴久
        'ueno-yuhei', // 上野裕平
        'uetsuji-osamu', // 上辻修
        'uno-masami', // 宇野雅美
        'usami-toshiharu', // 宇佐美敏晴
        'utsumi-isoo', // 内海五十雄
        'watabe-hiroshi', // 渡部弘
        'watanabe-kunio', // 渡部久二男
        'watanabe-masahito', // 渡辺政仁
        'yabe-yuichi', // 矢部祐一
        'yahata-hideo', // 八幡英男
        'yamada-kozo', // 山田幸造
        'yamada-shinsuke', // 山田真介
        'yamada-takeshi', // 山田武史
        'yamamoto-eiichiro', // 山本栄一郎
        'yamamoto-katsuya', // 山本勝哉
        'yamamoto-koji82', // 山本幸二
        'yamaoka-masaru', // 山岡勝
        'yamasaki-akihiro', // 山崎章弘
        'yamazaki-hiromi', // 山崎弘美
        'yashima-yoneo', // 八島米雄
        'yasuhara-masatoshi', // 安原政俊
        'yatsunami-akio', // 八浪彬雄
        'yokoyama-tadao', // 横山忠夫
        'yoshikawa-motohiro', // 吉川元浩
        'yoshimura-mareo', // 吉村典男
        'yoshizawa-hidekazu', // 吉沢勝
    );
}

add_filter( 'wp_robots', function( $robots ) {
    if ( ! is_page() ) {
        return $robots;
    }
    $slug = get_post_field( 'post_name', get_the_ID() );
    if ( $slug && in_array( $slug, yoshilover_data_noindex_slugs(), true ) ) {
        unset( $robots['index'] );
        $robots['noindex'] = true;
        $robots['follow']  = true; // リンクは辿らせる(内部リンク導線を維持)
    }
    return $robots;
}, 20 );
