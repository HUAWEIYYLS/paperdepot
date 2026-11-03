#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_obsidian_graph — 给 Obsidian 原生图视图写入「颜色分组 + 过滤」预设

背景：
    论文库的论文条目自带四类分层标签（领域/方法/应用/仪器）和双向链接
    （概念页 ↔ 论文）。Obsidian 图视图本身能显示这些节点和边，只是默认
    全是灰色、标签节点又太多，所以看起来是一团毛球。
    这个脚本把「按领域上色、概念页高亮、隐藏缓存/重复区、待补元数据标橙」
    写进 <vault>/.obsidian/graph.json，让原生图直接变成可读的分类视图。

Obsidian graph.json 关键结构（实测）：
    {
      "showTags": false,          # 关掉标签节点（176 个标签会变毛球）
      "showAttachments": false,
      "showOrphans": true,        # 没进概念层的论文也显示（外圈散点）
      "search": "-path:_duplicates/",
      "colorGroups": [
        {"query": "tag:#领域/天文仪器", "color": {"a": 1, "rgb": 3447003}}
      ],
      ...
    }
    query 语法与搜索框一致：path: / file: / tag: / line: / [field:value]，
    支持 AND / OR / - 取反；颜色是 RGB 十进制整数，不是 #hex。
    注意：分组从上到下匹配，**先匹配先生效**（specific 放前面）。

用法：
    python make_obsidian_graph.py --vault <路径>
    python make_obsidian_graph.py --vault <路径> --dry-run
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import time
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FM_RE = re.compile(r'^---\s*\n(.*?)\n---', re.S)
TAG_RE = re.compile(r'^\s*-\s+"?([^"\n]+)"?\s*$')
DOMAIN_PREFIX = '领域/'

# 面向前 12 个领域的配色（按出现次数从多到少分配）；超出用灰
PALETTE = [
    '#3498db',  # 蓝
    '#2ecc71',  # 绿
    '#e67e22',  # 橙
    '#9b59b6',  # 紫
    '#e84393',  # 粉
    '#f1c40f',  # 黄
    '#1abc9c',  # 青
    '#e74c3c',  # 红
    '#2980b9',  # 深蓝
    '#16a085',  # 深青
    '#8e44ad',  # 深紫
    '#d35400',  # 深橙
]

CONCEPT_COLOR = '#a78bfa'   # 概念页：紫
TAXONOMY_COLOR = '#ffd700'  # 分类页：金（3-Taxonomy/ 文件夹）
INDEX_COLOR = '#555555'     # 索引/统计：深灰
PENDING_COLOR = '#c0392b'   # 待补元数据：红
FALLBACK_COLOR = '#909090'  # 其它论文：灰


def hx(c):
    return int(c.lstrip('#'), 16)


def group(query, color):
    return {"query": query, "color": {"a": 1, "rgb": hx(color)}}


def collections(vault):
    """统计领域标签出现次数 -> [(domain, count)]"""
    papers = os.path.join(vault, '1-Papers')
    cnt = Counter()
    if not os.path.isdir(papers):
        return cnt
    for name in os.listdir(papers):
        idx = os.path.join(papers, name, 'index.md')
        if not os.path.isfile(idx):
            continue
        try:
            with io.open(idx, encoding='utf-8', errors='replace') as f:
                txt = f.read()
        except OSError:
            continue
        m = FM_RE.match(txt)
        if not m:
            continue
        block = m.group(1)
        for line in block.split('\n'):
            tm = TAG_RE.match(line)
            if not tm:
                continue
            tag = tm.group(1).strip()
            if tag.startswith(DOMAIN_PREFIX):
                cnt[tag[len(DOMAIN_PREFIX):]] += 1
    return cnt


def build_groups(vault):
    domains = collections(vault)
    groups = [
        # 先放特殊页（specific -> general）
        group('path:2-Concepts/', CONCEPT_COLOR),
        group('path:3-Taxonomy/', TAXONOMY_COLOR),
        group('path:1-Papers/_index.md', INDEX_COLOR),
        group('path:1-Papers/_stats.md', INDEX_COLOR),
        group('path:_duplicates/', INDEX_COLOR),
        # 待补元数据的论文先标出（可操作项）
        group('tag:#状态/待补元数据', PENDING_COLOR),
    ]
    for i, (domain, _count) in enumerate(domains.most_common()):
        color = PALETTE[i] if i < len(PALETTE) else '#7f8c8d'
        groups.append(group('tag:#%s%s' % (DOMAIN_PREFIX, domain), color))
    # 兜底：其余论文统一浅灰（不要覆盖概念/分类页）
    groups.append(group('-path:2-Concepts/ -path:3-Taxonomy/ -path:_duplicates/', FALLBACK_COLOR))
    return domains, groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    vault = os.path.abspath(a.vault)
    graph_path = os.path.join(vault, '.obsidian', 'graph.json')
    if not os.path.isfile(graph_path):
        print('❌ 找不到 .obsidian/graph.json：先用 Obsidian 打开一次这个库（让它生成设置文件）')
        return 1

    domains, groups = build_groups(vault)
    print('领域标签分布（%d 个）：' % len(domains))
    for d, c in domains.most_common():
        print('  %-24s %d' % (d, c))
    print('\n颜色分组（%d 个，先匹配先生效）：' % len(groups))
    for g in groups:
        print('  %-52s #%06x' % (g['query'][:52], g['color']['rgb']))

    if a.dry_run:
        print('\n[dry-run] 未写入')
        return 0

    backup = graph_path + '.bak-%s' % time.strftime('%Y%m%d-%H%M%S')
    with io.open(graph_path, encoding='utf-8') as f:
        data = json.load(f)

    updated = dict(data)
    updated.update({
        'showTags': False,        # 标签节点关掉，避免 176 个标签毛球
        'showAttachments': False,
        'hideUnresolved': True,
        'showOrphans': True,      # 没进概念层的论文也显示在外圈
        'search': '-path:_duplicates/',
        'showArrow': False,
        'textFadeMultiplier': 0,
        'nodeSizeMultiplier': 1,
        'lineSizeMultiplier': 0.7,
        'linkDistance': 180,
        'repelStrength': 12,
        'colorGroups': groups,
    })
    if json.dumps(updated, ensure_ascii=False, sort_keys=True) == json.dumps(data, ensure_ascii=False, sort_keys=True):
        print('\n颜色分组已是最新，跳过写入（不产生新备份）')
        return 0

    shutil.copy2(graph_path, backup)
    with io.open(graph_path, 'w', encoding='utf-8') as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)
        f.write('\n')
    # 只保留最近 3 份备份，避免反复导入时堆一堆 .bak
    import glob
    baks = sorted(glob.glob(graph_path + '.bak-*'))
    for old in baks[:-3]:
        try:
            os.remove(old)
        except OSError:
            pass
    print('\n✅ 已写入 %s' % graph_path)
    print('   备份：%s' % backup)
    print('   在 Obsidian 里按 Ctrl+R 重载（或重开库）即可看到效果。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
