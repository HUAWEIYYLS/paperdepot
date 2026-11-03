#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_concept_index — 生成 2-Concepts/_index.md

扫描 2-Concepts/*.md 的 frontmatter 与首段引言，输出一个纯 markdown 索引页：
  · 按引用论文数降序的表格（概念 | 论文数 | 一句话）
  · 按四类标签分组的清单（领域 / 方法 / 应用 / 仪器）

不依赖任何插件，手机端可读。

用法：
    python make_concept_index.py --vault <vault路径>
    python make_concept_index.py --vault <vault路径> --dry-run
"""
import argparse
import datetime
import io
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
CATS = ('领域', '方法', '应用', '仪器')
FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)


def parse(text):
    m = FM_RE.match(text)
    fm = m.group(1) if m else ''
    body = text[m.end():] if m else text

    def scalar(key):
        mm = re.search(rf'^{re.escape(key)}:\s*(.+?)\s*$', fm, re.M)
        if not mm:
            return ''
        v = mm.group(1).strip()
        return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'' else v

    def block_list(key):
        mm = re.search(rf'^{re.escape(key)}:\s*\n((?:[ \t]*-[^\n]*\n?)+)', fm, re.M)
        if not mm:
            return []
        return [l.strip()[1:].strip().strip('"\'')
                for l in mm.group(1).splitlines() if l.strip().startswith('-')]

    one = ''
    qm = re.search(r'^>\s*\*\*一句话\*\*[：:]\s*(.+)$', body, re.M)
    if qm:
        one = qm.group(1).strip()
    else:
        qm = re.search(r'^>\s*(.+)$', body, re.M)
        if qm:
            one = qm.group(1).strip()
    one = one.replace('|', '\\|')

    return dict(title=scalar('title'), papers=scalar('papers'),
                updated=scalar('updated'), tags=block_list('tags'), one=one)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    cdir = os.path.join(a.vault, '2-Concepts')
    if not os.path.isdir(cdir):
        print(f'❌ 不存在 {cdir}')
        return 1

    rows = []
    for f in sorted(os.listdir(cdir)):
        if not f.endswith('.md') or f.startswith('_'):
            continue
        name = os.path.splitext(f)[0]
        text = io.open(os.path.join(cdir, f), encoding='utf-8',
                       errors='replace').read()
        d = parse(text)
        d['name'] = d['title'] or name
        rows.append(d)

    if not rows:
        print('没有概念页')
        return 1

    def pcount(r):
        try:
            return int(r['papers'])
        except (TypeError, ValueError):
            return 0

    rows.sort(key=lambda r: (-pcount(r), r['name']))
    total_papers = sum(pcount(r) for r in rows)
    today = datetime.date.today().isoformat()

    out = ['# 概念索引', '',
           f'> {len(rows)} 个概念 · 累计引用 {total_papers} 篇次 · 更新于 {today}', '>',
           '> 概念层只装跨论文概念；论文条目见 [[1-Papers/_index|论文总索引]]。',
           '',
           '| 概念 | 论文数 | 一句话 |',
           '|---|---:|---|']
    for r in rows:
        out.append(f"| [[2-Concepts/{r['name']}|{r['name']}]] | {pcount(r)} | {r['one']} |")

    for cat in CATS:
        items = []
        for r in rows:
            for t in r['tags']:
                if t.startswith(cat + '/'):
                    items.append((t.split('/', 1)[1], r['name']))
        if not items:
            continue
        out.append('')
        out.append(f'## {cat}')
        out.append('')
        by_tag = {}
        for tag, name in items:
            by_tag.setdefault(tag, []).append(name)
        for tag in sorted(by_tag):
            out.append(f"- **{tag}**：" + '　'.join(
                f"[[2-Concepts/{n}|{n}]]" for n in sorted(by_tag[tag])))

    out.append('')
    text = '\n'.join(out)
    dst = os.path.join(cdir, '_index.md')
    if a.dry_run:
        print(text)
        return 0
    io.open(dst, 'w', encoding='utf-8').write(text)
    print(f'✅ 概念索引已生成：{len(rows)} 个概念 → {dst}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
