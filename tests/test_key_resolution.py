# -*- coding: utf-8 -*-
"""MinerU key 路径解析回归测试（离线，不碰真实 key / 不访问 MinerU）。

覆盖两种布局：
  · 开发态：<仓库>/tools/           → 配置在 <仓库>/config/
  · 安装态：<插件包>/pipeline/tools/ → 配置在 ~/.dsh/paperdepot/config/

安装态曾出现「面板保存成功、Python 说没配置」：宿主写用户目录，Python 却去
插件包内找。这里把两边约定固化成测试，防止再分叉。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / 'tools'

# 运行时拼接，避免被 tests/check-paths.mjs 当成真实 key 扫描
FAKE_FILE_KEY = 'sk-' + 'file' + '0123456789ab'
FAKE_ENV_KEY = 'sk-' + 'env' + '0123456789ab'
SCRUB = ('MINERU_API_KEY', 'PAPERDEPOT_HOME', 'PAPERDEPOT_CONFIG_DIR', 'PAPERDEPOT_VAULT')


def _copy_tools(dst: Path) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for p in TOOLS.glob('*.py'):
        shutil.copy2(p, dst / p.name)
    return dst


def _installed_tools(tmp: Path) -> Path:
    """模拟 npm / 市场安装：<pkg>/pipeline/tools，包根没有 tools/ 与 scripts/。"""
    pkg = tmp / 'pkg'
    tools = _copy_tools(pkg / 'pipeline' / 'tools')
    assert not (pkg / 'tools').exists()
    return tools


def _write_key(config_dir: Path, key: str) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    p = config_dir / 'secrets.local.json'
    p.write_text(json.dumps({'mineru_api_key': key}), encoding='utf-8')
    return p


def _base_env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}
    env['HOME'] = str(home)
    env['USERPROFILE'] = str(home)  # Windows 上 expanduser('~') 读这个
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def _probe(tools: Path, env: dict) -> dict:
    script = (
        'import json, os, sys\n'
        'sys.path.insert(0, os.getcwd())\n'
        'import _paths, mineru_parse\n'
        'print(json.dumps({\n'
        '    "key": mineru_parse.API_KEY,\n'
        '    "source": mineru_parse.KEY_SOURCE,\n'
        '    "config_dir": _paths.config_dir(),\n'
        '    "home": _paths.home_dir(),\n'
        '    "secrets": _paths.secrets_path(),\n'
        '}))\n'
    )
    r = subprocess.run(
        [sys.executable, '-c', script],
        cwd=str(tools),
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _run_selftest_key(tools: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tools / 'mineru_parse.py'), '--selftest-key'],
        cwd=str(tools),
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )


def test_repo_layout_reads_repo_config(tmp_path):
    repo = tmp_path / 'repo'
    tools = _copy_tools(repo / 'tools')
    _write_key(repo / 'config', FAKE_FILE_KEY)

    got = _probe(tools, _base_env(tmp_path / 'home'))

    assert got['key'] == FAKE_FILE_KEY
    assert Path(got['config_dir']) == repo / 'config'
    assert Path(got['home']) == repo


def test_installed_layout_reads_user_config(tmp_path):
    tools = _installed_tools(tmp_path)
    home = tmp_path / 'home'
    cfg = home / '.dsh' / 'paperdepot' / 'config'
    _write_key(cfg, FAKE_FILE_KEY)

    got = _probe(tools, _base_env(home))

    assert got['key'] == FAKE_FILE_KEY
    assert Path(got['config_dir']) == cfg
    assert Path(got['home']) == home / '.dsh' / 'paperdepot'
    assert Path(got['secrets']) == cfg / 'secrets.local.json'


def test_env_key_wins_over_file(tmp_path):
    tools = _installed_tools(tmp_path)
    home = tmp_path / 'home'
    _write_key(home / '.dsh' / 'paperdepot' / 'config', FAKE_FILE_KEY)
    env = _base_env(home)
    env['MINERU_API_KEY'] = FAKE_ENV_KEY

    got = _probe(tools, env)

    assert got['key'] == FAKE_ENV_KEY
    assert got['source'] == 'env:MINERU_API_KEY'


def test_host_style_config_dir_env(tmp_path):
    """宿主 lib/impl.js 的 buildChildEnv 会传 PAPERDEPOT_CONFIG_DIR。"""
    tools = _installed_tools(tmp_path)
    home = tmp_path / 'home'
    cfg = tmp_path / 'custom-config'
    _write_key(cfg, FAKE_FILE_KEY)
    env = _base_env(home)
    env['PAPERDEPOT_CONFIG_DIR'] = str(cfg)

    got = _probe(tools, env)

    assert got['key'] == FAKE_FILE_KEY
    assert Path(got['config_dir']) == cfg


def test_paperdepot_home_env(tmp_path):
    tools = _installed_tools(tmp_path)
    ph = tmp_path / 'pd-home'
    _write_key(ph / 'config', FAKE_FILE_KEY)
    env = _base_env(tmp_path / 'home')
    env['PAPERDEPOT_HOME'] = str(ph)

    got = _probe(tools, env)

    assert got['key'] == FAKE_FILE_KEY
    assert Path(got['home']) == ph
    assert Path(got['config_dir']) == ph / 'config'


def test_missing_key_lists_checked_paths(tmp_path):
    tools = _installed_tools(tmp_path)
    env = _base_env(tmp_path / 'home')

    got = _probe(tools, env)
    assert got['key'] == ''

    r = _run_selftest_key(tools, env)
    assert r.returncode == 1
    assert 'key ok = False' in r.stdout
    # 安装态旧路径 <pkg>/pipeline/config 也在候选里，方便排查
    legacy = tools.parent / 'config' / 'secrets.local.json'
    assert str(legacy) in r.stdout


def test_selftest_key_reports_source_without_leaking_key(tmp_path):
    tools = _installed_tools(tmp_path)
    home = tmp_path / 'home'
    cfg = home / '.dsh' / 'paperdepot' / 'config'
    _write_key(cfg, FAKE_FILE_KEY)

    r = _run_selftest_key(tools, _base_env(home))

    assert r.returncode == 0
    assert 'key ok = True' in r.stdout
    assert str(cfg / 'secrets.local.json') in r.stdout
    assert FAKE_FILE_KEY not in r.stdout + r.stderr
