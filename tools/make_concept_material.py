#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_concept_material — 从论文条目抽概念素材

按标签召回 1-Papers/*/index.md，抽出写概念页所需的最小素材：
每篇的 目录 / 年份 / 期刊 / 命中标签 / 一句话总结 / 主要结果。

输出：<out-dir>/_concept_<概念名>.md
（out-dir 默认 ../cache，素材不进 vault）

标签召回只是候选池，含噪声；概念页撰写时必须人工按标题+摘要再筛一遍。

用法：
    python make_concept_material.py --name 光纤扰频 --tags 方法/光纤扰频
    python make_concept_material.py --name 图像复原 \
        --tags 方法/反卷积 方法/图像重建 方法/盲反卷积
"""
import argparse
import io
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _paths

DEFAULT_VAULT = _paths.default_vault()
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), 'cache')


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def read(p):
    return io.open(lp(p), encoding='utf-8', errors='replace').read()


def fm(txt):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', txt, re.S)
    return m.group(1) if m else ''


def field(f, k):
    m = re.search(rf'^{re.escape(k)}:\s*(.+?)\s*$', f, re.M)
    if not m:
        return ''
    v = m.group(1).strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'' else v


def tags_of(f):
    m = re.search(r'^tags:\s*\n((?:\s*-\s*.+\n?)+)', f, re.M)
    if not m:
        return []
    return [l.strip().lstrip('- ').strip().strip('"\'')
            for l in m.group(1).splitlines()]


def section(txt, name):
    m = re.search(rf'^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)', txt, re.S | re.M)
    return m.group(1).strip() if m else ''


def clean(s, n):
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', s)
    s = re.sub(r'\n{2,}', '\n', s)
    return s[:n].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True, help='概念名（用作文件名）')
    ap.add_argument('--tags', nargs='+', required=True,
                    help='召回用的标签（取并集），如 方法/反卷积 方法/图像重建')
    ap.add_argument('--vault', default=DEFAULT_VAULT)
    ap.add_argument('--out-dir', default=DEFAULT_OUT)
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if not os.path.isdir(lp(papers)):
        print(f'❌ 找不到 {papers}')
        return 1

    rows = []
    for d in sorted(os.listdir(lp(papers))):
        p = os.path.join(papers, d, 'index.md')
        if not os.path.isfile(lp(p)):
            continue
        txt = read(p)
        f = fm(txt)
        tset = set(tags_of(f))
        hit = [t for t in a.tags if t in tset]
        if not hit:
            continue
        rows.append(dict(
            dir=d,
            title=field(f, 'title') or d,
            year=field(f, 'year'),
            journal=field(f, 'journal'),
            status=field(f, 'status'),
            hit=hit,
            summary=clean(section(txt, '一句话总结'), 500),
            results=clean(section(txt, '主要结果'), 900),
        ))

    os.makedirs(a.out_dir, exist_ok=True)
    dst = os.path.join(a.out_dir, f'_concept_{a.name}.md')

    out = [f'# 概念素材：{a.name}  （{len(rows)} 篇，召回标签 {", ".join(a.tags)}）',
           '',
           '> 这是按标签机械召回的候选池，**含噪声**。撰写概念页时按标题与一句话总结',
           '> 人工判断相关性，不相关的篇目不要收录、也不要提及。',
           '']
    for i, r in enumerate(rows, 1):
        out.append(f'## {i}. {r["title"]}')
        out.append(f'- 目录：`{r["dir"]}`')
        out.append(f'- 年份：{r["year"]}｜期刊：{r["journal"] or "—"}｜'
                   f'状态：{r["status"]}｜命中标签：{", ".join(r["hit"])}')
        out.append('- 一句话总结：' + r['summary'].replace('\n', ' '))
        out.append('- 主要结果：')
        out.append(r['results'])
        out.append('')

    io.open(dst, 'w', encoding='utf-8').write('\n'.join(out))
    size = os.path.getsize(dst)
    print(f'{a.name}: 召回 {len(rows)} 篇 → {dst}（{size/1024:.1f} KB）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
