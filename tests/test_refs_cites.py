# -*- coding: utf-8 -*-
"""库内引用（引文 → 库内论文 wikilink）的回归测试。

不读真实论文库、不联网；用合成库验证匹配精度边界与标记块幂等。
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / 'tools'
sys.path.insert(0, str(TOOLS))

import make_references  # noqa: E402


ALPHA = 'Paper Alpha Long Title for Testing'
BETA = 'Paper Beta Long Title About Fibers'
GAMMA = 'Short'


def _write_entry(vault, name, title, refs_text, aliases=None):
    entry = Path(vault) / '1-Papers' / name
    entry.mkdir(parents=True, exist_ok=True)
    fm = ['---', 'title: %r' % title]
    if aliases:
        fm.append('aliases:')
        fm += ['  - %r' % a for a in aliases]
    fm += ['---', '', '# %s' % title, '']
    (entry / 'index.md').write_text('\n'.join(fm), encoding='utf-8')
    (entry / 'full.md').write_text(
        '# %s\n\nSome body.\n\n## References\n\n%s\n' % (title, refs_text),
        encoding='utf-8',
    )
    return entry


@pytest.fixture()
def vault(tmp_path):
    """三个条目：Alpha 引用 Beta，Beta 引用 Alpha，Gamma 引用无关文献。

    parse_references 要求 ≥3 条引文才算有效参考文献段，所以每条都凑够 3 条。
    """
    filler = ('2. Other, O., Some unrelated work on calibration. J. Test 4, 4 (2004).\n'
              '3. Third, T., Yet another unrelated instrument paper. J. Test 5, 5 (2005).')
    _write_entry(tmp_path, ALPHA, ALPHA,
                 '1. Beta, B., %s. J. Test 2, 2 (2001).\n%s' % (BETA, filler))
    _write_entry(tmp_path, BETA, BETA,
                 '1. Alpha, A., %s. J. Test 1, 1 (2000).\n%s' % (ALPHA, filler))
    _write_entry(tmp_path, GAMMA, GAMMA,
                 '1. Other, O., Some unrelated work on calibration. J. Test 4, 4 (2004).\n'
                 '2. Third, T., Yet another unrelated instrument paper. J. Test 5, 5 (2005).\n'
                 '3. Fourth, F., A completely different study of detectors. J. Test 6, 6 (2006).')
    return tmp_path


def test_norm_title_strips_math_and_punctuation():
    assert make_references._norm_title('A $x^2$ Title: With-Punctuation!') == 'a title with punctuation'
    assert make_references._norm_title('  Multi   Space\nBreaks ') == 'multi space breaks'
    assert make_references._norm_title('') == ''


def test_match_picks_longest_title_only(vault):
    """一条引文只认一个目标：命中最长的那个标题。"""
    entries = [
        {'text': 'Beta, B., %s. J. Test 2, 2 (2001).' % BETA},
        {'text': '1. %s. J. Test 1, 1 (2000).' % ALPHA},
    ]
    hits = make_references.match_in_vault(entries, str(vault), self_dir=GAMMA)
    assert [h[0] for h in hits] == [BETA, ALPHA]


def test_self_reference_not_matched(vault):
    """论文不引用自己。"""
    entries = [{'text': '%s. J. Test 1, 1 (2000).' % ALPHA}]
    assert make_references.match_in_vault(entries, str(vault), self_dir=ALPHA) == []


def test_short_title_is_ignored(vault):
    """归一化后不足 18 字符的标题不参与匹配，避免乱命中。"""
    entries = [{'text': 'Gamma, G., %s. J. Test 3, 3 (2003).' % GAMMA}]
    assert make_references.match_in_vault(entries, str(vault), self_dir=ALPHA) == []


def test_build_writes_cites_block_then_is_idempotent(vault):
    entry = Path(vault) / '1-Papers' / ALPHA
    res = make_references.build_for_entry(str(entry), ALPHA, online=False, vault=str(vault))
    assert res['ok'] is True
    assert res['cites'] == 1

    text = (entry / 'index.md').read_text(encoding='utf-8')
    assert '<!-- paperdepot:cites:start -->' in text
    assert '## 🔗 库内引用（1 篇）' in text
    assert '[[1-Papers/%s/index|%s]]' % (BETA, BETA) in text
    # refs 入口仍在，且排在 cites 之前
    assert text.index('paperdepot:refs:start') < text.index('paperdepot:cites:start')

    # 第二次：内容没变 → SKIP，不重写
    again = make_references.build_for_entry(str(entry), ALPHA, online=False, vault=str(vault))
    assert again['ok'] is True
    assert again.get('skipped') is True


def test_no_cites_flag_suppresses_block(vault):
    entry = Path(vault) / '1-Papers' / ALPHA
    make_references.build_for_entry(str(entry), ALPHA, online=False, vault=str(vault))
    assert 'paperdepot:cites:start' in (entry / 'index.md').read_text(encoding='utf-8')

    make_references.build_for_entry(str(entry), ALPHA, online=False, vault=str(vault),
                                    cites=False, force=True)
    assert 'paperdepot:cites:start' not in (entry / 'index.md').read_text(encoding='utf-8')


def test_apply_summary_preserves_cites_block(vault):
    """apply_summary 重建 index.md 时必须保留 cites 标记块（否则每次重写都会丢边）。"""
    import apply_summary

    entry = Path(vault) / '1-Papers' / ALPHA
    make_references.build_for_entry(str(entry), ALPHA, online=False, vault=str(vault))
    before = (entry / 'index.md').read_text(encoding='utf-8')
    block = make_references.CITES_MARKER_RE.search(before).group(0)

    # apply_summary 的保留逻辑：MARKER_BLOCK_RE 必须能识别 cites
    assert apply_summary.MARKER_BLOCK_RE.search(before) is not None
    matched = [m.group(0) for m in apply_summary.MARKER_BLOCK_RE.finditer(before)]
    assert block in matched


def test_generic_alias_is_not_used_for_matching(tmp_path):
    """aliases 常是宽泛词组（"blind deconvolution"），不能拿来当引文身份。

    真实回归：曾用 aliases 匹配，导致一条 "Blind deconvolution methods: A review"
    的引文同时命中库里多篇带该别名的论文。
    """
    entry = tmp_path / '1-Papers' / 'Blind Deconvolution Survey Paper'
    entry.mkdir(parents=True)
    (entry / 'index.md').write_text(
        '---\ntitle: "Blind Deconvolution Survey Paper"\naliases:\n'
        '  - "blind deconvolution"\n---\n\n# Blind Deconvolution Survey Paper\n',
        encoding='utf-8',
    )
    # 另一篇只在句中出现 "blind deconvolution" 关键词，标题并不等长
    other = tmp_path / '1-Papers' / 'Something Else Entirely'
    other.mkdir(parents=True)
    (other / 'index.md').write_text('---\ntitle: "Something Else Entirely"\n---\n\n# x\n', encoding='utf-8')

    entries = [{'text': '11. Krishnan, D., Blind deconvolution using a normalized sparsity measure. CVPR (2011).'}]
    assert make_references.match_in_vault(entries, str(tmp_path), self_dir='Something Else Entirely') == []


def test_quoted_short_title_matches_exactly(tmp_path):
    """短标题（不足 CITES_MIN_TITLE）只有在引文里被引号完整括起时才算命中。"""
    short_title = 'Deep Image Prior'
    entry = tmp_path / '1-Papers' / short_title
    entry.mkdir(parents=True)
    (entry / 'index.md').write_text(
        '---\ntitle: "%s"\n---\n\n# %s\n' % (short_title, short_title), encoding='utf-8')
    other = tmp_path / '1-Papers' / 'Some Citing Paper'
    other.mkdir(parents=True)
    (other / 'index.md').write_text('---\ntitle: "Some Citing Paper"\n---\n\n# x\n', encoding='utf-8')

    quoted = [{'text': '3. Ulyanov, D., “Deep Image Prior,” CVPR, 2018.'}]
    assert [h[0] for h in make_references.match_in_vault(
        quoted, str(tmp_path), self_dir='Some Citing Paper')] == [short_title]

    # 同样字样没有被引号括起 → 不算命中（避免 "deep image prior" 这种词串乱吸）
    bare = [{'text': '3. Ulyanov, D., Deep Image Prior CVPR 2018.'}]
    assert make_references.match_in_vault(
        bare, str(tmp_path), self_dir='Some Citing Paper') == []
