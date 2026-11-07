# -*- coding: utf-8 -*-
"""make_references 规则解析 / 幂等 / 标记块保留的回归测试。

不读真实论文库，不联网；用合成 full.md。
"""
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / 'tools'
sys.path.insert(0, str(TOOLS))

import make_references  # noqa: E402
import apply_summary  # noqa: E402


PREFIX_TEXT = '''# Demo Paper

Some body text.

## References

\\*This research was supported by a grant.

1. Alpha, A., First paper. J. Test 1, 1 (2000). https://doi.org/10.1234/alpha.
2. Beta, B., Second paper. J. Test 2, 2 (2001). arXiv:2101.01234
3. Gamma, C., Third paper. J. Test 3, 3 (2002).
'''

BLOCK_TEXT = '''# Demo Paper

## 参考文献

[1] Culshaw, B., Optical Fiber Sensors, 1989.

[2] Medlock, R. S., Review of modulating techniques, 1986.

[3] Lawson, C. M., Fiber-optic diaphragm pressure transducer, 1983.
'''

NO_REF_TEXT = '# Demo Paper\n\n## Introduction\n\nNo references here.\n'


def test_parse_prefixed_and_footnote():
    parsed = make_references.parse_references(PREFIX_TEXT)
    assert parsed['ok'] is True
    assert parsed['count'] == 3
    assert parsed['entries'][0]['text'].startswith('Alpha')
    assert len(parsed['notes']) == 1
    assert parsed['notes'][0].startswith('\\*This research')


def test_parse_block_fallback():
    parsed = make_references.parse_references(BLOCK_TEXT)
    assert parsed['ok'] is True
    assert parsed['count'] == 3
    assert parsed['entries'][0]['text'].startswith('Culshaw')


def test_parse_no_heading():
    parsed = make_references.parse_references(NO_REF_TEXT)
    assert parsed['ok'] is False
    assert parsed['reason'] == 'no-heading'


def test_parse_loose_heading_variants():
    for heading in ('## 7. REFERENCES', '## References and links',
                    '## References and Notes:', '## 参考文献：'):
        text = heading + '\n\n' + '\n\n'.join(
            ['A, A., One, 2000.', 'B, B., Two, 2001.', 'C, C., Three, 2002.'])
        parsed = make_references.parse_references(text)
        assert parsed['ok'] is True, heading
        assert parsed['count'] == 3, heading


def test_block_fallback_keeps_notes_separate():
    text = ('## REFERENCES\n\n\\*Funding note.\n\n'
            'A, A., One, 2000.\n\nB, B., Two, 2001.\n\nC, C., Three, 2002.\n')
    parsed = make_references.parse_references(text)
    assert parsed['ok'] is True
    assert parsed['count'] == 3
    assert len(parsed['notes']) == 1
    assert all('Funding note' not in e['text'] for e in parsed['entries'])


def test_links_appended_without_duplicate():
    text = 'A. Alpha, J. Test 1, 1 (2000). 10.1234/alpha.'
    linked = make_references._append_links(text)
    assert '[DOI](https://doi.org/10.1234/alpha)' in linked
    assert linked.count('10.1234/alpha') == 2

    already = 'A. Alpha. https://doi.org/10.1234/alpha'
    assert make_references._append_links(already) == already


def _make_entry(tmp_path, full_text, title='Test Paper'):
    entry = tmp_path / '1-Papers' / 'Test Paper'
    entry.mkdir(parents=True)
    (entry / 'full.md').write_text(full_text, encoding='utf-8')
    (entry / 'index.md').write_text(
        '---\ntitle: "%s"\nyear: "2020"\n---\n\n# %s\n\n正文\n' % (title, title),
        encoding='utf-8')
    return entry


def test_build_for_entry_and_idempotent(tmp_path):
    entry = _make_entry(tmp_path, PREFIX_TEXT)
    res = make_references.build_for_entry(str(entry), 'Test Paper')
    assert res['ok'] and res['skipped'] is False
    refs = (entry / 'references.md').read_text(encoding='utf-8')
    assert 'count: 3' in refs
    assert 'source: "full.md"' in refs
    assert 'source_hash: "' in refs
    assert '# 📚 参考文献' in refs
    assert '1. Alpha' in refs
    assert '## 注释' in refs
    index = (entry / 'index.md').read_text(encoding='utf-8')
    assert '<!-- paperdepot:refs:start -->' in index
    assert '[[references|📚 参考文献（3 条）]]' in index
    assert '正文' in index  # 不碰 index 其他内容

    refs_mtime = (entry / 'references.md').stat().st_mtime_ns
    index_mtime = (entry / 'index.md').stat().st_mtime_ns
    time.sleep(0.02)
    res2 = make_references.build_for_entry(str(entry), 'Test Paper')
    assert res2['ok'] and res2['skipped'] is True
    assert (entry / 'references.md').stat().st_mtime_ns == refs_mtime
    assert (entry / 'index.md').stat().st_mtime_ns == index_mtime


def test_missing_index_does_not_write(tmp_path):
    entry = tmp_path / 'entry'
    entry.mkdir()
    (entry / 'full.md').write_text(PREFIX_TEXT, encoding='utf-8')
    res = make_references.build_for_entry(str(entry), 'X')
    assert res['ok'] is False
    assert res['reason'] == 'index.md missing'
    assert not (entry / 'references.md').exists()


def test_apply_summary_keeps_all_marker_blocks(tmp_path):
    vault = tmp_path / 'vault'
    entry = vault / '1-Papers' / 'Test Paper'
    entry.mkdir(parents=True)
    (entry / 'summary.md').write_text(
        '---\naliases: []\nkeywords: []\ncitekey: "x2020test"\n---\n\n'
        '# 📖 论文摘要\n\n## 一句话总结\n\n测试摘要。\n', encoding='utf-8')
    (entry / 'tags.md').write_text('# Test Paper - 标签\n\n## 研究领域\n- 测试\n', encoding='utf-8')
    old = (
        '---\ntitle: "Test Paper"\nyear: "2020"\n---\n\n# Test Paper\n\n正文\n\n'
        '<!-- paperdepot:nav:start -->\n[[nav|导航]]\n<!-- paperdepot:nav:end -->\n\n'
        '<!-- paperdepot:refs:start -->\n[[references|📚 参考文献（3 条）]]\n'
        '<!-- paperdepot:refs:end -->\n'
    )
    (entry / 'index.md').write_text(old, encoding='utf-8')

    assert apply_summary.apply_one(str(vault), 'Test Paper') is True
    new = (entry / 'index.md').read_text(encoding='utf-8')
    assert new.count('<!-- paperdepot:nav:start -->') == 1
    assert new.count('<!-- paperdepot:refs:start -->') == 1
    assert '[[nav|导航]]' in new
    assert '[[references|📚 参考文献（3 条）]]' in new
    # refs 在 nav 之后仍存在，且没有重复
    assert new.index('paperdepot:refs:start') > new.index('paperdepot:nav:start')


# ── L1 在线补全（全部离线测试，不联网）─────────────────────────────────

NO_REFS_TEXT = '# Demo Paper\n\n## Introduction\n\n没有参考文献段。\n'


def _make_entry_with_id(tmp_path, doi='10.1234/demo', arxiv='', full_text=NO_REFS_TEXT):
    entry = tmp_path / '1-Papers' / 'Online Paper'
    entry.mkdir(parents=True)
    (entry / 'full.md').write_text(full_text, encoding='utf-8')
    fm = ['---', 'title: "Online Paper"', 'year: "2020"']
    if doi:
        fm.append('doi: "https://doi.org/%s"' % doi)
    if arxiv:
        fm.append('arxiv: "arXiv:%s"' % arxiv)
    fm.append('---')
    (entry / 'index.md').write_text('\n'.join(fm) + '\n\n# Online Paper\n\n正文\n', encoding='utf-8')
    return entry


def _online_ok(source='s2', n=4):
    entries = [{'text': 'Author%d. Paper %d. J. Test, 20%02d. [DOI](https://doi.org/10.1234/x%d)'
                % (i, i, i, i), 'num': i} for i in range(1, n + 1)]
    return {'ok': True, 'source': source, 'entries': entries,
            'count': len(entries), 'reason': '', 'transient': False}


def test_read_ids_parses_frontmatter():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / 'index.md'
        p.write_text(
            '---\ntitle: "X"\ndoi: "https://doi.org/10.1088/0004-6256/145/1/10"\n'
            'arxiv: "arXiv:2401.01234v2"\n---\n\n# X\n', encoding='utf-8')
        ids = make_references.read_ids(str(p))
        assert ids['doi'] == '10.1088/0004-6256/145/1/10'
        assert ids['arxiv'] == '2401.01234v2'


def test_entries_from_s2_composes_and_filters():
    payload = {'data': [
        {'citedPaper': {'title': 'A Good Title', 'year': 2020, 'venue': 'ApJ',
                        'authors': [{'name': 'A. One'}, {'name': 'B. Two'}],
                        'externalIds': {'DOI': '10.1234/abc'}}},
        {'citedPaper': {'title': 'x' * 400, 'year': 2021}},           # 过长，丢弃
        {'citedPaper': {'title': '', 'year': 2021}},                   # 空标题，丢弃
        {'citedPaper': {'title': 'No Ids', 'year': 2019, 'venue': ' , ',
                        'externalIds': {}}},
    ]}
    entries = make_references._entries_from_s2(payload)
    assert len(entries) == 2
    assert entries[0]['text'].startswith('A. One, B. Two. A Good Title. ApJ, 2020.')
    assert '[DOI](https://doi.org/10.1234/abc)' in entries[0]['text']
    # venue 是 " , " 时要被清掉，不能留个空逗号
    assert 'No Ids. 2019.' in entries[1]['text']
    assert ', ,' not in entries[1]['text']


def test_entries_from_crossref_structured_and_tidy():
    work = {'message': {'reference': [
        {'unstructured': 'D.Fried Conf. on Optical Propagation Boulder United States1965'},
        {'author': 'Abazajian', 'journal-title': 'AJ', 'volume': '128',
         'first-page': '502', 'year': '2004', 'DOI': '10.1086/421365'},
        {'year': '2004'},  # 信息太少，丢弃
    ]}}
    entries = make_references._entries_from_crossref(work)
    assert len(entries) == 2
    # 粘连被补空格
    assert 'D. Fried' in entries[0]['text']
    assert 'States 1965' in entries[0]['text']
    # 没有 unstructured 时按 ADS 风格拼
    assert entries[1]['text'].startswith('Abazajian. AJ, 128, 502 (2004).')
    assert '[DOI](https://doi.org/10.1086/421365)' in entries[1]['text']


def test_online_fallback_writes_source_and_marker(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path)
    monkeypatch.setattr(make_references, 'fetch_online',
                        lambda doi, arxiv, budget=None: _online_ok('s2'))
    res = make_references.build_for_entry(str(entry), 'Online Paper')
    assert res['ok'] is True and res['skipped'] is False
    assert res['source'] == 's2'
    refs = (entry / 'references.md').read_text(encoding='utf-8')
    assert 'source: "s2"' in refs
    assert 'Semantic Scholar' in refs
    index = (entry / 'index.md').read_text(encoding='utf-8')
    assert '[[references|📚 参考文献（4 条）]]' in index


def test_online_result_is_idempotent_without_network(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path)
    calls = []

    def fake(doi, arxiv, budget=None):
        calls.append(doi)
        return _online_ok('crossref')

    monkeypatch.setattr(make_references, 'fetch_online', fake)
    assert make_references.build_for_entry(str(entry), 'P')['ok'] is True
    mtime = (entry / 'references.md').stat().st_mtime_ns

    # 第二次：在线 hash 只由 ids 决定，应当直接 SKIP，不再联网
    res2 = make_references.build_for_entry(str(entry), 'P')
    assert res2['skipped'] is True
    assert res2['source'] == 'crossref'
    assert len(calls) == 1
    assert (entry / 'references.md').stat().st_mtime_ns == mtime


def test_offline_flag_disables_online(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path)
    monkeypatch.setattr(make_references, 'fetch_online',
                        lambda doi, arxiv, budget=None: (_ for _ in ()).throw(AssertionError('不该联网')))
    res = make_references.build_for_entry(str(entry), 'P', online=False)
    assert res['ok'] is False
    assert res['reason'] == 'no-heading'
    assert not (entry / 'references.md').exists()


def test_env_can_disable_online(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path)
    monkeypatch.setenv('PAPERDEPOT_NO_ONLINE_REFS', '1')
    monkeypatch.setattr(make_references, 'fetch_online',
                        lambda doi, arxiv, budget=None: (_ for _ in ()).throw(AssertionError('不该联网')))
    res = make_references.build_for_entry(str(entry), 'P')
    assert res['ok'] is False


def test_no_id_skips_online(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path, doi='', arxiv='')
    monkeypatch.setattr(make_references, 'fetch_online',
                        lambda doi, arxiv, budget=None: (_ for _ in ()).throw(AssertionError('不该联网')))
    res = make_references.build_for_entry(str(entry), 'P')
    assert res['ok'] is False


def test_negative_cache_prevents_repeat(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path)
    calls = []

    def fake(doi, arxiv, budget=None):
        calls.append(1)
        return {'ok': False, 'source': '', 'entries': [], 'count': 0,
                'reason': 'no-online-refs', 'transient': False}

    monkeypatch.setattr(make_references, 'fetch_online', fake)
    assert make_references.build_for_entry(str(entry), 'P')['ok'] is False
    assert make_references.build_for_entry(str(entry), 'P')['ok'] is False
    assert len(calls) == 1, '确定性「没有参考文献」应命中负缓存'
    assert (entry / '.refs-online.json').exists()


def test_transient_failure_is_not_cached(tmp_path, monkeypatch):
    entry = _make_entry_with_id(tmp_path)
    calls = []

    def fake(doi, arxiv, budget=None):
        calls.append(1)
        return {'ok': False, 'source': '', 'entries': [], 'count': 0,
                'reason': 'rate-limited', 'transient': True}

    monkeypatch.setattr(make_references, 'fetch_online', fake)
    assert make_references.build_for_entry(str(entry), 'P')['ok'] is False
    assert make_references.build_for_entry(str(entry), 'P')['ok'] is False
    assert len(calls) == 2, '限流/超时不应写负缓存'
    assert not (entry / '.refs-online.json').exists()


def test_offline_source_unchanged_still_not_overwritten(tmp_path, monkeypatch):
    """离线已有 references.md 时，不应因为在线可用就被替换。"""
    entry = _make_entry(tmp_path, PREFIX_TEXT)
    assert make_references.build_for_entry(str(entry), 'Test Paper')['source'] == 'full.md'
    monkeypatch.setattr(make_references, 'fetch_online',
                        lambda doi, arxiv, budget=None: _online_ok('s2'))
    res = make_references.build_for_entry(str(entry), 'Test Paper')
    assert res['skipped'] is True
    assert res['source'] == 'full.md'
