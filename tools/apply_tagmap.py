#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_tagmap — 把发散标签替换成规范词表

读取 tagmap_{领域,方法,应用,仪器}.json，对每个 index.md：
  · frontmatter 里的 `- "方法/xxx"` 全部替换成规范词，并去重
  · 正文 `## 🏷 标签` 小节同步重建
  · 状态/* 标签保持不动

幂等：重复运行结果不变。

用法：
    python apply_tagmap.py --vault <路径> --dry-run
    python apply_tagmap.py --vault <路径>
"""
import argparse
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
# 词表放在 ../config/（与脚本分离）；若不存在则回退到脚本同目录
_CONFIG = os.path.join(os.path.dirname(HERE), 'config')
TAGMAP_DIR = _CONFIG if os.path.isdir(_CONFIG) else HERE
CATS = ('领域', '方法', '应用', '仪器')
FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)
TAGLINE_RE = re.compile(r'^(\s*)-\s+"?(领域|方法|应用|仪器)/(.+?)"?\s*$')
SECTION_RE = re.compile(r'^## 🏷 标签\s*$.*?(?=^## |\Z)', re.S | re.M)


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def load_maps():
    maps = {}
    for c in CATS:
        p = os.path.join(TAGMAP_DIR, f'tagmap_{c}.json')
        if not os.path.isfile(p):
            print(f'⚠ 缺少 {p}', file=sys.stderr)
            maps[c] = {}
            continue
        d = json.load(io.open(p, encoding='utf-8'))
        maps[c] = d.get('mapping', {})
    return maps


def canonical_of(maps, cat, tag):
    """查映射；查不到就用原标签（尽量不丢信息）"""
    return maps.get(cat, {}).get(tag, tag)


def process(text, maps):
    m = FM_RE.match(text)
    if not m:
        return text, 0
    fm_block = m.group(1)
    body = text[m.end():]

    # ---- frontmatter ----
    new_tags = []
    seen = set()
    changed = 0
    out_fm = []
    for line in fm_block.split('\n'):
        mm = TAGLINE_RE.match(line)
        if not mm:
            out_fm.append(line)
            continue
        cat, tag = mm.group(2), mm.group(3)
        canon = canonical_of(maps, cat, tag)
        if canon != tag:
            changed += 1
        key = f'{cat}/{canon}'
        if key in seen:
            changed += 1      # 归并后重复，删掉
            continue
        seen.add(key)
        new_tags.append((cat, canon))
        out_fm.append(f'  - "{key}"')

    new_text = '---\n' + '\n'.join(out_fm) + '\n---\n' + body

    # ---- 正文标签小节 ----
    by_cat = {}
    for cat, tag in new_tags:
        by_cat.setdefault(cat, [])
        if tag not in by_cat[cat]:
            by_cat[cat].append(tag)

    labels = {'领域': '研究领域', '方法': '技术方法',
              '应用': '应用场景', '仪器': '仪器设备'}
    sec = ['## 🏷 标签', '']
    for cat in CATS:
        items = by_cat.get(cat, [])
        if items:
            sec.append(f'**{labels[cat]}**：' + '　'.join(f'`{t}`' for t in items))
            sec.append('')
    sec_block = '\n'.join(sec)

    if SECTION_RE.search(new_text):
        new_text = SECTION_RE.sub(sec_block + '\n', new_text)
    else:
        # 插到「## 📄 相关文件」之前，否则追加到末尾
        if '## 📄 相关文件' in new_text:
            new_text = new_text.replace('## 📄 相关文件', sec_block + '\n## 📄 相关文件', 1)
        else:
            new_text = new_text.rstrip() + '\n\n' + sec_block

    return new_text, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    maps = load_maps()
    for c in CATS:
        print(f'  载入映射 {c}: {len(maps[c])} 条')

    papers = os.path.join(a.vault, '1-Papers')
    total_changed = 0
    files = 0
    for d in sorted(os.listdir(lp(papers))):
        if d.startswith('_'):
            continue
        base = os.path.join(papers, d)
        if not os.path.isdir(lp(base)):
            continue
        p = os.path.join(base, 'index.md')
        if not os.path.isfile(lp(p)):
            continue
        text = io.open(lp(p), encoding='utf-8', errors='replace').read()
        new, changed = process(text, maps)
        files += 1
        total_changed += changed
        if changed and not a.dry_run:
            io.open(lp(p), 'w', encoding='utf-8').write(new)

    print(f'\n处理 {files} 个条目，标签变更 {total_changed} 处'
          + ('（dry-run，未写入）' if a.dry_run else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
