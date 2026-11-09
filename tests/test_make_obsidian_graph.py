#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_obsidian_graph 的回归测试。

重点：生成的目录/统计页必须被排除在图外 —— 一个 `_index.md` 连向全部条目，
留在图里就会抢走布局中心，让分类枢纽看不出来（这是实际观察到的回归）。
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools' / 'make_obsidian_graph.py'


def _load_module():
    spec = importlib.util.spec_from_file_location('make_obsidian_graph', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_vault(root: Path, tags_by_paper):
    """建一个最小可运行的库：论文条目 + 空的 graph.json。"""
    papers = root / '1-Papers'
    for name, tags in tags_by_paper.items():
        entry = papers / name
        entry.mkdir(parents=True, exist_ok=True)
        lines = ['---', 'title: "%s"' % name, 'tags:']
        lines += ['  - "%s"' % t for t in tags]
        lines += ['---', '', '# %s' % name, '']
        (entry / 'index.md').write_text('\n'.join(lines), encoding='utf-8')
    obsidian = root / '.obsidian'
    obsidian.mkdir(parents=True, exist_ok=True)
    (obsidian / 'graph.json').write_text('{}', encoding='utf-8')
    return root


@pytest.fixture(scope='module')
def mod():
    return _load_module()


def test_search_excludes_generated_index_pages(mod):
    """四个生成页的排除规则都必须在 GRAPH_SEARCH 里，且保留原有重复区排除。"""
    for token in (
        '-path:1-Papers/_index.md',
        '-path:1-Papers/_stats.md',
        '-path:3-Taxonomy/_index.md',
        '-path:2-Concepts/_index.md',
    ):
        assert token in mod.GRAPH_SEARCH
    assert '-path:_duplicates/' in mod.GRAPH_SEARCH


def test_main_writes_search_and_filters_to_graph_json(tmp_path, mod):
    """真跑一次脚本：写出的 search 与过滤器要落到 graph.json。"""
    vault = _make_vault(tmp_path, {'p1': ['领域/光谱学', '状态/已总结']})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--vault', str(vault)],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout

    data = json.loads((vault / '.obsidian' / 'graph.json').read_text(encoding='utf-8'))
    for token in mod.INDEX_EXCLUDED:
        assert token in data['search']
    assert data['hideUnresolved'] is True
    assert data['showTags'] is False


def test_build_groups_colors_special_pages_and_domains(tmp_path, mod):
    """概念页/分类页各自有分组，领域标签按出现次数拿到配色。"""
    vault = _make_vault(
        tmp_path,
        {
            'p1': ['领域/光谱学'],
            'p2': ['领域/光谱学'],
            'p3': ['领域/光纤光学'],
        },
    )
    domains, groups = mod.build_groups(str(vault))
    queries = [g['query'] for g in groups]

    assert 'path:2-Concepts/' in queries
    assert 'path:3-Taxonomy/' in queries
    assert 'tag:#领域/光谱学' in queries
    assert 'tag:#领域/光纤光学' in queries
    # 出现次数多的领域排前面（先生效）
    assert queries.index('tag:#领域/光谱学') < queries.index('tag:#领域/光纤光学')
    assert domains['光谱学'] == 2


def test_idempotent_second_run_keeps_backup_single(tmp_path):
    """重复运行不应不断堆备份文件（脚本只保留最近 3 份，且无变化时跳过）。"""
    vault = _make_vault(tmp_path, {'p1': ['领域/光谱学']})
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), '--vault', str(vault)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout
    baks = list((vault / '.obsidian').glob('graph.json.bak-*'))
    assert len(baks) <= 1
