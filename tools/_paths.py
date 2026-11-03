#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台路径与本地配置解析（论文库流水线共用）。

lp(): Windows 长路径前缀只在 Windows 添加；POSIX 原样返回。
default_vault(): 环境变量 → config/paperdepot.local.json → ~/Documents/ObsidianVault。
"""
import json
import os


def lp(p: str) -> str:
    """Windows 长路径前缀；POSIX 上原样返回。"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def config_dir() -> str:
    home = os.environ.get('PAPERDEPOT_HOME')
    if home:
        return os.path.join(home, 'config')
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.join(os.path.dirname(here), 'config')
    if os.path.isdir(repo):
        return repo
    return os.path.join(os.path.expanduser('~'), '.dsh', 'paperdepot', 'config')


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
