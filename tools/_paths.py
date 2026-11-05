#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台路径与本地配置解析（论文库流水线共用）。

lp(): Windows 长路径前缀只在 Windows 添加；POSIX 原样返回。
home_dir(): PAPERDEPOT_HOME → 开发态仓库根 / 安装态 ~/.dsh/paperdepot。
config_dir(): PAPERDEPOT_CONFIG_DIR → <home_dir>/config（与 DSH 宿主 lib/impl.js 同一处）。
default_vault(): 环境变量 → config/paperdepot.local.json → ~/Documents/ObsidianVault。

为什么要有安装态判定：
  npm / 市场安装时，流水线在 <插件包>/pipeline/tools/，而用户配置在
  ~/.dsh/paperdepot/config/（宿主 lib/impl.js 写在这里）。旧版把父目录的
  config/ 当成用户配置，安装态会指向插件包内只读的 pipeline/config/，
  与宿主各读各的路径 —— MinerU key 就是这样「面板说已配置、Python 说没配」。
"""
import json
import os


def lp(p: str) -> str:
    """Windows 长路径前缀；POSIX 上原样返回。"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def _tools_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


# 只有源码仓库（含 link 安装）才有的标记；npm 包按 package.json files 发布，不带这些。
_REPO_MARKERS = (
    os.path.join('tools', 'ingest.py'),
    os.path.join('scripts', 'pack-pipeline.mjs'),
)


def is_installed_layout() -> bool:
    """流水线是否在插件包的 pipeline/tools 下（npm / 市场 / tarball 安装）。"""
    tools = _tools_dir()
    pipeline_root = os.path.dirname(tools)
    if os.path.basename(pipeline_root) != 'pipeline':
        return False
    pkg_root = os.path.dirname(pipeline_root)
    return not any(os.path.exists(os.path.join(pkg_root, m)) for m in _REPO_MARKERS)


def home_dir() -> str:
    """配置与缓存根：环境变量 → 安装态 ~/.dsh/paperdepot → 开发态仓库根。"""
    home = (os.environ.get('PAPERDEPOT_HOME') or '').strip()
    if home:
        return home
    if is_installed_layout():
        return os.path.join(os.path.expanduser('~'), '.dsh', 'paperdepot')
    return os.path.dirname(_tools_dir())


def config_dir() -> str:
    """用户配置目录：显式覆盖 → <home_dir>/config。"""
    explicit = (os.environ.get('PAPERDEPOT_CONFIG_DIR') or '').strip()
    if explicit:
        return explicit
    return os.path.join(home_dir(), 'config')


def secrets_path() -> str:
    """MinerU key 等本机密钥文件（不进 git）。"""
    return os.path.join(config_dir(), 'secrets.local.json')


def default_vault() -> str:
    v = (os.environ.get('PAPERDEPOT_VAULT') or '').strip()
    if v:
        return v
    path = os.path.join(config_dir(), 'paperdepot.local.json')
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('vault'):
            return str(data['vault'])
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents', 'ObsidianVault')
