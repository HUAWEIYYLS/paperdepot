#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_digest — 把一篇论文压成给 LLM 读的「浓缩材料」

为什么需要：
    一篇 full.md 少则 30 KB、多则 300 KB（十几万字）。
    139 篇全塞给模型，既贵又慢，而且超出上下文。
    但写摘要并不需要全文——标题、摘要、章节结构、首尾关键段
    已经能覆盖 90% 的信息量。

digest 组成（约 1.5 万字符）：
    1. 元数据（标题/作者/年份/期刊/DOI）
    2. Crossref 摘要（如果有）
    3. 章节结构（从 full.md 的 # 标题提取）
    4. 正文开头 N 字符（通常含 Abstract + Introduction）
    5. 正文结尾 M 字符（通常含 Conclusion）
    6. 图注列表（图片周围的文字，帮助理解实验结果）

用法：
    python make_digest.py --vault <路径> --limit 3 --out <目录>
    python make_digest.py --vault <路径> --only "<条目目录名>"
"""
import argparse
import io
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)
H_RE = re.compile(r'^(#{1,3})\s+(.+)$', re.M)

HEAD_CHARS = 26000
TAIL_CHARS = 10000
CAPTION_MAX = 12
CAPTION_LEN = 180
# 全文短于这个阈值就整篇给出，不省略
FULL_INLINE_LIMIT = 70000


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def parse_fm(text):
    m = FM_RE.match(text)
    if not m:
        return {}
    d = {}
    key = None
    for line in m.group(1).split('\n'):
        if not line.strip():
            continue
        if re.match(r'^\s*-\s+', line) and key:
            v = re.sub(r'^\s*-\s+', '', line).strip().strip('"').strip("'")
            if not isinstance(d.get(key), list):
                d[key] = []
            d[key].append(v)
            continue
        mm = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if mm:
            key, val = mm.group(1), mm.group(2).strip()
            d[key] = val.strip('"').strip("'")
    return d


def clean_body(md: str) -> str:
    """去掉图片引用、HTML、多余空行，降低 token 浪费"""
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '[FIG]', md)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def extract_captions(body: str) -> list:
    """抓 Fig/Figure/Table 开头的图注行"""
    out = []
    for line in body.split('\n'):
        s = line.strip()
        if not s or len(s) > CAPTION_LEN * 2:
            continue
        if re.match(r'^(Fig(?:ure)?\.?\s*\d+|Table\s*\d+|图\s*\d+|表\s*\d+)', s, re.I):
            out.append(s[:CAPTION_LEN])
            if len(out) >= CAPTION_MAX:
                break
    return out


def make_digest(entry_dir: str) -> str:
    idx = os.path.join(entry_dir, 'index.md')
    full = os.path.join(entry_dir, 'full.md')

    fm = {}
    if os.path.isfile(lp(idx)):
        fm = parse_fm(io.open(lp(idx), encoding='utf-8', errors='replace').read())

    body = ''
    if os.path.isfile(lp(full)):
        body = clean_body(io.open(lp(full), encoding='utf-8', errors='replace').read())

    L = ['# 论文材料', '']
    L.append(f"标题: {fm.get('title', os.path.basename(entry_dir))}")
    au = fm.get('authors')
    if isinstance(au, list):
        L.append(f"作者: {', '.join(str(a) for a in au[:8])}"
                 + (f' …共{len(au)}人' if len(au) > 8 else ''))
    L.append(f"年份: {fm.get('year', '')}")
    L.append(f"期刊: {fm.get('journal', '')}")
    L.append(f"DOI: {fm.get('doi', '') or fm.get('arxiv', '')}")
    L.append(f"页数/图数: {fm.get('pages', '')} / {fm.get('figures', '')}")
    L.append('')

    # 章节结构
    heads = [f'{len(m.group(1)) * "#"} {m.group(2).strip()}'
             for m in H_RE.finditer(body)]
    if heads:
        L.append('## 章节结构')
        L.extend(heads[:40])
        L.append('')

    # 图注
    caps = extract_captions(body)
    if caps:
        L.append('## 图注（部分）')
        L.extend(f'- {c}' for c in caps)
        L.append('')

    # 正文开头 + 结尾
    plain = H_RE.sub(lambda m: '', body)          # 去标题行，省 token
    plain = re.sub(r'\n{3,}', '\n\n', plain).strip()
    if len(plain) <= FULL_INLINE_LIMIT:
        L.append('## 正文（全文）')
        L.append(plain)
    elif len(plain) <= HEAD_CHARS + TAIL_CHARS:
        L.append('## 正文')
        L.append(plain)
    else:
        L.append('## 正文开头')
        L.append(plain[:HEAD_CHARS])
        L.append('')
        L.append(f'…（中间省略 {len(plain) - HEAD_CHARS - TAIL_CHARS} 字符，'
                 f'如需更多细节请直接读同目录下的 full.md）…')
        L.append('')
        L.append('## 正文结尾')
        L.append(plain[-TAIL_CHARS:])

    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--out')
    ap.add_argument('--only')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if a.only:
        dirs = [os.path.join(papers, a.only)]
    else:
        dirs = [os.path.join(papers, d) for d in sorted(os.listdir(lp(papers)))
                if os.path.isdir(lp(os.path.join(papers, d))) and not d.startswith('_')]
    if a.limit:
        dirs = dirs[:a.limit]

    made = 0
    for d in dirs:
        if not os.path.isfile(lp(os.path.join(d, 'index.md'))):
            continue
        dg = make_digest(d)
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            safe = re.sub(r'[^\w\u4e00-\u9fff.-]', '_', os.path.basename(d))[:100]
            p = os.path.join(a.out, safe + '.digest.md')
            io.open(p, 'w', encoding='utf-8').write(dg)
        else:
            print('=' * 74)
            print(f'条目: {os.path.basename(d)}')
            print(f'digest 长度: {len(dg):,} 字符')
            print('=' * 74)
            print(dg[:1500])
            print('…')
        made += 1

    if a.out:
        print(f'✅ 生成 {made} 份 digest → {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
