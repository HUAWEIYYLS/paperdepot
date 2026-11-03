#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_summary — 把 LLM 生成的 summary.md / tags.md 合并进 index.md

设计取舍：每篇论文只保留一个入口页 index.md
    · 生成阶段：LLM 分别写 summary.md（长文）+ tags.md（四类标签），结构清晰好写
    · 合并阶段：把两者塞进 index.md，然后删除临时文件
    · 结果：Obsidian 里打开一个 index.md 就能看到元数据 + 摘要 + 标签 + 全文链接

标签写进 frontmatter（分层 tag，决策 5 的 A 方案）：
    领域/天文光纤光谱处理
    方法/光谱提取
    应用/多目标光谱
    仪器/LAMOST
这样 Obsidian 标签面板会显示成树，Dataview 也能查。

用法：
    python apply_summary.py --vault <路径> --entry "<条目目录名>"
    python apply_summary.py --vault <路径> --all
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_entry

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)
# make_nav.py 生成的导航块：重建 index.md 时要保留
NAV_BLOCK_RE = re.compile(r'<!-- paperdepot:nav:start -->.*?<!-- paperdepot:nav:end -->', re.S)
# tags.md 的四类小节
TAG_SECTIONS = {
    '研究领域': '领域',
    '技术方法': '方法',
    '应用场景': '应用',
    '仪器设备': '仪器',
}
TAG_LINE = re.compile(r'^\s*[-*]\s+(.+?)\s*$')


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def strip_frontmatter(text: str) -> str:
    m = FM_RE.match(text)
    return text[m.end():] if m else text


def parse_list_field(block: str, name: str) -> list:
    """解析 frontmatter 里 name 的列表值（支持 [a, b] 和块列表两种写法）。"""
    m = re.search(r'^' + re.escape(name) + r':\s*\[(.*?)\]\s*$', block, re.M)
    if m:
        return [x.strip().strip('"').strip("'") for x in m.group(1).split(',') if x.strip()]
    m = re.search(r'^' + re.escape(name) + r':\s*$', block, re.M)
    if not m:
        return []
    out = []
    for line in block[m.end():].split('\n'):
        if re.match(r'^\s*-\s+', line):
            out.append(re.sub(r'^\s*-\s+', '', line).strip().strip('"').strip("'"))
        elif line.strip() and not line.startswith((' ', '\t')):
            break
    return out


def parse_scalar_field(block: str, name: str) -> str:
    m = re.search(r'^' + re.escape(name) + r':\s*(.+?)\s*$', block, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else ''


def parse_tags_md(text: str) -> dict:
    """从 tags.md 解析四类标签 -> {'领域': [...], ...}"""
    out = {}
    cur = None
    for line in text.split('\n'):
        h = re.match(r'^#{1,3}\s*(.+?)\s*$', line)
        if h:
            name = h.group(1).strip()
            cur = None
            for cn, prefix in TAG_SECTIONS.items():
                if cn in name:
                    cur = prefix
                    out.setdefault(cur, [])
                    break
            continue
        if cur:
            m = TAG_LINE.match(line)
            if m:
                v = m.group(1).strip()
                v = re.sub(r'\s*[（(].*?[)）]\s*$', '', v)   # 去掉英文括号解释，保留简洁标签
                v = v.strip()
                if v and v not in out[cur]:
                    out[cur].append(v)
    return out


def yaml_list(items, indent='  '):
    return [f'{indent}- {build_entry.yq(t)}' for t in items]


TAGLIKE = re.compile(r'^(状态|领域|方法|应用|仪器)/')


def parse_authors(fm_block: str) -> list:
    """
    只解析 authors: 这个块的列表项。

    ⚠️ 不能用「抓所有 - 行」——frontmatter 里 tags: 也是同样的列表写法，
       那样会把标签当成作者（实测 bug）。
    另外过滤掉 TAGLIKE，兼容已经写坏的文件。
    """
    out = []
    inside = False
    for line in fm_block.split('\n'):
        if re.match(r'^authors:\s*', line):
            inside = True
            continue
        if inside:
            if re.match(r'^\s*-\s+', line):
                v = re.sub(r'^\s*-\s+', '', line).strip().strip('"').strip("'")
                if v and not TAGLIKE.match(v):
                    out.append(v)
            elif line.strip():
                inside = False
    return out


def rebuild_index(entry_dir: str, summary_text: str, tags: dict) -> str:
    """用 build_entry 的元数据 + LLM 摘要 + 分层标签，重建 index.md"""
    idx_path = os.path.join(entry_dir, 'index.md')
    old = io.open(lp(idx_path), encoding='utf-8', errors='replace').read()
    m = FM_RE.match(old)
    fm = {}
    fm_block = ''
    if m:
        fm_block = m.group(1)
        for line in fm_block.split('\n'):
            mm = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
            if mm:
                fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")

    title = fm.get('title', os.path.basename(entry_dir))
    authors_raw = parse_authors(fm_block)

    # summary.md 的 frontmatter 里带检索字段（aliases / keywords / citekey）
    sm = FM_RE.match(summary_text)
    sfm_block = sm.group(1) if sm else ''
    aliases = parse_list_field(sfm_block, 'aliases')
    keywords = parse_list_field(sfm_block, 'keywords')
    citekey = parse_scalar_field(sfm_block, 'citekey')

    # ---- frontmatter ----
    L = ['---', f'title: {build_entry.yq(title)}']
    if authors_raw:
        L.append('authors:')
        L += [f'  - {build_entry.yq(a)}' for a in authors_raw]
    else:
        L.append('authors: []')
    for k in ('year', 'journal', 'doi', 'arxiv', 'type'):
        if fm.get(k):
            L.append(f'{k}: {build_entry.yq(fm[k])}')
    L.append('source: "paper"')
    L.append(f'status: "{("parsed" if "needs_metadata" not in fm.get("status", "") else "needs_metadata")}"')
    L.append('summarized: true')
    for k in ('fingerprint', 'pages', 'figures', 'chars', 'added'):
        if fm.get(k):
            L.append(f'{k}: {fm[k]}')
    if aliases:
        L.append('aliases:')
        L += [f'  - {build_entry.yq(a)}' for a in aliases]
    if keywords:
        L.append('keywords:')
        L += [f'  - {build_entry.yq(k)}' for k in keywords]
    if citekey:
        L.append(f'citekey: {build_entry.yq(citekey)}')

    all_tags = ['状态/已总结']
    if fm.get('doi'):
        all_tags.append('状态/有DOI')
    for prefix in ('领域', '方法', '应用', '仪器'):
        for t in tags.get(prefix, []):
            all_tags.append(f'{prefix}/{t}')
    L.append('tags:')
    L += yaml_list(all_tags)
    L.append('---')
    L.append('')

    # ---- 正文 ----
    L.append(f'# {title}')
    L.append('')

    # 基本信息表
    L += ['| 项 | 内容 |', '|---|---|']
    if authors_raw:
        a = ', '.join(authors_raw)
        L.append(f'| 作者 | {a if len(a) < 130 else a[:127] + "…"} |')
    for k, label in (('year', '年份'), ('journal', '期刊/会议')):
        if fm.get(k):
            L.append(f'| {label} | {fm[k]} |')
    if fm.get('doi'):
        L.append(f'| DOI | [{fm["doi"]}](https://doi.org/{fm["doi"]}) |')
    if fm.get('arxiv'):
        L.append(f'| arXiv | [{fm["arxiv"]}](https://arxiv.org/abs/{fm["arxiv"]}) |')
    if fm.get('pages'):
        L.append(f'| 页数 | {fm["pages"]} |')
    if fm.get('figures'):
        L.append(f'| 图数 | {fm["figures"]} |')
    L.append('')

    # LLM 摘要正文（去掉它自己的 frontmatter 和一级标题）
    body = strip_frontmatter(summary_text)
    body = re.sub(r'^#\s*📖?\s*论文摘要\s*$', '', body, flags=re.M)
    body = body.lstrip('\n')
    L.append(body.rstrip())
    L.append('')

    # 标签清单（正文里也放一份，方便阅读时不看 properties）
    L.append('## 🏷 标签')
    L.append('')
    for prefix, label in (('领域', '研究领域'), ('方法', '技术方法'),
                          ('应用', '应用场景'), ('仪器', '仪器设备')):
        items = tags.get(prefix, [])
        if items:
            L.append(f'**{label}**：' + '　'.join(f'`{t}`' for t in items))
            L.append('')

    L += ['## 📄 相关文件', '',
          '[[full|📄 打开全文]]　·　[[paper.pdf|📎 原始 PDF]]', '']
    return '\n'.join(L)


def apply_one(vault: str, entry_dir_name: str) -> bool:
    entry_dir = os.path.join(vault, '1-Papers', entry_dir_name)
    sp = os.path.join(entry_dir, 'summary.md')
    tp = os.path.join(entry_dir, 'tags.md')
    if not os.path.isfile(lp(sp)):
        print(f'  跳过（无 summary.md）: {entry_dir_name[:56]}')
        return False
    summary = io.open(lp(sp), encoding='utf-8', errors='replace').read()
    tags = {}
    if os.path.isfile(lp(tp)):
        tags = parse_tags_md(io.open(lp(tp), encoding='utf-8', errors='replace').read())

    new_index = rebuild_index(entry_dir, summary, tags)
    # 保留 make_nav.py 写入的导航块（概念/分类链接），避免重建后丢失
    idx_path = os.path.join(entry_dir, 'index.md')
    old_text = ''
    if os.path.isfile(lp(idx_path)):
        try:
            old_text = io.open(lp(idx_path), encoding='utf-8', errors='replace').read()
        except OSError:
            old_text = ''
    nav = NAV_BLOCK_RE.search(old_text)
    if nav:
        new_index = new_index.rstrip() + '\n\n' + nav.group(0) + '\n'
    io.open(lp(idx_path), 'w', encoding='utf-8').write(new_index)

    # 清理临时文件（内容已并入 index.md）
    for p in (sp, tp):
        try:
            os.remove(lp(p))
        except OSError:
            pass

    n_tags = sum(len(v) for v in tags.values())
    print(f'  ✅ {entry_dir_name[:58]}  ({n_tags} 个标签)')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--entry')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if a.entry:
        ok = apply_one(a.vault, a.entry)
        return 0 if ok else 1

    dirs = [d for d in sorted(os.listdir(lp(papers)))
            if os.path.isdir(lp(os.path.join(papers, d))) and not d.startswith('_')]
    n = 0
    for d in dirs:
        if apply_one(a.vault, d):
            n += 1
    print(f'\n✅ 合并完成：{n} 篇')
    return 0


if __name__ == '__main__':
    sys.exit(main())
