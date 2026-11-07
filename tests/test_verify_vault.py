# -*- coding: utf-8 -*-
"""verify_vault 的只读检查 / 忽略列表 / 重复隔离回归测试。

不读真实论文库，不联网；全部用合成 vault。
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / 'tools'
sys.path.insert(0, str(TOOLS))

import verify_vault  # noqa: E402


FULL_MD = '# T\n\n![](images/fig01.jpg)\n\n## References\n\n1. A one.\n2. B two.\n3. C three.\n'


def _entry(vault, name, pdf=b'%PDF-1.4 test', summarized=False, needs_meta=False,
           doi='', images=True):
    d = Path(vault) / '1-Papers' / name
    (d / 'images').mkdir(parents=True, exist_ok=True)
    (d / 'full.md').write_text(FULL_MD, encoding='utf-8')
    (d / 'paper.pdf').write_bytes(pdf)
    if images:
        (d / 'images' / 'fig01.jpg').write_bytes(b'jpg')
    fm = ['---', 'title: "T"', 'source: "paper"']
    if summarized:
        fm.append('summarized: true')
    if needs_meta:
        fm.append('status: "needs_metadata"')
    if doi:
        fm.append('doi: "%s"' % doi)
    fm.append('---')
    (d / 'index.md').write_text('\n'.join(fm) + '\n\n# T\n', encoding='utf-8')
    (d / '.entry.json').write_text(json.dumps({'fingerprint': name}), encoding='utf-8')
    return d


def _scan(vault, state=None):
    """跑一遍 verify_one + 忽略过滤，返回 (results, summary 数据源)。"""
    papers = Path(vault) / '1-Papers'
    dirs = [str(p) for p in sorted(papers.iterdir()) if p.is_dir() and not p.name.startswith('_')]
    results = [verify_vault.verify_one(d) for d in dirs]
    st = verify_vault.load_state(state) if state else {'ignored': {}}
    verify_vault.apply_ignores(results, st)
    return results


def test_clean_entry_has_no_problem(tmp_path):
    _entry(tmp_path, 'Clean')
    r = _scan(tmp_path)[0]
    assert r['issues'] == []
    assert r['warn'] == []
    assert r['images'] == 1
    assert r['broken'] == 0
    assert r['refs_parse_ok'] is True


def test_missing_image_is_issue(tmp_path):
    _entry(tmp_path, 'Broken', images=False)
    r = _scan(tmp_path)[0]
    assert any('图引用不存在' in i for i in r['issues'])


def test_missing_required_files_is_issue(tmp_path):
    d = _entry(tmp_path, 'NoPdf')
    (d / 'paper.pdf').unlink()
    r = _scan(tmp_path)[0]
    assert any('缺 paper.pdf' in i for i in r['issues'])


def test_needs_metadata_is_warning(tmp_path):
    _entry(tmp_path, 'Meta', needs_meta=True)
    r = _scan(tmp_path)[0]
    assert '待补元数据' in r['warn']


def test_ignore_hides_warning_and_persists(tmp_path):
    _entry(tmp_path, 'Meta', needs_meta=True)
    state_file = str(tmp_path / 'state.json')
    state = {'ignored': {'Meta': {'warn': ['待补元数据'], 'at': '2026-01-01T00:00:00'}}}
    verify_vault.save_state(state_file, state)

    r = _scan(tmp_path, state_file)[0]
    assert r['warn'] == []
    assert r['ignored_warn'] == ['待补元数据']


def test_ignore_never_hides_issues(tmp_path):
    _entry(tmp_path, 'Broken', images=False, needs_meta=True)
    state_file = str(tmp_path / 'state.json')
    verify_vault.save_state(state_file, {
        'ignored': {'Broken': {'warn': ['待补元数据', '1 张图引用不存在']}}})
    r = _scan(tmp_path, state_file)[0]
    assert r['warn'] == []
    # issues 不可被忽略
    assert any('图引用不存在' in i for i in r['issues'])


def test_load_state_tolerates_garbage(tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text('not json', encoding='utf-8')
    assert verify_vault.load_state(str(p))['ignored'] == {}


def test_plan_fixes_separates_identical_and_different_pdfs(tmp_path):
    _entry(tmp_path, 'A', pdf=b'%PDF-same', doi='10.1/x')
    _entry(tmp_path, 'B', pdf=b'%PDF-same', doi='10.1/x')
    _entry(tmp_path, 'C', pdf=b'%PDF-one', doi='10.9/y')
    _entry(tmp_path, 'D', pdf=b'%PDF-two', doi='10.9/y')

    papers = Path(tmp_path) / '1-Papers'
    dirs = [str(p) for p in sorted(papers.iterdir())]
    groups = verify_vault.collect_duplicates(dirs)
    auto, manual = verify_vault.plan_fixes(groups)

    assert len(auto) == 1
    assert auto[0]['key'] == '10.1/x'
    assert len(auto[0]['remove']) == 1
    assert len(manual) == 1
    assert manual[0]['key'] == '10.9/y'


def test_plan_fixes_prefers_summarized_entry(tmp_path):
    _entry(tmp_path, 'Old', pdf=b'%PDF-same', doi='10.1/x')
    _entry(tmp_path, 'New', pdf=b'%PDF-same', doi='10.1/x', summarized=True)
    papers = Path(tmp_path) / '1-Papers'
    dirs = [str(p) for p in sorted(papers.iterdir())]
    auto, _ = verify_vault.plan_fixes(verify_vault.collect_duplicates(dirs))
    assert Path(auto[0]['keep']).name == 'New'
    assert [Path(x).name for x in auto[0]['remove']] == ['Old']


def test_apply_fixes_moves_to_quarantine(tmp_path):
    _entry(tmp_path, 'A', pdf=b'%PDF-same', doi='10.1/x')
    _entry(tmp_path, 'B', pdf=b'%PDF-same', doi='10.1/x')
    papers = Path(tmp_path) / '1-Papers'
    dirs = [str(p) for p in sorted(papers.iterdir())]
    auto, _ = verify_vault.plan_fixes(verify_vault.collect_duplicates(dirs))

    dest_root, moved = verify_vault.apply_fixes(str(tmp_path), auto)
    assert len(moved) == 1
    assert Path(dest_root).is_dir()
    assert (Path(dest_root) / 'B').is_dir()
    assert not (Path(tmp_path) / '1-Papers' / 'B').exists()
    assert (Path(tmp_path) / '1-Papers' / 'A').is_dir()
    # 隔离区在 0-Inbox 下，可恢复
    assert '.paperdepot-dupes' in dest_root


def test_state_roundtrip(tmp_path):
    state_file = str(tmp_path / 'sub' / 'verify.json')
    verify_vault.save_state(state_file, {'ignored': {'X': {'warn': ['w']}}})
    assert verify_vault.load_state(state_file)['ignored']['X']['warn'] == ['w']