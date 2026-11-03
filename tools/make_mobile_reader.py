#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_mobile_reader — 把论文库库导出成手机离线阅读版

为什么需要它：
    · 鸿蒙手机没有 Obsidian（OHSidian 只支持 2in1/平板）
    · 鸿蒙华为浏览器打不开本地 HTML（file:// 被限制）
    · 手机上最稳的是"单文件"：EPUB / DOCX / PDF，放华为云盘下载后用
      华为阅读 / WPS / 系统查看器打开

产出（同目录下三个同名文件 + 使用说明）：
    论文库文库-手机版.epub   手机阅读器（华为阅读等），可重排、有目录
    论文库文库-手机版.docx   WPS 打开，可重排、可搜索
    论文库文库-手机版.pdf    最通用的兜底（由 docx 用 LibreOffice 转出）

支持两种库格式：
    新格式：1-Papers/<标题>/index.md（frontmatter + 分节摘要）
    旧格式：1-Papers/<标题>/meta.yaml + summary.md + tags.md

常用：
    python tools/make_mobile_reader.py --vault <库> --out cache/mobile
    python tools/make_mobile_reader.py --vault <库> --out cache/mobile --format epub,docx,pdf
    python tools/make_mobile_reader.py --vault <库> --out cache/mobile --fulltext   # 带正文
"""
import argparse
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ---------------------------------------------------------------- 基础工具

def lp(p):
    """Windows 长路径前缀"""
    if os.name != 'nt':
        return p
    p = os.path.abspath(p)
    if p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + p


def read_text(path):
    """utf-8 / gb18030 兜底（先 strict，最后才 replace）"""
    for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            with io.open(lp(path), encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return ''
    try:
        with io.open(lp(path), encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)


def parse_frontmatter(text):
    """极简 YAML frontmatter（本项目的标量/列表）"""
    m = FM_RE.match(text)
    if not m:
        return {}
    out, key = {}, None
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


def unquote(v):
    return str(v).strip().strip('"').strip("'")


def parse_meta_yaml(text):
    """旧格式 meta.yaml（只有本项目用到的标量/列表）"""
    out, key = {}, None
    for line in text.split('\n'):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if re.match(r'^\s*-\s+', line) and key:
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(unquote(re.sub(r'^\s*-\s+', '', line)))
            continue
        mm = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if mm:
            key = mm.group(1)
            val = mm.group(2).strip()
            out[key] = val if val else ''
    return out


def strip_md_title(text):
    """去掉 markdown 里的标题行，返回 (title, body)"""
    lines = text.split('\n')
    for i, line in enumerate(lines):
        m = re.match(r'^#\s+(.*)$', line.strip())
        if m:
            return m.group(1).strip(), '\n'.join(lines[i + 1:])
    return '', text


# ---------------------------------------------------------------- markdown → blocks

MATH_SYMBOLS = {
    r'\\alpha': 'α', r'\\beta': 'β', r'\\gamma': 'γ', r'\\delta': 'δ',
    r'\\epsilon': 'ε', r'\\varepsilon': 'ε', r'\\lambda': 'λ', r'\\mu': 'μ',
    r'\\nu': 'ν', r'\\pi': 'π', r'\\sigma': 'σ', r'\\tau': 'τ', r'\\phi': 'φ',
    r'\\Phi': 'Φ', r'\\Delta': 'Δ', r'\\Omega': 'Ω', r'\\omega': 'ω',
    r'\\times': '×', r'\\pm': '±', r'\\sim': '~', r'\\approx': '≈',
    r'\\le': '≤', r'\\leq': '≤', r'\\ge': '≥', r'\\geq': '≥',
    r'\\rightarrow': '→', r'\\to': '→', r'\\propto': '∝', r'\\cdot': '·',
    r'\\infty': '∞', r'\\prime': '′', r'\\degree': '°', r'\\%': '%',
    r'\\,': ' ', r'\\;': ' ', r'\\ ': ' ', r'\\!': '',
    r'\\mathrm': '', r'\\text': '', r'\\rm': '', r'\\left': '', r'\\right': '',
}


def simplify_math(s):
    t = s.replace('\\\\', '\\')
    for k, v in sorted(MATH_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        t = t.replace(k, v)
    t = t.replace('\\_', '_').replace('\\^', '^')
    t = re.sub(r'\\[{}]', '', t)
    t = t.replace('{', '').replace('}', '')
    t = t.replace('$', '')
    return t.strip()


def split_table_row(line):
    line = line.strip().strip('|')
    cells, cur, esc = [], '', False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == '\\':
            esc = True
            cur += ch
        elif ch == '|':
            cells.append(cur.strip())
            cur = ''
        else:
            cur += ch
    cells.append(cur.strip())
    return [c.replace('\\|', '|') for c in cells]


IMAGE_LINE_RE = re.compile(r'^!\[([^\]]*)\]\(([^)]+)\)\s*$')


def parse_blocks(md):
    """markdown → 结构化块：h / p / ul / ol / quote / table / hr / code / img"""
    lines = md.replace('\r\n', '\n').split('\n')
    blocks, i = [], 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s.startswith('```'):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append({'t': 'code', 'text': '\n'.join(buf)})
            continue
        m_img = IMAGE_LINE_RE.match(s)
        if m_img:
            blocks.append({'t': 'img', 'alt': m_img.group(1), 'src': m_img.group(2)})
            i += 1
            continue
        m = re.match(r'^(#{1,6})\s+(.*)$', s)
        if m:
            blocks.append({'t': 'h', 'level': len(m.group(1)),
                           'text': m.group(2).strip()})
            i += 1
            continue
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', s):
            blocks.append({'t': 'hr'})
            i += 1
            continue
        if s.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = lines[i].strip()
                if re.match(r'^\|?[\s:\-|]+\|?$', row) and '-' in row:
                    i += 1
                    continue
                rows.append(split_table_row(row))
                i += 1
            if rows:
                blocks.append({'t': 'table', 'rows': rows})
            continue
        if s.startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            blocks.append({'t': 'quote', 'text': ' '.join(buf)})
            continue
        if re.match(r'^[-*+]\s+', s):
            items = []
            while i < len(lines):
                ss = lines[i].strip()
                mm = re.match(r'^[-*+]\s+(.*)$', ss)
                if mm:
                    items.append(mm.group(1))
                    i += 1
                elif ss and items and not re.match(r'^(\d+[.)]\s+|#{1,6}\s+|\||>)', ss):
                    items[-1] += ' ' + ss
                    i += 1
                else:
                    break
            blocks.append({'t': 'ul', 'items': items})
            continue
        if re.match(r'^\d+[.)]\s+', s):
            items = []
            while i < len(lines):
                ss = lines[i].strip()
                mm = re.match(r'^\d+[.)]\s+(.*)$', ss)
                if mm:
                    items.append(mm.group(1))
                    i += 1
                elif ss and items and not re.match(r'^([-*+]\s+|#{1,6}\s+|\||>)', ss):
                    items[-1] += ' ' + ss
                    i += 1
                else:
                    break
            blocks.append({'t': 'ol', 'items': items})
            continue
        # 段落
        buf = [s]
        i += 1
        while i < len(lines):
            ss = lines[i].strip()
            if (not ss or ss.startswith('#') or ss.startswith('|') or
                    re.match(r'^([-*+]\s+|\d+[.)]\s+|>|```)', ss) or
                    IMAGE_LINE_RE.match(ss)):
                break
            buf.append(ss)
            i += 1
        blocks.append({'t': 'p', 'text': ' '.join(buf)})
    return blocks


INLINE_RE = re.compile(
    r'(\*\*.+?\*\*|__.+?__|\*[^*\n]+?\*|_[^_\n]+?_|`[^`\n]+?`|'
    r'\[\[[^\]\n]+?\]\]|\[[^\]\n]+?\]\([^)\n]+?\)|\$[^$\n]+?\$)')


def inline_segments(s):
    """把一行拆成 [(kind, text, extra)]，kind: text/bold/italic/code/link/wikilink/math"""
    out, pos = [], 0
    for m in INLINE_RE.finditer(s):
        if m.start() > pos:
            out.append(('text', s[pos:m.start()], None))
        tok = m.group(0)
        if tok.startswith('**') or tok.startswith('__'):
            out.append(('bold', tok[2:-2], None))
        elif tok.startswith('`'):
            out.append(('code', tok[1:-1], None))
        elif tok.startswith('[['):
            out.append(('wikilink', tok[2:-2], None))
        elif tok.startswith('['):
            mm = re.match(r'\[([^\]]+)\]\(([^)]+)\)', tok)
            if mm:
                out.append(('link', mm.group(1), mm.group(2)))
            else:
                out.append(('text', tok, None))
        elif tok.startswith('$'):
            out.append(('math', simplify_math(tok[1:-1]), None))
        elif tok.startswith('*') or tok.startswith('_'):
            out.append(('italic', tok[1:-1], None))
        else:
            out.append(('text', tok, None))
        pos = m.end()
    if pos < len(s):
        out.append(('text', s[pos:], None))
    return out


def inline_html(s):
    parts = []
    for kind, text, extra in inline_segments(s):
        t = html.escape(text)
        if kind == 'bold':
            parts.append('<strong>%s</strong>' % t)
        elif kind == 'italic':
            parts.append('<em>%s</em>' % t)
        elif kind == 'code':
            parts.append('<code>%s</code>' % t)
        elif kind == 'math':
            parts.append('<span class="math">%s</span>' % t)
        elif kind == 'wikilink':
            parts.append('<span class="wikilink">%s</span>' % t)
        elif kind == 'link':
            if re.match(r'^(https?|mailto):', extra or ''):
                parts.append('<a href="%s">%s</a>' % (html.escape(extra), t))
            else:
                parts.append(t)
        else:
            parts.append(t)
    return ''.join(parts)


# ---------------------------------------------------------------- 解析库

class Entry:
    def __init__(self):
        self.slug = ''
        self.dir = ''
        self.kind = 'new'
        self.title = ''
        self.title_en = ''
        self.authors = []
        self.year = ''
        self.journal = ''
        self.doi = ''
        self.arxiv = ''
        self.pages = ''
        self.abstract = ''       # 一句话总结
        self.tags = []           # [(分组, 词)]
        self.sections = []       # [(标题, [blocks])]
        self.fulltext = []       # [blocks]
        self.images = {}         # 文件名 -> 绝对路径 (仅 fulltext 有图时)


def parse_new_entry(path):
    e = Entry()
    e.kind = 'new'
    e.dir = path
    e.slug = os.path.basename(path.rstrip('\\/'))
    idx = os.path.join(path, 'index.md')
    text = read_text(idx)
    fm = parse_frontmatter(text)
    body = FM_RE.sub('', text, count=1)
    blocks = parse_blocks(body)
    # 去掉正文开头的 H1 与信息表
    start = 0
    while start < len(blocks):
        b = blocks[start]
        if b['t'] == 'h' and b['level'] == 1:
            start += 1
            continue
        if b['t'] == 'table' and start < 4:
            start += 1
            continue
        break
    blocks = blocks[start:]
    e.title = unquote(fm.get('title') or '') or e.slug
    e.title_en = unquote(fm.get('title_en') or '')
    e.authors = [unquote(a) for a in (fm.get('authors') or [])]
    e.year = unquote(fm.get('year') or '')
    e.journal = unquote(fm.get('journal') or '')
    e.doi = unquote(fm.get('doi') or '')
    e.arxiv = unquote(fm.get('arxiv') or '')
    e.pages = unquote(fm.get('pages') or '')
    e.tags = [('', unquote(t)) for t in (fm.get('tags') or [])]
    e.sections, e.abstract = split_sections(blocks)
    return e


def parse_old_entry(path):
    e = Entry()
    e.kind = 'old'
    e.dir = path
    e.slug = os.path.basename(path.rstrip('\\/'))
    meta_p = os.path.join(path, 'meta.yaml')
    sum_p = os.path.join(path, 'summary.md')
    tags_p = os.path.join(path, 'tags.md')
    meta = parse_meta_yaml(read_text(meta_p)) if os.path.isfile(lp(meta_p)) else {}
    e.title = unquote(meta.get('title') or '') or e.slug
    e.title_en = unquote(meta.get('title_en') or '')
    e.authors = [unquote(a) for a in (meta.get('authors') or [])]
    e.year = unquote(meta.get('year') or '')
    e.journal = unquote(meta.get('journal') or '')
    e.doi = unquote(meta.get('doi') or '')
    e.arxiv = unquote(meta.get('arxiv') or '')
    e.pages = unquote(meta.get('pages') or '')
    # summary.md → blocks
    sum_text = read_text(sum_p)
    body = re.sub(r'^#\s+.*$', '', sum_text, count=1, flags=re.M) if sum_text else ''
    blocks = parse_blocks(body)
    e.sections, e.abstract = split_sections(blocks)
    # tags.md → [(组, 词)]
    if os.path.isfile(lp(tags_p)):
        group = ''
        for line in read_text(tags_p).split('\n'):
            s = line.strip()
            if not s:
                continue
            if s.startswith('#'):
                group = s.lstrip('#').strip()
                continue
            if re.match(r'^[-*+]\s+', s):
                e.tags.append((group, re.sub(r'^[-*+]\s+', '', s).strip()))
            elif s.endswith('：') or s.endswith(':'):
                group = s.rstrip('：:').strip()
    # keywords 兜底
    if not e.tags:
        e.tags = [('关键词', unquote(k)) for k in (meta.get('keywords') or [])]
    return e


def split_sections(blocks):
    """按 H2 分组；一句话总结单独抽出来"""
    sections, abstract = [], ''
    cur_title, cur = None, []
    for b in blocks:
        if b['t'] == 'h' and b['level'] == 2:
            if cur_title is not None:
                sections.append((cur_title, cur))
            cur_title, cur = b['text'], []
            continue
        if cur_title is None:
            continue
        cur.append(b)
    if cur_title is not None:
        sections.append((cur_title, cur))
    # 抽一句话总结
    out = []
    for title, blks in sections:
        if '一句话总结' in title:
            texts = [b.get('text', '') for b in blks if b['t'] in ('p', 'quote') and b.get('text')]
            if texts:
                abstract = texts[0]
            continue
        out.append((title, blks))
    return out, abstract


def load_entries(vault, limit=0):
    papers_dir = os.path.join(vault, '1-Papers')
    if not os.path.isdir(lp(papers_dir)):
        raise SystemExit('找不到 1-Papers 目录：%s' % papers_dir)
    entries = []
    for name in sorted(os.listdir(lp(papers_dir))):
        if name.startswith(('.', '_')):
            continue
        path = os.path.join(papers_dir, name)
        if not os.path.isdir(lp(path)):
            continue
        if os.path.isfile(lp(os.path.join(path, 'index.md'))):
            e = parse_new_entry(path)
        elif os.path.isfile(lp(os.path.join(path, 'summary.md'))):
            e = parse_old_entry(path)
        else:
            continue
        if e.title:
            entries.append(e)
        if limit and len(entries) >= limit:
            break
    entries.sort(key=lambda x: (-(int(re.sub(r'\D', '', x.year) or 0)), x.title.lower()))
    return entries


def load_misc_pages(vault, include_concepts=True):
    """概念 / 笔记 / 项目（跳过旧式"一篇论文一页"的概念页）"""
    out = []
    for sub, label in (('2-Concepts', '概念'), ('4-Notes', '笔记'), ('5-Projects', '项目')):
        if sub == '2-Concepts' and not include_concepts:
            continue
        d = os.path.join(vault, sub)
        if not os.path.isdir(lp(d)):
            continue
        for name in sorted(os.listdir(lp(d))):
            if not name.endswith('.md') or name.startswith(('.', '_')):
                continue
            p = os.path.join(d, name)
            text = read_text(p)
            fm = parse_frontmatter(text)
            if sub == '2-Concepts' and (fm.get('paper') or not fm):
                continue   # 旧式：每篇论文一个概念页，跳过
            body = FM_RE.sub('', text, count=1) if fm else text
            title, body = strip_md_title(body)
            title = unquote(fm.get('title') or '') or title or name[:-3]
            out.append({'label': label, 'title': title, 'blocks': parse_blocks(body)})
    return out


# ---------------------------------------------------------------- EPUB

CSS = """
body { margin: 0; padding: 0.4em 0.5em; font-family: "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", serif;
       line-height: 1.75; color: #222; font-size: 1em; }
h1 { font-size: 1.5em; line-height: 1.3; margin: 0.6em 0 0.3em; }
h2 { font-size: 1.2em; margin: 1.2em 0 0.4em; border-left: 0.35em solid #3b6ea5; padding-left: 0.5em; }
h3 { font-size: 1.05em; margin: 1em 0 0.3em; color: #3b6ea5; }
p { margin: 0.35em 0; text-align: justify; }
.meta { color: #666; font-size: 0.88em; line-height: 1.6; }
.tags { margin: 0.4em 0 0.8em; }
.tag { display: inline-block; background: #eef3f9; color: #3b6ea5; border-radius: 0.2em;
       padding: 0.05em 0.4em; margin: 0.15em 0.2em 0.15em 0; font-size: 0.8em; }
.lead { border-left: 0.3em solid #d8a13a; background: #fdf8ee; padding: 0.5em 0.7em;
        margin: 0.6em 0 1em; font-size: 0.98em; }
.quote { color: #555; border-left: 0.2em solid #ccc; padding-left: 0.6em; }
table { border-collapse: collapse; width: 100%; margin: 0.6em 0; font-size: 0.85em; }
td, th { border: 1px solid #ccc; padding: 0.2em 0.35em; text-align: left; vertical-align: top; }
th { background: #f0f3f7; }
img { max-width: 100%; height: auto; }
hr { border: none; border-top: 1px solid #ddd; margin: 1em 0; }
.cover { text-align: center; padding-top: 25%; }
.cover h1 { font-size: 2.2em; border: none; }
.toc-list { list-style: none; padding-left: 0; }
.toc-list li { margin: 0.3em 0; }
.small { color: #888; font-size: 0.82em; }
"""


def blocks_to_html(blocks, img_map=None):
    out = []
    for b in blocks:
        t = b['t']
        if t == 'h':
            lv = min(max(b['level'], 2), 4)
            out.append('<h%d>%s</h%d>' % (lv, inline_html(b['text']), lv))
        elif t == 'p':
            out.append('<p>%s</p>' % inline_html(b['text']))
        elif t == 'quote':
            out.append('<blockquote class="quote"><p>%s</p></blockquote>' % inline_html(b['text']))
        elif t == 'ul':
            out.append('<ul>%s</ul>' % ''.join('<li>%s</li>' % inline_html(x) for x in b['items']))
        elif t == 'ol':
            out.append('<ol>%s</ol>' % ''.join('<li>%s</li>' % inline_html(x) for x in b['items']))
        elif t == 'table':
            rows = b['rows']
            h = ['<table>']
            for ri, row in enumerate(rows):
                tag = 'th' if ri == 0 else 'td'
                h.append('<tr>%s</tr>' % ''.join('<%s>%s</%s>' % (tag, inline_html(c), tag) for c in row))
            h.append('</table>')
            out.append(''.join(h))
        elif t == 'hr':
            out.append('<hr/>')
        elif t == 'code':
            out.append('<pre><code>%s</code></pre>' % html.escape(b['text']))
        elif t == 'img':
            src = b.get('src', '')
            if img_map and src in img_map:
                out.append('<div class="fig"><img src="../%s" alt="%s"/></div>'
                           % (html.escape(img_map[src]), html.escape(b.get('alt') or '')))
            else:
                out.append('<p class="small">[图] %s</p>' % html.escape(b.get('alt') or ''))
    return '\n'.join(out)


def join_authors(authors, n=8):
    if not authors:
        return ''
    sep = '、' if any(re.search(r'[\u4e00-\u9fff]', a) for a in authors) else ', '
    head = sep.join(authors[:n])
    if len(authors) > n:
        head += ' 等 %d 人' % len(authors)
    return head


def paper_html(e, idx, with_fulltext=False, img_map=None):
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<!DOCTYPE html>',
             '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">',
             '<head><title>%s</title><link rel="stylesheet" type="text/css" href="../style.css"/></head><body>' % html.escape(e.title),
             '<h1>%s</h1>' % html.escape(e.title)]
    if e.title_en:
        parts.append('<p class="meta">%s</p>' % html.escape(e.title_en))
    meta = []
    if e.authors:
        meta.append('作者：' + join_authors(e.authors))
    if e.year:
        meta.append('年份：' + e.year)
    if e.journal:
        meta.append('期刊：' + e.journal)
    if e.doi:
        meta.append('DOI：' + e.doi)
    if e.arxiv:
        meta.append('arXiv：' + e.arxiv)
    if e.pages:
        meta.append('页数：' + e.pages)
    if meta:
        parts.append('<p class="meta">%s</p>' % html.escape(' · '.join(meta)))
    if e.tags:
        parts.append('<div class="tags">%s</div>' % ''.join(
            '<span class="tag">%s</span>' % html.escape((g + '/' if g else '') + t) for g, t in e.tags))
    if e.abstract:
        parts.append('<blockquote class="lead"><p>%s</p></blockquote>' % inline_html(e.abstract))
    for title, blks in e.sections:
        parts.append('<h2>%s</h2>' % html.escape(title))
        parts.append(blocks_to_html(blks))
    if with_fulltext and e.fulltext:
        parts.append('<h2>正文</h2>')
        parts.append(blocks_to_html(e.fulltext, img_map))
    parts.append('<hr/><p class="small">库内路径：1-Papers/%s</p>' % html.escape(e.slug))
    parts.append('</body></html>')
    return '\n'.join(parts)


IMG_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
             '.gif': 'image/gif', '.svg': 'image/svg+xml', '.webp': 'image/webp',
             '.bmp': 'image/bmp'}


def build_epub(entries, misc, out_path, title, with_fulltext=False):
    uid = 'urn:uuid:' + str(uuid.uuid4())
    now = datetime.now().strftime('%Y-%m-%d')
    years = {}
    for e in entries:
        years.setdefault(e.year or '未知', []).append(e)

    files = {}   # zip 内路径 -> bytes
    files['mimetype'] = b'application/epub+zip'
    files['META-INF/container.xml'] = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>').encode('utf-8')
    files['OEBPS/style.css'] = CSS.encode('utf-8')

    manifest, spine = [], []
    def add(id_, href, data):
        files['OEBPS/' + href] = data.encode('utf-8')
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (id_, href))
        spine.append('<itemref idref="%s"/>' % id_)

    # 封面/总览
    years_count = '、'.join('%s 年 %d 篇' % (y, len(v)) for y, v in sorted(years.items(), key=lambda kv: kv[0], reverse=True))
    cover = ['<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml"><head>'
             '<title>%s</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
             '<div class="cover"><h1>%s</h1><p>手机离线阅读版</p><p class="small">%s 篇论文 · 生成于 %s</p></div>'
             '<h2>说明</h2><p>这是论文库库的只读快照，方便在手机上浏览摘要与要点。'
             '完整正文、图片和双链请在电脑上的 Obsidian 中查看。</p>'
             '<p class="small">%s</p>'
             '<h2>年份分布</h2><p>%s</p></body></html>'
             % (html.escape(title), html.escape(title), len(entries), now,
                html.escape(years_count), html.escape(years_count))]
    add('cover', 'cover.xhtml', '\n'.join(cover))

    # 标签索引
    tag_count = {}
    for e in entries:
        for g, t in e.tags:
            key = (g + '/' if g else '') + t
            tag_count[key] = tag_count.get(key, 0) + 1
    tag_items = ''.join('<li>%s <span class="small">（%d）</span></li>' % (html.escape(k), v)
                        for k, v in sorted(tag_count.items(), key=lambda kv: (-kv[1], kv[0])))
    tag_page = ('<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                '<head><title>标签索引</title><link rel="stylesheet" type="text/css" href="style.css"/></head>'
                '<body><h1>标签索引</h1><p class="small">共 %d 个标签</p><ul class="toc-list">%s</ul></body></html>'
                % (len(tag_count), tag_items))
    add('tags', 'tags.xhtml', tag_page)

    nav_items = ['<li><a href="cover.xhtml">%s</a></li>' % html.escape(title)]
    # 每篇论文
    paper_files = []
    for i, e in enumerate(entries):
        href = 'papers/p%04d.xhtml' % (i + 1)
        img_map = {}
        if with_fulltext and e.fulltext:
            nimg = 0
            for b in e.fulltext:
                if b['t'] != 'img':
                    continue
                src = b.get('src', '')
                if not src or src in img_map:
                    continue
                p = os.path.join(e.dir, src.replace('/', os.sep))
                if not os.path.isfile(lp(p)):
                    continue
                ext = os.path.splitext(p)[1].lower()
                if ext not in IMG_TYPES:
                    continue
                nimg += 1
                rel = 'images/p%04d_i%02d%s' % (i + 1, nimg, ext)
                with io.open(lp(p), 'rb') as f:
                    files['OEBPS/' + rel] = f.read()
                manifest.append('<item id="img%04d_%02d" href="%s" media-type="%s"/>'
                                % (i + 1, nimg, rel, IMG_TYPES[ext]))
                img_map[src] = rel
        add('p%04d' % (i + 1), href, paper_html(e, i, with_fulltext, img_map))
        paper_files.append((e, href))
    # 导航：按年份分组
    group_html = []
    pi = 0
    for y in sorted(years.keys(), key=lambda x: (-(int(re.sub(r'\D', '', x) or 0)), x), reverse=False):
        pass
    for y in sorted(years.keys(), key=lambda x: (-(int(re.sub(r'\D', '', x) or 0)), x.lower()), reverse=False):
        pass
    # 按 entries 顺序分组（entries 已按年份倒序）
    nav_year = []
    cur_year = None
    for i, (e, href) in enumerate(paper_files):
        y = e.year or '未知'
        if y != cur_year:
            if cur_year is not None:
                nav_year.append('</ol></li>')
            nav_year.append('<li><span>%s 年（%d 篇）</span><ol>' % (html.escape(y), len(years[y])))
            cur_year = y
        nav_year.append('<li><a href="%s">%s</a></li>' % (href, html.escape(e.title)))
    if cur_year is not None:
        nav_year.append('</ol></li>')
    nav_items += nav_year
    nav_items.append('<li><a href="tags.xhtml">标签索引</a></li>')
    # 概念/笔记/项目
    if misc:
        for k, m in enumerate(misc):
            href = 'misc/m%04d.xhtml' % (k + 1)
            body = ['<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">',
                    '<head><title>%s</title><link rel="stylesheet" type="text/css" href="../style.css"/></head><body>' % html.escape(m['title']),
                    '<h1>%s</h1>' % html.escape(m['title']),
                    blocks_to_html(m['blocks']),
                    '</body></html>']
            add('m%04d' % (k + 1), href, '\n'.join(body))
            nav_items.append('<li><a href="%s">%s：%s</a></li>' % (href, m['label'], html.escape(m['title'])))
    nav = ('<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title>'
           '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
           '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>%s</ol></nav></body></html>' % ''.join(nav_items))
    files['OEBPS/nav.xhtml'] = nav.encode('utf-8')

    opf = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">',
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
           '<dc:identifier id="bookid">%s</dc:identifier>' % uid,
           '<dc:title>%s</dc:title>' % html.escape(title),
           '<dc:language>zh-CN</dc:language>',
           '<dc:creator>论文库</dc:creator>',
           '<meta property="dcterms:modified">%sT00:00:00Z</meta>' % now,
           '</metadata>',
           '<manifest>',
           '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
           '<item id="css" href="style.css" media-type="text/css"/>']
    opf += manifest
    opf.append('</manifest><spine>')
    opf += spine
    opf.append('</spine></package>')
    files['OEBPS/content.opf'] = '\n'.join(opf).encode('utf-8')

    os.makedirs(lp(os.path.dirname(out_path)), exist_ok=True)
    tmp = out_path + '.tmp'
    with zipfile.ZipFile(lp(tmp), 'w') as z:
        # mimetype 必须第一个且不压缩
        z.writestr(zipfile.ZipInfo('mimetype'), files['mimetype'], compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            if name == 'mimetype':
                continue
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    if os.path.exists(lp(out_path)):
        os.remove(lp(out_path))
    os.replace(lp(tmp), lp(out_path))
    return len(files)


# ---------------------------------------------------------------- DOCX

def set_cjk_font(style, name='微软雅黑'):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    style.font.name = name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = OxmlElement('w:rFonts')
        rpr.append(rfonts)
    rfonts.set(qn('w:eastAsia'), name)
    rfonts.set(qn('w:ascii'), name)
    rfonts.set(qn('w:hAnsi'), name)


def docx_inline(par, text):
    """把 inline markdown 写进段落（粗体/斜体/代码）"""
    from docx.shared import Pt
    for kind, t, extra in inline_segments(text):
        run = par.add_run(t)
        if kind == 'bold':
            run.bold = True
        elif kind == 'italic':
            run.italic = True
        elif kind == 'code':
            run.font.name = 'Consolas'
            run.font.size = Pt(9)
        elif kind == 'math':
            run.italic = True


def docx_blocks(doc, blocks, content_width_cm, image_base=None):
    from docx.shared import Cm, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    for b in blocks:
        t = b['t']
        if t == 'h':
            lv = min(b['level'], 4)
            doc.add_heading(b['text'], level=max(lv, 1))
        elif t == 'p':
            par = doc.add_paragraph()
            docx_inline(par, b['text'])
        elif t == 'quote':
            par = doc.add_paragraph()
            par.paragraph_format.left_indent = Cm(0.4)
            docx_inline(par, b['text'])
            for r in par.runs:
                r.italic = True
        elif t == 'ul':
            for item in b['items']:
                par = doc.add_paragraph(style='List Bullet')
                docx_inline(par, item)
        elif t == 'ol':
            for i, item in enumerate(b['items'], 1):
                par = doc.add_paragraph()
                par.paragraph_format.left_indent = Cm(0.5)
                par.paragraph_format.first_line_indent = Cm(-0.5)
                par.add_run('%d. ' % i)
                docx_inline(par, item)
        elif t == 'table':
            rows = b['rows']
            if not rows:
                continue
            ncol = max(len(r) for r in rows)
            table = doc.add_table(rows=len(rows), cols=ncol)
            table.style = 'Table Grid'
            for ri, row in enumerate(rows):
                for ci in range(ncol):
                    cell = table.cell(ri, ci)
                    cell.text = ''
                    par = cell.paragraphs[0]
                    docx_inline(par, row[ci] if ci < len(row) else '')
                    if ri == 0:
                        for r in par.runs:
                            r.bold = True
                    for r in par.runs:
                        r.font.size = Pt(9)
        elif t == 'hr':
            doc.add_paragraph('————————————')
        elif t == 'code':
            par = doc.add_paragraph()
            run = par.add_run(b['text'])
            run.font.name = 'Consolas'
            run.font.size = Pt(8.5)
        elif t == 'img':
            if image_base:
                path = os.path.join(image_base, b['src'].replace('/', os.sep))
                if os.path.isfile(lp(path)):
                    try:
                        doc.add_picture(lp(path), width=Cm(content_width_cm))
                        if b.get('alt'):
                            cap = doc.add_paragraph(b['alt'])
                            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            for r in cap.runs:
                                r.italic = True
                                r.font.size = Pt(8)
                    except Exception:
                        pass


def add_page_number_footer(section):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    footer = section.footer
    par = footer.paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = par.add_run()
    for tag, attr in (('w:fldChar', {'w:fldCharType': 'begin'}),
                      ('w:instrText', None),
                      ('w:fldChar', {'w:fldCharType': 'end'})):
        el = OxmlElement(tag)
        if tag == 'w:instrText':
            el.set(qn('xml:space'), 'preserve')
            el.text = 'PAGE'
        else:
            for k, v in attr.items():
                el.set(qn(k), v)
        run._r.append(el)


def build_docx(entries, misc, out_path, title, with_fulltext=False, paper='mobile'):
    from docx import Document
    from docx.shared import Mm, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.enum.section import WD_ORIENT

    doc = Document()
    # 页面尺寸：mobile 版按手机屏宽比例
    if paper == 'mobile':
        page_w, page_h = Mm(82), Mm(170)
        margin = Mm(6)
    elif paper == 'a5':
        page_w, page_h = Mm(148), Mm(210)
        margin = Mm(14)
    else:
        page_w, page_h = Mm(210), Mm(297)
        margin = Mm(20)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = page_w, page_h
    sec.top_margin = sec.bottom_margin = margin
    sec.left_margin = sec.right_margin = margin
    content_width_cm = (page_w.mm - 2 * margin.mm) / 10.0

    # 全局字体
    normal = doc.styles['Normal']
    normal.font.size = Pt(10.5 if paper == 'mobile' else 11)
    normal.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    set_cjk_font(normal)
    normal.paragraph_format.line_spacing = 1.35
    normal.paragraph_format.space_after = Pt(2)
    for name, size in (('Heading 1', 15), ('Heading 2', 12.5), ('Heading 3', 11)):
        try:
            st = doc.styles[name]
            st.font.size = Pt(size)
            st.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
            set_cjk_font(st)
        except KeyError:
            pass
    add_page_number_footer(sec)

    # 封面
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(120)
    r = p.add_run(title)
    r.font.size = Pt(24)
    r.bold = True
    r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    set_cjk_font(p.style)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run('手机离线阅读版')
    r2.font.size = Pt(12)
    r2.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r3 = p3.add_run('%d 篇论文 · %s' % (len(entries), datetime.now().strftime('%Y-%m-%d')))
    r3.font.size = Pt(10)
    r3.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    doc.add_page_break()

    # 目录
    doc.add_heading('目录', level=1)
    years = {}
    for e in entries:
        years.setdefault(e.year or '未知', []).append(e)
    for y in sorted(years.keys(), key=lambda x: -int(re.sub(r'\D', '', x) or 0)):
        doc.add_heading('%s 年（%d 篇）' % (y, len(years[y])), level=2)
        for e in years[y]:
            par = doc.add_paragraph(e.title, style='List Bullet')
            for r in par.runs:
                r.font.size = Pt(9.5)
    doc.add_page_break()

    # 正文
    for y in sorted(years.keys(), key=lambda x: -int(re.sub(r'\D', '', x) or 0)):
        doc.add_heading('%s 年' % y, level=1)
        for e in years[y]:
            doc.add_heading(e.title, level=2)
            if e.title_en:
                par = doc.add_paragraph(e.title_en)
                for r in par.runs:
                    r.italic = True
                    r.font.size = Pt(9)
                    r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            meta = []
            if e.authors:
                meta.append('作者：' + join_authors(e.authors))
            if e.year:
                meta.append('年份：' + e.year)
            if e.journal:
                meta.append('期刊：' + e.journal)
            if e.doi:
                meta.append('DOI：' + e.doi)
            if e.arxiv:
                meta.append('arXiv：' + e.arxiv)
            if meta:
                par = doc.add_paragraph(' · '.join(meta))
                for r in par.runs:
                    r.font.size = Pt(8.5)
                    r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            if e.tags:
                par = doc.add_paragraph('标签：' + '　'.join((g + '/' if g else '') + t for g, t in e.tags))
                for r in par.runs:
                    r.font.size = Pt(8.5)
                    r.font.color.rgb = RGBColor(0x3B, 0x6E, 0xA5)
            if e.abstract:
                par = doc.add_paragraph()
                par.paragraph_format.left_indent = Cm(0.35)
                r = par.add_run(e.abstract)
                r.font.size = Pt(10)
                r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
            for stitle, blks in e.sections:
                doc.add_heading(stitle, level=3)
                docx_blocks(doc, blks, content_width_cm, image_base=e.dir if with_fulltext else None)
            if with_fulltext and e.fulltext:
                doc.add_heading('正文', level=3)
                docx_blocks(doc, e.fulltext, content_width_cm, image_base=e.dir)
            par = doc.add_paragraph('库内路径：1-Papers/' + e.slug)
            for r in par.runs:
                r.font.size = Pt(7.5)
                r.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
    # 概念/笔记/项目
    if misc:
        doc.add_page_break()
        doc.add_heading('概念 · 笔记 · 项目', level=1)
        for m in misc:
            doc.add_heading('%s：%s' % (m['label'], m['title']), level=2)
            docx_blocks(doc, m['blocks'], content_width_cm)

    doc.save(lp(out_path))
    return sec


# ---------------------------------------------------------------- PDF

def find_soffice():
    cands = [r'C:\Program Files\LibreOffice\program\soffice.exe',
             r'C:\Program Files (x86)\LibreOffice\program\soffice.exe']
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which('soffice')


def docx_to_pdf(docx_path, out_dir):
    soffice = find_soffice()
    if not soffice:
        print('  ! 未找到 LibreOffice，跳过 PDF')
        return None
    profile = os.path.join(tempfile.gettempdir(), 'paperdepot_lo_profile')
    os.makedirs(profile, exist_ok=True)
    profile_url = 'file:///' + os.path.abspath(profile).replace('\\', '/').lstrip('/')
    cmd = [soffice, '--headless', '--norestore',
           '-env:UserInstallation=' + profile_url,
           '--convert-to', 'pdf:writer_pdf_Export',
           '--outdir', out_dir, docx_path]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    except subprocess.CalledProcessError as ex:
        print('  ! PDF 转换失败：', ex.stdout.decode('utf-8', 'replace')[-500:])
        return None
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + '.pdf')
    return pdf if os.path.isfile(pdf) else None


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description='论文库库 → 手机离线阅读版')
    ap.add_argument('--vault', default=None, help='Obsidian 库根目录（省略时读 config/paperdepot.local.json）')
    ap.add_argument('--out', default='cache/mobile', help='输出目录')
    ap.add_argument('--title', default='论文库文库', help='书名')
    ap.add_argument('--format', default='epub,docx,pdf', help='epub,docx,pdf')
    ap.add_argument('--paper', default='mobile', choices=['mobile', 'a5', 'a4'])
    ap.add_argument('--fulltext', action='store_true', help='附带 full.md 正文（体积大）')
    ap.add_argument('--limit', type=int, default=0, help='只导出前 N 篇（调试）')
    ap.add_argument('--include-misc', action='store_true', default=True,
                    help='包含 2-Concepts/4-Notes/5-Projects（默认开）')
    args = ap.parse_args()

    if not args.vault:
        cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'config', 'paperdepot.local.json')
        try:
            with io.open(cfg, encoding='utf-8') as f:
                args.vault = json.load(f).get('vault') or ''
        except (OSError, ValueError):
            args.vault = ''
    if not args.vault:
        raise SystemExit('需要 --vault，或先配置 config/paperdepot.local.json')

    vault = os.path.abspath(args.vault)
    out_dir = os.path.abspath(args.out)
    os.makedirs(lp(out_dir), exist_ok=True)
    formats = [x.strip().lower() for x in args.format.split(',') if x.strip()]

    print('库：', vault)
    entries = load_entries(vault, args.limit)
    if not entries:
        raise SystemExit('没有读到任何论文条目')
    print('论文：%d 篇（%.0f%% 有摘要）' % (
        len(entries), 100.0 * sum(1 for e in entries if e.sections) / max(len(entries), 1)))
    year_count = {}
    for e in entries:
        year_count[e.year or '未知'] = year_count.get(e.year or '未知', 0) + 1
    print('年份：', '、'.join('%s(%d)' % (k, v) for k, v in sorted(year_count.items(), key=lambda kv: kv[0], reverse=True)[:8]))

    if args.fulltext:
        for e in entries:
            p = os.path.join(e.dir, 'full.md')
            if os.path.isfile(lp(p)):
                e.fulltext = parse_blocks(read_text(p))
    misc = load_misc_pages(vault, include_concepts=any(e.kind == 'new' for e in entries)) if args.include_misc else []
    if misc:
        print('附加页：', len(misc))

    base = args.title + '-手机版'
    results = []
    if 'epub' in formats:
        p = os.path.join(out_dir, base + '.epub')
        n = build_epub(entries, misc, p, args.title, args.fulltext)
        print('EPUB  →', p, '（%d 个文件, %.1f MB）' % (n, os.path.getsize(lp(p)) / 1048576))
        results.append(p)
    if 'docx' in formats or 'pdf' in formats:
        p = os.path.join(out_dir, base + '.docx')
        build_docx(entries, misc, p, args.title, args.fulltext, args.paper)
        print('DOCX  →', p, '（%.1f MB）' % (os.path.getsize(lp(p)) / 1048576))
        results.append(p)
        if 'pdf' in formats:
            pdf = docx_to_pdf(p, out_dir)
            if pdf:
                print('PDF   →', pdf, '（%.1f MB）' % (os.path.getsize(lp(pdf)) / 1048576))
                results.append(pdf)

    # 使用说明
    readme = os.path.join(out_dir, '使用说明.txt')
    with io.open(lp(readme), 'w', encoding='utf-8') as f:
        f.write('论文库文库 · 手机离线阅读版\n')
        f.write('生成于 %s，只读快照。\n\n' % datetime.now().strftime('%Y-%m-%d %H:%M'))
        f.write('怎么放到手机：\n')
        f.write('  1. 把本目录里的 epub/docx/pdf 拖进「华为云盘」任意文件夹（会同步到手机）\n')
        f.write('  2. 手机打开「云盘」App → 下载该文件\n')
        f.write('  3. 推荐顺序：\n')
        f.write('     · 华为阅读：导入本地书 → 选 EPUB\n')
        f.write('     · WPS Office：直接打开 DOCX（可重排、可搜索、目录在左侧/大纲）\n')
        f.write('     · 系统「文件管理」或 PDF 查看器：打开 PDF（兜底）\n')
        f.write('\n更新：电脑上重新导入论文后，重跑一次本脚本，覆盖云盘里的同名文件即可。\n')
    print('说明  →', readme)
    print('完成。')


if __name__ == '__main__':
    main()
