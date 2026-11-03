#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_nav — 给论文条目补「所属概念 / 分类」导航块，并生成 3-Taxonomy/ 分类页

为什么：
    Obsidian 原生图只画链接。论文之间没有链接，只有概念页 → 论文的单向链接，
    所以图里看不出「分类 ↔ 论文」的层级。这个脚本做两件事：
      1. 每篇论文 index.md 末尾追加带标记的导航块（概念 + 分类 wikilink）
      2. 生成 3-Taxonomy/ 分类页（领域全部 + 高频方法/应用/仪器），
         分类页里链回论文，形成「分类页 ↔ 论文」的双向边

幂等：
    导航块用 <!-- paperdepot:nav:start --> / <!-- paperdepot:nav:end --> 包起来，
    重复运行会先删旧块再写新块；apply_summary 重建 index.md 时也会保留该块。

用法：
    python make_nav.py --vault <路径>
    python make_nav.py --vault <路径> --dry-run
    python make_nav.py --vault <路径> --method-top 12 --app-top 8 --inst-top 8
"""
import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(os.path.dirname(HERE), 'config')

FM_RE = re.compile(r'^---\s*\n(.*?)\n---', re.S)
TAG_LINE = re.compile(r'^\s*-\s+"?([^"\n]+?)"?\s*$')
NAV_RE = re.compile(r'\n*<!-- paperdepot:nav:start -->.*?<!-- paperdepot:nav:end -->\n*', re.S)
LINK_RE = re.compile(r'\[\[1-Papers/([^|\]]+?)/index\b[^\]]*\]\]')

CATS = [('领域', '领域'), ('方法', '方法'), ('应用', '应用'), ('仪器', '仪器')]


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def load_tagmap(cat):
    """返回 (mapping, canonical_set)"""
    p = os.path.join(CONFIG, 'tagmap_%s.json' % cat)
    try:
        with io.open(p, encoding='utf-8') as f:
            d = json.load(f)
        mapping = d.get('mapping', {})
        return mapping, set(mapping.values())
    except (OSError, ValueError):
        return {}, set()


def parse_frontmatter(text):
    m = FM_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^([A-Za-z_][\w-]*):\s*(.+?)\s*$', line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    tags = []
    tm = re.search(r'^tags:\s*\n((?:[ \t]*-[^\n]*\n?)+)', m.group(1), re.M)
    if tm:
        for line in tm.group(1).split('\n'):
            t = TAG_LINE.match(line)
            if t:
                tags.append(t.group(1).strip())
    return {'fm': fm, 'tags': tags}


def load_papers(vault):
    papers = {}
    base = os.path.join(vault, '1-Papers')
    if not os.path.isdir(base):
        return papers
    for name in sorted(os.listdir(base)):
        idx = os.path.join(base, name, 'index.md')
        if not os.path.isfile(idx):
            continue
        try:
            txt = io.open(idx, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        info = parse_frontmatter(txt)
        fm = info['fm']
        papers[name] = {
            'dir': name,
            'path': idx,
            'title': fm.get('title', name),
            'year': fm.get('year', ''),
            'tags': info['tags'],
            'text': txt,
        }
    return papers


def load_concepts(vault):
    """dir -> [概念名]"""
    base = os.path.join(vault, '2-Concepts')
    out = defaultdict(list)
    if not os.path.isdir(base):
        return out
    for f in sorted(os.listdir(base)):
        if not f.endswith('.md') or f.startswith('_'):
            continue
        name = f[:-3]
        try:
            txt = io.open(os.path.join(base, f), encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for m in LINK_RE.finditer(txt):
            d = m.group(1).strip()
            if d and name not in out[d]:
                out[d].append(name)
    return out


def norm_tags(papers, maps):
    """每篇论文 -> {类别: [规范值]}"""
    per = {}
    for d, p in papers.items():
        cats = {}
        for cat in ('领域', '方法', '应用', '仪器'):
            mapping, _canon = maps[cat]
            vals = []
            for tag in p['tags']:
                if not tag.startswith(cat + '/'):
                    continue
                raw = tag[len(cat) + 1:]
                v = mapping.get(raw, raw)
                if v and v not in vals:
                    vals.append(v)
            cats[cat] = vals
        per[d] = cats
    return per


def safe_name(v):
    return re.sub(r'[\\/:*?"<>|]', '－', v).strip()[:80]


def build_taxonomy(per, papers, method_top, app_top, inst_top, min_papers=2):
    counts = {c: Counter() for c, _ in CATS}
    for d, cats in per.items():
        for cat, _ in CATS:
            for v in cats[cat]:
                counts[cat][v] += 1
    selected = {}
    for cat, _ in CATS:
        items = [(v, c) for v, c in counts[cat].most_common() if c >= min_papers]
        if cat == '领域':
            picked = items  # 领域：建页（过滤掉只出现 1 次的生僻词）
        elif cat == '方法':
            picked = items[:method_top]
        elif cat == '应用':
            picked = items[:app_top]
        else:
            picked = items[:inst_top]
        selected[cat] = {v for v, c in picked if c > 0}
    return counts, selected


def taxonomy_filename(cat, value):
    return '%s-%s.md' % (cat, safe_name(value))


def write_taxonomy(vault, selected, counts, papers, per, dry_run):
    out_dir = os.path.join(vault, '3-Taxonomy')
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
    now = time.strftime('%Y-%m-%d')
    made = 0
    expected = set()
    for cat, _ in CATS:
        for value in sorted(selected[cat]):
            members = [d for d, cats in per.items() if value in cats[cat]]
            members.sort(key=lambda d: (papers[d]['year'] or '0000'), reverse=True)
            lines = [
                '---',
                'title: "%s · %s"' % (cat, value),
                'type: taxonomy',
                'category: "%s"' % cat,
                'value: "%s"' % value,
                'papers: %d' % len(members),
                'updated: %s' % now,
                '---',
                '',
                '# %s · %s' % (cat, value),
                '',
                '> 共 %d 篇论文（按年份倒序）。本页由 `tools/make_nav.py` 生成，可重复运行。' % len(members),
                '',
                '## 论文',
                '',
            ]
            for d in members:
                p = papers[d]
                lines.append('- [[1-Papers/%s/index|%s]]（%s）' % (d, p['title'], p['year'] or '—'))
            content = '\n'.join(lines) + '\n'
            fname = taxonomy_filename(cat, value)
            expected.add(fname)
            if not dry_run:
                io.open(lp(os.path.join(out_dir, fname)), 'w', encoding='utf-8').write(content)
            made += 1
    # 清理过期分类页（例如某篇论文删掉后，某个方法掉出 Top N）
    if not dry_run and os.path.isdir(out_dir):
        stale = re.compile(r'^(%s)-.+\.md$' % '|'.join(cat for cat, _ in CATS))
        for f in os.listdir(out_dir):
            if f == '_index.md' or f in expected:
                continue
            if stale.match(f):
                try:
                    os.remove(lp(os.path.join(out_dir, f)))
                except OSError:
                    pass
    # 分类索引
    lines = ['---', 'title: "分类索引"', 'type: taxonomy-index', 'updated: %s' % now, '---', '', '# 分类索引', '',
             '| 分类 | 数量 | 页面 |', '|---|---|---|']
    for cat, _ in CATS:
        for value in sorted(selected[cat], key=lambda v: -counts[cat][v]):
            lines.append('| %s | %d | [[3-Taxonomy/%s|%s]] |' % (cat, counts[cat][value], taxonomy_filename(cat, value)[:-3], value))
    if not dry_run:
        io.open(lp(os.path.join(out_dir, '_index.md')), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    return made


def nav_block_for(paper_dir, concepts, per, selected, counts):
    cons = concepts.get(paper_dir, [])
    cats = per[paper_dir]
    taxa = []
    for cat, _ in CATS:
        vals = [v for v in cats[cat] if v in selected[cat]]
        vals.sort(key=lambda v: -counts[cat][v])
        cap = {'领域': 2, '方法': 2, '应用': 1, '仪器': 2}[cat]
        for v in vals[:cap]:
            taxa.append((cat, v))
    if not cons and not taxa:
        return ''
    L = ['<!-- paperdepot:nav:start -->', '## 所属概念', '']
    if cons:
        L += ['- [[2-Concepts/%s]]' % c for c in cons]
    else:
        L.append('- （暂无）')
    L += ['', '## 分类', '']
    if taxa:
        L += ['- [[3-Taxonomy/%s|%s · %s]]' % (taxonomy_filename(cat, v)[:-3], cat, v) for cat, v in taxa]
    else:
        L.append('- （暂无）')
    L.append('<!-- paperdepot:nav:end -->')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--method-top', type=int, default=12)
    ap.add_argument('--app-top', type=int, default=8)
    ap.add_argument('--inst-top', type=int, default=8)
    ap.add_argument('--min-papers', type=int, default=2, help='领域分类页的最少论文数（过滤生僻词）')
    ap.add_argument('--no-paper-update', action='store_true')
    a = ap.parse_args()

    vault = os.path.abspath(a.vault)
    papers = load_papers(vault)
    concepts = load_concepts(vault)
    maps = {cat: load_tagmap(cat) for cat, _ in CATS}
    per = norm_tags(papers, maps)
    # 小库（刚建库/只有几篇）不启用生僻词阈值，否则分类页会一个都建不出来
    min_papers = 1 if len(papers) < 20 else a.min_papers
    counts, selected = build_taxonomy(per, papers, a.method_top, a.app_top, a.inst_top, min_papers)

    print('论文 %d 篇；概念关联 %d 篇；分类页阈值 min_papers=%d' % (len(papers), len(concepts), min_papers))
    for cat, _ in CATS:
        print('  %s：使用 %d 种，建页 %d 个' % (cat, len(counts[cat]), len(selected[cat])))

    made = write_taxonomy(vault, selected, counts, papers, per, a.dry_run)
    print('分类页：%d 个 %s' % (made, '(dry-run，未写入)' if a.dry_run else '→ 3-Taxonomy/'))

    if a.no_paper_update:
        print('跳过论文导航块更新')
        return 0

    updated = 0
    for d, p in papers.items():
        block = nav_block_for(d, concepts, per, selected, counts)
        text = p['text']
        stripped = NAV_RE.sub('\n', text).rstrip()
        new_text = stripped + ('\n\n' + block + '\n' if block else '\n')
        if new_text != text:
            updated += 1
            if not a.dry_run:
                io.open(lp(p['path']), 'w', encoding='utf-8').write(new_text)
    print('论文导航块：%d 篇%s' % (updated, '（dry-run，未写入）' if a.dry_run else '已更新'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
