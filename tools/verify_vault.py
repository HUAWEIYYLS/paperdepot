#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_vault — 条目完整性自检

检查每篇论文：
  1. 必备文件是否齐全   index.md / full.md / paper.pdf / images/ / .entry.json
  2. frontmatter 是否可解析，关键字段是否缺失
  3. full.md 里的图片引用是否全部存在（这条直接对应"破图"）
  4. 目录名长度是否安全（≤120，防止路径超限）
  5. 是否有重复（同 fingerprint 或同 DOI）

用法：
    python verify_vault.py --vault <路径>
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

IMG_REF = re.compile(r'!\[[^\]]*\]\(images/([^)]+)\)')
FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)
REQUIRED = ['index.md', 'full.md', 'paper.pdf']
REQUIRED_DIRS = ['images']


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def check_dirs(roots):
    """检查根目录名不超 260"""
    issues = []
    for r in roots:
        if len(r) > 240:
            issues.append(f'根路径过长 {len(r)}: {r}')
    return issues


def verify_one(base: str) -> dict:
    r = {'dir': os.path.basename(base), 'issues': [], 'warn': [],
         'images': 0, 'broken': 0}

    names = set(os.listdir(lp(base)))
    for f in REQUIRED:
        if f not in names:
            r['issues'].append(f'缺 {f}')
    for d in REQUIRED_DIRS:
        if d not in names:
            r['issues'].append(f'缺 {d}/')

    # frontmatter
    idx = os.path.join(base, 'index.md')
    if os.path.isfile(lp(idx)):
        text = io.open(lp(idx), encoding='utf-8', errors='replace').read()
        m = FM_RE.match(text)
        if not m:
            r['issues'].append('index.md 无 frontmatter')
        else:
            fm = m.group(1)
            for k in ('title:', 'source:'):
                if k not in fm:
                    r['warn'].append(f'frontmatter 缺 {k.rstrip(":")}')
            if 'needs_metadata' in fm:
                r['warn'].append('待补元数据')

    # 图片引用
    full = os.path.join(base, 'full.md')
    if os.path.isfile(lp(full)):
        md = io.open(lp(full), encoding='utf-8', errors='replace').read()
        refs = IMG_REF.findall(md)
        r['images'] = len(refs)
        imgdir = os.path.join(base, 'images')
        have = set(os.listdir(lp(imgdir))) if os.path.isdir(lp(imgdir)) else set()
        missing = [x for x in refs if x not in have]
        r['broken'] = len(missing)
        if missing:
            r['issues'].append(f'{len(missing)} 张图引用不存在')

    # 目录名长度
    if len(r['dir']) > 120:
        r['warn'].append(f'目录名 {len(r["dir"])} 字符（建议 ≤120）')

    # 路径总长
    deepest = os.path.join(base, 'images', 'fig99.jpg')
    if len(deepest) > 250:
        r['issues'].append(f'最深路径 {len(deepest)} 字符，接近上限')

    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if not os.path.isdir(papers):
        print('没有 1-Papers', file=sys.stderr)
        return 1

    dirs = [os.path.join(papers, d) for d in sorted(os.listdir(lp(papers)))
            if os.path.isdir(lp(os.path.join(papers, d))) and not d.startswith('_')]

    print(f'检查 {len(dirs)} 个条目\n')
    results = [verify_one(d) for d in dirs]

    ok = [r for r in results if not r['issues']]
    bad = [r for r in results if r['issues']]
    warn = [r for r in results if r['warn'] and not r['issues']]

    total_img = sum(r['images'] for r in results)
    total_broken = sum(r['broken'] for r in results)

    print('=' * 70)
    print(f'条目总数      : {len(results)}')
    print(f'完全正常      : {len(ok)}')
    print(f'有警告        : {len(warn)}')
    print(f'有错误        : {len(bad)}')
    print(f'图片引用总数  : {total_img}')
    print(f'其中断链      : {total_broken}')
    print('=' * 70)

    if bad:
        print('\n【错误】')
        for r in bad[:30]:
            print(f'  ❌ {r["dir"][:60]}')
            for i in r['issues']:
                print(f'       {i}')
        if len(bad) > 30:
            print(f'  … 另有 {len(bad)-30} 个')

    warn_groups = Counter()
    for r in warn:
        for w in r['warn']:
            warn_groups[w] += 1
    if warn_groups:
        print('\n【警告汇总】')
        for w, n in warn_groups.most_common():
            print(f'  ⚠ {w}: {n} 个')

    # 重复检测
    fps = Counter()
    dois = Counter()
    for d in dirs:
        ej = os.path.join(d, '.entry.json')
        if os.path.isfile(lp(ej)):
            try:
                e = json.load(io.open(lp(ej), encoding='utf-8'))
                if e.get('fingerprint'):
                    fps[e['fingerprint']] += 1
                if e.get('doi'):
                    dois[e['doi'].lower()] += 1
            except Exception:
                pass
    dup_fp = {k: v for k, v in fps.items() if v > 1}
    dup_doi = {k: v for k, v in dois.items() if v > 1}
    if dup_fp or dup_doi:
        print('\n【重复】')
        if dup_fp:
            print(f'  同 fingerprint（同一 PDF 入库多次）: {len(dup_fp)} 组')
            for k, v in list(dup_fp.items())[:8]:
                print(f'     {k} × {v}')
        if dup_doi:
            print(f'  同 DOI（不同 PDF 但同一论文）: {len(dup_doi)} 组')
            for k, v in list(dup_doi.items())[:8]:
                print(f'     {k} × {v}')

    return 0 if not bad else 2


if __name__ == '__main__':
    sys.exit(main())
