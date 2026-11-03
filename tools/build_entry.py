#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_entry — 把 MinerU 产物 + 元数据 组装成一个 Obsidian 论文条目

目录结构（每篇）：
    1-Papers/<标题≤120字符>/
        index.md        元数据(frontmatter) + 基本信息 + 摘要/标签占位
        full.md         正文（图片引用已改为 fig01.jpg 形式）
        paper.pdf       PDF 原件（固定短名）
        images/fig01.jpg ...
        .entry.json     内部清单（fig 映射、指纹、来源；点开头被 Obsidian 隐藏）

为什么图片要重命名（本机实测结论 2026-10-21）：
    MinerU 产出 64 位 sha 文件名，如 images/5d61e6b8...a.jpg（69 字符）
    vault 根 48 + 1-Papers 9 + 最长标题 168 + images 7 + 文件名 69 = 301 > 260
    → Obsidian 显示破图（图片无法加载）
    改成 fig01.jpg（10 字符）后总长 242，正常显示。
    实测：同目录下 fig01.jpg 能显示，<sha>.jpg 破图。这是纯文件名长度问题。

为什么标题截断到 120：
    48 + 9 + 121 + 7 + 10 = 195，余量 65 字符，即使 vault 换个更深的位置也安全。
    完整标题存在 frontmatter 的 title 里，显示和搜索不受影响。
"""
import io
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TITLE_MAX = 120
ILLEGAL = re.compile(r'[:*?"<>|\\/]')
IMG_REF = re.compile(r'!\[([^\]]*)\]\(images/([^)]+)\)')


def lp(p: str) -> str:
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def safe_title_dir(title: str, limit: int = TITLE_MAX) -> str:
    """把标题变成安全的目录名"""
    n = re.sub(r'<[^>]+>', '', title or '')
    n = n.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    n = ILLEGAL.sub('-', n)
    n = re.sub(r'\s+', ' ', n).strip().rstrip('. ')
    if len(n) > limit:
        cut = n[:limit]
        sp = cut.rfind(' ')
        if sp > limit * 0.6:
            cut = cut[:sp]
        n = cut.rstrip('- .,')
    return n or 'Untitled'


def yq(v) -> str:
    """YAML 字符串值转义"""
    s = str(v).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'


def unique_dir(base: str, year: str, existing: set) -> str:
    """目录名冲突时追加年份或序号"""
    if base not in existing:
        return base
    if year:
        alt = f'{base} ({year})'
        if alt not in existing:
            return alt
    i = 2
    while f'{base} ({i})' in existing:
        i += 1
    return f'{base} ({i})'


def rewrite_images(full_md: str, src_img_dir: str, dst_img_dir: str) -> tuple:
    """
    按出现顺序把图片重命名为 fig01.jpg..figNN.jpg，
    并改写 full.md 里的引用。
    返回 (新 full_md, fig 映射表, 未引用图片数)
    """
    os.makedirs(lp(dst_img_dir), exist_ok=True)

    mapping = {}          # 原文件名 -> figNN.jpg
    counter = [0]
    skipped = [0]

    def repl(m):
        alt, filename = m.group(1), m.group(2)
        base = os.path.basename(filename)
        if base in mapping:
            return f'![{alt}](images/{mapping[base]})'
        src = os.path.join(src_img_dir, base)
        if not os.path.isfile(src):
            skipped[0] += 1
            return m.group(0)
        counter[0] += 1
        ext = os.path.splitext(base)[1].lower() or '.jpg'
        newname = f'fig{counter[0]:02d}{ext}'
        try:
            shutil.copy2(lp(src), lp(os.path.join(dst_img_dir, newname)))
        except OSError as exc:
            print(f'      ⚠ 图片复制失败 {base[:16]}: {exc}')
            skipped[0] += 1
            counter[0] -= 1
            return m.group(0)
        mapping[base] = newname
        return f'![{alt}](images/{newname})'

    new_md = IMG_REF.sub(repl, full_md)

    # 未被引用的图片
    referenced = set(mapping.keys())
    unreferenced = 0
    if os.path.isdir(lp(src_img_dir)):
        for f in os.listdir(lp(src_img_dir)):
            if f not in referenced and os.path.isfile(lp(os.path.join(src_img_dir, f))):
                if os.path.splitext(f)[1].lower() in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                    unreferenced += 1

    return new_md, mapping, unreferenced


def build_index_md(meta: dict, parsed: dict, fig_count: int) -> str:
    """生成 index.md：frontmatter + 基本信息 + 待填充的摘要/标签区"""
    title = meta.get('title') or parsed.get('title') or 'Untitled'
    authors = meta.get('authors') or []
    year = str(meta.get('year') or '')
    journal = meta.get('journal') or ''
    doi = (meta.get('doi') or '').strip()
    arxiv = meta.get('arxiv_id') or ''
    needs = meta.get('source') == 'mineru-fallback'
    abstract = (meta.get('abstract') or '').strip()

    tags = []
    if needs:
        tags.append('状态/待补元数据')
    else:
        tags.append('状态/已入库')
    if doi:
        tags.append('状态/有DOI')

    L = ['---', f'title: {yq(title)}']
    if authors:
        L.append('authors:')
        L += [f'  - {yq(a)}' for a in authors]
    else:
        L.append('authors: []')
    L.append(f'year: {yq(year)}')
    if journal:
        L.append(f'journal: {yq(journal)}')
    if doi:
        L.append(f'doi: {yq(doi)}')
    if arxiv:
        L.append(f'arxiv: {yq(arxiv)}')
    L.append(f'type: {yq(meta.get("type", ""))}')
    L.append('source: "paper"')
    L.append(f'status: "{"needs_metadata" if needs else "parsed"}"')
    if 'match_score' in meta:
        L.append(f'match_score: {meta["match_score"]}')
    L.append(f'fingerprint: {yq(parsed["fingerprint"])}')
    L.append(f'pages: {parsed.get("layout_pages") or 0}')
    L.append(f'figures: {fig_count}')
    L.append(f'chars: {parsed.get("md_chars") or 0}')
    L.append('tags:')
    L += [f'  - {yq(t)}' for t in tags]
    L.append(f'added: {yq(parsed.get("parsed_at", "")[:10])}')
    L.append('---')
    L += ['', f'# {title}', '']

    if needs:
        L += ['> [!warning] 元数据未自动确认',
              '> Crossref 未匹配到可信结果，请人工核对标题/作者/年份/DOI。',
              '> 补全后把 `status` 改为 `parsed`。', '']

    # 基本信息表
    L += ['| 项 | 内容 |', '|---|---|']
    if authors:
        a = ', '.join(authors)
        L.append(f'| 作者 | {a if len(a) < 120 else a[:117] + "…"} |')
    if year:
        L.append(f'| 年份 | {year} |')
    if journal:
        L.append(f'| 期刊/会议 | {journal} |')
    if doi:
        L.append(f'| DOI | [{doi}](https://doi.org/{doi}) |')
    if arxiv:
        L.append(f'| arXiv | [{arxiv}](https://arxiv.org/abs/{arxiv}) |')
    if parsed.get('layout_pages'):
        L.append(f'| 页数 | {parsed["layout_pages"]} |')
    if fig_count:
        L.append(f'| 图数 | {fig_count} |')
    L.append('')

    if abstract:
        L += ['## 摘要', '', abstract, '']

    L += ['## 一句话总结', '', '> 待生成', '',
          '## 核心方法', '', '待生成', '',
          '## 主要结果', '', '待生成', '',
          '## 标签', '', '待生成', '',
          '## 相关论文', '', '待建立', '']

    L += ['## 全文', '',
          '[[full|📄 打开全文]]', '',
          '## 原始文件', '',
          '[[paper.pdf|📎 原始 PDF]]', '']
    return '\n'.join(L)


def build_entry(meta: dict, parsed: dict, pdf_path: str,
                vault: str, overwrite: bool = False) -> dict:
    """
    组装一个完整条目。返回结果字典。
    """
    title = meta.get('title') or parsed.get('title') or 'Untitled'
    year = str(meta.get('year') or '')

    papers_root = os.path.join(vault, '1-Papers')
    os.makedirs(lp(papers_root), exist_ok=True)
    existing = set(os.listdir(lp(papers_root))) if os.path.isdir(lp(papers_root)) else set()

    base = safe_title_dir(title)
    slug = unique_dir(base, year, existing)
    dst = os.path.join(papers_root, slug)

    if os.path.isfile(lp(os.path.join(dst, 'index.md'))) and not overwrite:
        return {'slug': slug, 'skipped': True}

    os.makedirs(lp(dst), exist_ok=True)

    # 1) 正文 + 图片
    src_dir = parsed['out_dir']
    full_src = os.path.join(src_dir, 'full.md')
    if not os.path.isfile(lp(full_src)):
        raise RuntimeError(f'缺少 full.md: {src_dir}')
    full_md = io.open(lp(full_src), encoding='utf-8', errors='replace').read()

    new_md, mapping, unref = rewrite_images(
        full_md, os.path.join(src_dir, 'images'), os.path.join(dst, 'images'))
    io.open(lp(os.path.join(dst, 'full.md')), 'w', encoding='utf-8').write(new_md)

    # 2) PDF 原件（固定短名）
    pdf_dst = os.path.join(dst, 'paper.pdf')
    if os.path.isfile(lp(pdf_path)) and not os.path.isfile(lp(pdf_dst)):
        shutil.copy2(lp(pdf_path), lp(pdf_dst))

    # 3) index.md
    fig_count = len(mapping)
    io.open(lp(os.path.join(dst, 'index.md')), 'w', encoding='utf-8').write(
        build_index_md(meta, parsed, fig_count))

    # 4) 内部清单（点开头，Obsidian 不索引）
    entry = {
        'slug': slug,
        'title': title,
        'fingerprint': parsed['fingerprint'],
        'source_pdf': os.path.abspath(pdf_path),
        'source_filename': os.path.basename(pdf_path),
        'fig_map': mapping,
        'figures': fig_count,
        'unreferenced_images': unref,
        'pages': parsed.get('layout_pages'),
        'chars': parsed.get('md_chars'),
        'meta_source': meta.get('source'),
        'doi': meta.get('doi', ''),
        'built_at': __import__('time').strftime('%Y-%m-%dT%H:%M:%S'),
    }
    io.open(lp(os.path.join(dst, '.entry.json')), 'w', encoding='utf-8').write(
        json.dumps(entry, ensure_ascii=False, indent=1))

    return {'slug': slug, 'skipped': False, 'title': title, 'year': year,
            'figures': fig_count, 'pages': parsed.get('layout_pages'),
            'doi': meta.get('doi', ''), 'unref': unref,
            'needs_meta': meta.get('source') == 'mineru-fallback'}
