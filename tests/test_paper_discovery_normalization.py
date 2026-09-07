"""paper_discovery_normalization 纯函数单测（spec-015 Task15 步骤5 底层去重依赖）。

覆盖 normalize_doi / normalize_title 两个纯函数的边界行为，落实 spec-015
覆盖率要求。这些函数是 DOI / DBLP key / 规范化标题+作者+年份+会议 合并去重的
底层依赖，故需固定其契约：

- normalize_doi：剥离 https://doi.org / https://dx.doi.org / doi: 前缀，
  去除首尾空白与尾部引用句点，统一 casefold 小写；None/空串归零为 ""。
- normalize_title：casefold + NFKD 去重音 + 删除全部非 \\w 字符，
  把"标题+作者+年份+会议"压成可比较的身份串；None/空串归零为 ""。

本文件仅新增测试，不修改被测模块；若断言暴露实现 bug，将停在日志而非改实现。
"""

import pytest

from backend.app.services.paper_discovery_normalization import (
    normalize_doi,
    normalize_title,
)

# --- normalize_doi -----------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        # None / 空输入归零
        (None, ""),
        ("", ""),
        ("   ", ""),
        # 裸 DOI 原样（仅 casefold + 去首尾空白）
        ("10.1234/abcd", "10.1234/abcd"),
        ("  10.1/2  ", "10.1/2"),
        # 大小写归一
        ("10.1234/ABCD", "10.1234/abcd"),
        # https://doi.org 前缀
        ("https://doi.org/10.1234/abcd", "10.1234/abcd"),
        # https://dx.doi.org 前缀（dx. 也被剥离）
        ("https://dx.doi.org/10.1234/abcd", "10.1234/abcd"),
        # http://doi.org 前缀
        ("http://doi.org/10.1/2", "10.1/2"),
        # doi: 前缀
        ("doi:10.1234/abcd", "10.1234/abcd"),
        # doi: 后允许空白
        ("doi:  10.1234/abcd", "10.1234/abcd"),
        # 前缀大小写不敏感（casefold 后再匹配小写前缀）
        ("HTTPS://DOI.ORG/10.1/2", "10.1/2"),
        # 尾部引用句点被剥离
        ("10.1234/abcd.", "10.1234/abcd"),
        ("10.1234/abcd...", "10.1234/abcd"),
        ("10.1234/abcd. ", "10.1234/abcd"),
        (" 10.1/2.", "10.1/2"),
        # 前缀 + 尾部句点组合
        ("https://doi.org/10.1/2.", "10.1/2"),
        # 非句点尾标点（逗号）不受 rstrip(".") 影响，被忠实保留
        ("10.1234/abcd,", "10.1234/abcd,"),
        # 内部点不被动（仅尾部点被剥）
        ("10.1234/5.6", "10.1234/5.6"),
        # 数字型输入
        (1.2, "1.2"),
        # URL 编码保持不变（函数不做 unquote）
        ("10.1234/abc%20def", "10.1234/abc%20def"),
        # 无 scheme 的 doi.org 前缀不被剥离（regex 要求 https?:// 开头）
        ("doi.org/10.1/2", "doi.org/10.1/2"),
        # 仅前缀、内容为空
        ("https://doi.org/", ""),
        ("doi:", ""),
        ("doi:   ", ""),
    ],
    ids=[
        "none", "empty", "whitespace",
        "bare", "bared-with-surrounding-space", "uppercase",
        "https-doi-org", "https-dx-doi-org", "http-doi-org",
        "doi-prefix", "doi-prefix-spaces", "uppercase-url",
        "trailing-dot", "trailing-dots", "trailing-dot-space", "leading-space-trailing-dot",
        "url-and-dot", "trailing-comma-kept", "inner-dot-kept",
        "numeric", "url-encoded-kept", "bare-doi-org-not-stripped",
        "empty-url-doi", "empty-doi-prefix", "doi-prefix-spaces-only",
    ],
)
def test_normalize_doi(raw, expected):
    assert normalize_doi(raw) == expected


def test_normalize_doi_is_idempotent():
    """对已规范化结果再次规范化保持不变（去重键稳定性）。"""
    once = normalize_doi("https://doi.org/10.1234/abcd.")
    assert once == "10.1234/abcd"
    assert normalize_doi(once) == once


# --- normalize_title ---------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        # None / 空输入归零
        (None, ""),
        ("", ""),
        ("   ", ""),
        # 大小写归一 + 删除空白（标题串被压成无分隔身份串）
        ("Hello World", "helloworld"),
        ("FOO BAR", "foobar"),
        # 多空白 / 换行被删除
        ("a   b", "ab"),
        ("line1\nline2", "line1line2"),
        # 标点被删除
        ("A: B, C!", "abc"),
        ("(Title)", "title"),
         # 斜杠等符号被删除
         ("with-slash/path", "withslashpath"),
        # 数字与下划线属 \w，被保留
        ("Paper 2019", "paper2019"),
        ("a_b c_d", "a_bc_d"),
        # 重音 / Unicode 经 NFKD 去组合
        ("Café", "cafe"),
        ("naïve résumé", "naiveresume"),
        ("Zürich", "zurich"),
        # 组合字符（e + U+0301 组合重音）同样归一为 e
        ("cafe\u0301", "cafe"),
        # NFKD 兼容字符：全角 ASCII 归为半角
        ("ＡｂＣ", "abc"),
        # 中日韩属 \w，保留
        ("机器学习", "机器学习"),
        # 纯标点 → 空
        ("!!! ... ???", ""),
        ("---", ""),
        # 数字年份+会议 组合压成身份串
        ("Agent Security, CCS 2099", "agentsecurityccs2099"),
    ],
    ids=[
        "none", "empty", "whitespace",
        "casefold-collapse", "uppercase-collapse",
        "multiple-space", "newline",
        "punctuation", "parenthesis",
        "slash-path",
        "digits-kept", "underscore-kept",
        "precomposed-accent", "precomposed-accents", "precomposed-u-ligature",
        "combining-mark", "nfkd-fullwidth",
        "cjk-kept",
        "punct-only-empty", "dash-only-empty",
        "title-venue-year",
    ],
)
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


def test_normalize_title_combines_into_stable_identity():
    """同一会议/年份下，标题的大小写与空白差异归一后应碰撞为同一身份串。"""
    assert normalize_title("Agent  Security") == normalize_title("AGENT security")
    assert normalize_title("Agent Security, CCS 2099") == normalize_title(
        "agent-security ccs 2099"
    )


def test_normalize_doi_matches_across_decorations_for_dedup():
    """去重场景下，同一 DOI 的不同书写形式应归一到同一键。"""
    forms = [
        "10.1234/abcd",
        "https://doi.org/10.1234/abcd",
        "DOI:10.1234/ABCD.",
    ]
    normalized = {normalize_doi(f) for f in forms}
    assert normalized == {"10.1234/abcd"}
