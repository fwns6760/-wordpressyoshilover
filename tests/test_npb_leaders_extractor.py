"""source_npb_leaders_extractor のパース検証(network 不要・固定 HTML)。"""

from src import source_npb_leaders_extractor as nle

_BAT_HTML = """
<table>
<tr><th>順位</th><th>選手</th><th>打率</th><th>試合</th><th>本塁打</th></tr>
<tr><td>1</td><td>佐藤　輝明(神)</td><td>.359</td><td>64</td><td>15</td></tr>
<tr><td>2</td><td>ダルベック(巨)</td><td>.249</td><td>61</td><td>11</td></tr>
</table>
<table><tr><td>無関係</td></tr></table>
"""


def test_parse_leaders_table_headers_and_rows():
    parsed = nle.parse_leaders_table(_BAT_HTML)
    assert parsed is not None
    headers, rows = parsed
    assert headers == ["順位", "選手", "打率", "試合", "本塁打"]
    assert rows[0] == ["1", "佐藤 輝明(神)", ".359", "64", "15"]  # 全角空白→半角
    assert rows[1][1] == "ダルベック(巨)"


def test_parse_leaders_table_respects_max_rows():
    parsed = nle.parse_leaders_table(_BAT_HTML, max_rows=1)
    assert parsed and len(parsed[1]) == 1


def test_parse_leaders_table_requires_rank_header():
    # 1列目が 順位 でないテーブルは採用しない
    html = "<table><tr><th>球団</th><th>打率</th></tr><tr><td>巨人</td><td>.228</td></tr></table>"
    assert nle.parse_leaders_table(html) is None
