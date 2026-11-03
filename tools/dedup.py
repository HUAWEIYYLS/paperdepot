#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dedup — 去重（移动，不删除）

判定依据：
  ① 同 fingerprint  = 同一个 PDF 文件被入库多次 → 一定是重复
  ② 同 DOI          = 不同 PDF 但同一篇论文（Zotero 里存了两份）→ 重复

保留规则（打分最高者留下）：
  · 有 DOI            +3
  · status=parsed     +2
  · 有期刊            +1
  · 有作者            +1
  · 目录名更短        +0~1（更清爽）
  · 入库更早          +0.5（先到先得）

被淘汰的移动到 vault/_duplicates/<原名>，并在 _duplicates/_dedup_report.md 里留档。
随时可以把文件移回来。

用法：
    python dedup.py --vault <路径> --dry-run
    python dedup.py --vault <路径>
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def read_fm(path):
    try:
        text = io.open(lp(path), encoding='utf-8', errors='replace').read()
    except OSError:
        return {}
    m = FM_RE.match(text)
    if not m:
        return {}
    d = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if mm:
            d[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return d


def score(entry_dir, fm, ent):
    s = 0.0
    if fm.get('doi'):
        s += 3
    if 'parsed' in (fm.get('status') or ''):
        s += 2
    if fm.get('journal'):
        s += 1
    if fm.get('authors'):
        s += 1
    # 目录名更短更清爽
    s += max(0.0, 1.0 - len(os.path.basename(entry_dir)) / 120.0)
    # 先到先得
    try:
        s += 0.5 * (1.0 / (1.0 + os.path.getmtime(entry_dir) % 1000))
    except OSError:
        pass
    return s


def collect(papers):
    rows = []
    for d in sorted(os.listdir(lp(papers))):
        base = os.path.join(papers, d)
        if not os.path.isdir(lp(base)) or d.startswith('_'):
            continue
        idx = os.path.join(base, 'index.md')
        if not os.path.isfile(lp(idx)):
            continue
        fm = read_fm(idx)
        ent = {}
        ej = os.path.join(base, '.entry.json')
        if os.path.isfile(lp(ej)):
            try:
                ent = json.load(io.open(lp(ej), encoding='utf-8'))
            except Exception:
                ent = {}
        rows.append({'dir': d, 'base': base, 'fm': fm, 'ent': ent,
                     'score': score(base, fm, ent)})
    return rows


def clip(s: str, n: int = 74) -> str:
    """保留头尾，中间省略 —— 重复条目的区别往往在尾部"""
    if len(s) <= n:
        return s
    head = n - 30
    return s[:head] + ' …' + s[-(26):]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if not os.path.isdir(papers):
        print('没有 1-Papers', file=sys.stderr)
        return 1

    rows = collect(papers)
    print(f'扫描 {len(rows)} 个条目\n')

    by_fp = defaultdict(list)
    by_doi = defaultdict(list)
    for r in rows:
        fp = r['ent'].get('fingerprint') or r['fm'].get('fingerprint')
        doi = (r['ent'].get('doi') or r['fm'].get('doi') or '').lower().strip()
        if fp:
            by_fp[fp].append(r)
        if doi:
            by_doi[doi].append(r)

    # 收集要淘汰的（同一目录只淘汰一次）
    drop = {}          # dir -> (reason, kept_dir)

    for fp, group in by_fp.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: -x['score'])
        keep = group[0]
        for r in group[1:]:
            drop.setdefault(r['dir'], (f'同 fingerprint {fp}', keep['dir']))

    for doi, group in by_doi.items():
        alive = [r for r in group if r['dir'] not in drop]
        if len(alive) < 2:
            continue
        alive.sort(key=lambda x: -x['score'])
        keep = alive[0]
        for r in alive[1:]:
            drop.setdefault(r['dir'], (f'同 DOI {doi}', keep['dir']))

    print(f'检测到重复，需淘汰 {len(drop)} 个条目\n')
    if not drop:
        print('✅ 没有重复')
        return 0

    for d, (reason, kept) in sorted(drop.items()):
        print(f'  ✂ 淘汰: {clip(d)}')
        print(f'        原因: {reason}')
        print(f'        保留: {clip(kept)}')

    if a.dry_run:
        print('\nDRY-RUN 结束，未做任何修改。去掉 --dry-run 执行。')
        return 0

    dup_root = os.path.join(a.vault, '_duplicates')
    os.makedirs(lp(dup_root), exist_ok=True)

    moved = 0
    for d, (reason, kept) in sorted(drop.items()):
        src = os.path.join(papers, d)
        dst = os.path.join(dup_root, d)
        # 目标已存在则加序号
        if os.path.exists(lp(dst)):
            i = 2
            while os.path.exists(lp(dst + f' ({i})')):
                i += 1
            dst = dst + f' ({i})'
        try:
            shutil.move(lp(src), lp(dst))
            moved += 1
        except Exception as exc:
            print(f'  ❌ 移动失败 {d[:50]}: {exc}')

    # 留档
    rep = ['---', 'title: "去重报告"', '---', '',
           '# 去重报告', '',
           f'隔离条目：{moved} 个', '',
           '被隔离的条目仍完整保存在 `_duplicates/`，需要时可直接移回 `1-Papers/`。', '',
           '| 被隔离 | 原因 | 保留的条目 |', '|---|---|---|']
    for d, (reason, kept) in sorted(drop.items()):
        rep.append(f'| {d[:60]} | {reason} | {kept[:60]} |')
    io.open(lp(os.path.join(dup_root, '_dedup_report.md')), 'w',
            encoding='utf-8').write('\n'.join(rep))

    print(f'\n✅ 已隔离 {moved} 个条目 → {dup_root}')
    print(f'   报告: {os.path.join(dup_root, "_dedup_report.md")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
