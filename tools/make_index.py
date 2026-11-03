#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_index — 从条目生成静态索引页

为什么用静态表格而不是 Dataview：
    · Dataview 要装插件，手机端更是用不了
    · 静态 Markdown 表格在任何地方都能看（Obsidian / 手机 App / GitHub）
    · 想用 Dataview 的话，同一份 frontmatter 照样能查，两者不冲突

产出：
    1-Papers/_index.md    全部论文总表（按年份倒序）
    1-Papers/_stats.md    统计概览
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

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _paths

FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def parse_frontmatter(text: str) -> dict:
    """极简 YAML frontmatter 解析（只处理本项目用到的标量/列表）"""
    m = FM_RE.match(text)
    if not m:
        return {}
    out = {}
    key = None
    for line in m.group(1).split('\n'):
        if not line.strip():
            continue
        if re.match(r'^\s*-\s+', line) and key:
            v = re.sub(r'^\s*-\s+', '', line).strip().strip('"').strip("'")
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(v)
            continue
        mm = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if mm:
            key, val = mm.group(1), mm.group(2).strip()
            if val in ('', '[]'):
                out[key] = [] if val == '[]' else ''
            else:
                out[key] = val.strip('"').strip("'")
    return out


def collect(papers_dir: str) -> list:
    rows = []
    for d in sorted(os.listdir(lp(papers_dir))):
        full = os.path.join(papers_dir, d)
        if not os.path.isdir(lp(full)) or d.startswith('_'):
            continue
        idx = os.path.join(full, 'index.md')
        if not os.path.isfile(lp(idx)):
            continue
        try:
            text = io.open(lp(idx), encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        fm = parse_frontmatter(text)
        m1 = re.search(r'##\s*一句话总结\s*\n+\s*>\s*(.+)', text)
        rows.append({
            'dir': d,
            'title': fm.get('title') or d,
            'year': fm.get('year') or '',
            'authors': fm.get('authors') or [],
            'journal': fm.get('journal') or '',
            'doi': fm.get('doi') or '',
            'arxiv': fm.get('arxiv') or '',
            'pages': fm.get('pages') or '',
            'figures': fm.get('figures') or '',
            'one_liner': m1.group(1).strip() if m1 else '',
            'status': (fm.get('status') or '').strip('"'),
            'fingerprint': fm.get('fingerprint') or '',
        })
    return rows


def esc(s: str) -> str:
    return str(s).replace('|', r'\|').replace('\n', ' ')


def short_authors(a: list, n: int = 2) -> str:
    if not a:
        return '—'
    a = [str(x) for x in a]
    if len(a) <= n:
        return ', '.join(a)
    first = a[0].split()[-1] if a[0].split() else a[0]
    return f'{first} 等 {len(a)} 人'


def make_index(rows: list) -> str:
    L = ['---', 'title: "论文总索引"', 'tags:', '  - 索引', '---', '',
         '# 📚 论文总索引', '']

    total = len(rows)
    need = [r for r in rows if r['status'] == 'needs_metadata']
    withdoi = [r for r in rows if r['doi']]
    # 同一 DOI 出现多次 = Zotero storage 里有重复 PDF
    doi_count = Counter(r['doi'] for r in rows if r['doi'])
    dups = {d: n for d, n in doi_count.items() if n > 1}
    L.append(f'**共 {total} 篇**　·　有 DOI {len(withdoi)} 篇　·　'
             f'待补元数据 {len(need)} 篇'
             + (f'　·　重复 DOI {len(dups)} 组' if dups else ''))
    L.append('')

    by_year = {}
    for r in rows:
        y = r['year'] or '未知'
        by_year.setdefault(y, []).append(r)

    L.append('## 按年份')
    L.append('')
    L.append('| 年份 | 篇数 |')
    L.append('|---|---|')
    for y in sorted(by_year, key=lambda x: (x == '未知', str(x))):
        L.append(f'| {y} | {len(by_year[y])} |')
    L.append('')

    for y in sorted(by_year, key=lambda x: (x == '未知', str(x)), reverse=True):
        L.append(f'## {y}（{len(by_year[y])} 篇）')
        L.append('')
        L.append('| 标题 | 一句话总结 | 作者 | 期刊 | 图 | DOI |')
        L.append('|---|---|---|---|---|---|')
        for r in sorted(by_year[y], key=lambda x: x['title'].lower()):
            disp = r['title'][:56] + ('…' if len(r['title']) > 56 else '')
            link = f'[[{r["dir"]}/index\\|{esc(disp)}]]'
            ol = (r.get('one_liner') or '').replace('|', '/')[:80]
            ol = ol + ('…' if len(r.get('one_liner') or '') > 80 else '')
            doi = r['doi'] or (f'[arXiv](https://arxiv.org/abs/{r["arxiv"]})'
                              if r['arxiv'] else '—')
            L.append(f'| {link} | {esc(ol) or "—"} | {esc(short_authors(r["authors"]))} | '
                     f'{esc(r["journal"][:28]) or "—"} | {r["figures"] or "—"} | {doi} |')
        L.append('')

    if dups:
        L.append('## ⚠ 重复条目（同一 DOI 多份）')
        L.append('')
        L.append('| DOI | 份数 | 条目 |')
        L.append('|---|---|---|')
        for d, n in sorted(dups.items(), key=lambda x: -x[1]):
            same = [r for r in rows if r['doi'] == d]
            links = '　'.join(f'[[{r["dir"]}/index|{r["dir"][:32]}]]' for r in same)
            L.append(f'| {d} | {n} | {links} |')
        L.append('')

    if need:
        L.append('## ⚠ 待补元数据')
        L.append('')
        for r in need:
            L.append(f'- [[{r["dir"]}/index|{r["title"][:70]}]]')
        L.append('')
    return '\n'.join(L)


def make_stats(rows: list) -> str:
    L = ['---', 'title: "论文库统计"', 'tags:', '  - 索引', '---', '',
         '# 📊 论文库统计', '']
    L.append('## 规模')
    L.append('')
    L.append('| 项 | 值 |')
    L.append('|---|---|')
    L.append(f'| 论文总数 | {len(rows)} |')
    L.append(f'| 有 DOI | {sum(1 for r in rows if r["doi"])} |')
    L.append(f'| 有 arXiv | {sum(1 for r in rows if r["arxiv"])} |')
    L.append(f'| 待补元数据 | {sum(1 for r in rows if r["status"] == "needs_metadata")} |')
    pgs = [int(r['pages']) for r in rows if str(r['pages']).isdigit()]
    if pgs:
        L.append(f'| 总页数 | {sum(pgs)} |')
    figs = [int(r['figures']) for r in rows if str(r['figures']).isdigit()]
    if figs:
        L.append(f'| 总图数 | {sum(figs)} |')
    L.append('')

    jc = Counter(r['journal'] for r in rows if r['journal'])
    if jc:
        L.append('## 期刊/会议分布')
        L.append('')
        L.append('| 期刊 | 篇数 |')
        L.append('|---|---|')
        for k, v in jc.most_common(20):
            L.append(f'| {esc(k[:52])} | {v} |')
        L.append('')

    years = [r['year'] for r in rows if r['year']]
    if years:
        L.append('## 年份范围')
        L.append('')
        L.append(f'{min(years)} — {max(years)}')
        L.append('')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', default=_paths.default_vault())
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if not os.path.isdir(papers):
        print('没有 1-Papers', file=sys.stderr)
        return 1

    rows = collect(papers)
    if not rows:
        print('没找到条目', file=sys.stderr)
        return 1

    io.open(lp(os.path.join(papers, '_index.md')), 'w', encoding='utf-8').write(
        make_index(rows))
    io.open(lp(os.path.join(papers, '_stats.md')), 'w', encoding='utf-8').write(
        make_stats(rows))

    print(f'✅ 索引已生成：{len(rows)} 篇')
    print(f'   1-Papers/_index.md')
    print(f'   1-Papers/_stats.md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
