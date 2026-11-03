#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_concepts — 概念层（2-Concepts/）校验

检查项：
  ① frontmatter 结构：type: concept、title、aliases、tags、papers、updated
  ② tags 是否全部落在受控词表（config/tagmap_*.json 的 canonical 值）内
  ③ wikilink 是否全部命中 1-Papers/<目录>/index.md
  ④ 数字溯源：页面里的数字是否都能在 cache/_concept_<title>.md 素材里找到
  ⑤ papers 字段是否等于实际去重链接数

用法：
    python verify_concepts.py --vault <vault路径>
    python verify_concepts.py --vault <vault路径> --concept 焦比退化
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
CONFIG = os.path.join(os.path.dirname(HERE), 'config')
CATS = ('领域', '方法', '应用', '仪器')
FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)
WIKI_RE = re.compile(r'\[\[(.+?)\]\]')
MDLINK_RE = re.compile(r'(?<!!)\[([^\]\n]*)\]\(([^)\n]+)\)')
NUM_RE = re.compile(r'\d+(?:\.\d+)?')


def load_canonical():
    canon = set()
    for c in CATS:
        p = os.path.join(CONFIG, f'tagmap_{c}.json')
        if os.path.isfile(p):
            d = json.load(io.open(p, encoding='utf-8'))
            canon |= {f'{c}/{v}' for v in d.get('mapping', {}).values()}
    return canon


def parse_frontmatter(text):
    m = FM_RE.match(text)
    if not m:
        return None, text
    fm = m.group(1)
    out = {}

    def scalar(key):
        mm = re.search(rf'^{re.escape(key)}:\s*(.+?)\s*$', fm, re.M)
        if not mm:
            return None
        v = mm.group(1).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        return v

    def block_list(key):
        mm = re.search(rf'^{re.escape(key)}:\s*\n((?:[ \t]*-[^\n]*\n?)+)', fm, re.M)
        if not mm:
            return []
        items = []
        for line in mm.group(1).splitlines():
            s = line.strip()
            if s.startswith('-'):
                s = s[1:].strip().strip('"\'')
                if s:
                    items.append(s)
        return items

    out['title'] = scalar('title')
    out['type'] = scalar('type')
    out['papers'] = scalar('papers')
    out['updated'] = scalar('updated')
    out['aliases'] = block_list('aliases')
    out['tags'] = block_list('tags')
    return out, text[m.end():]


def split_target(inner):
    """'1-Papers/x/index|alias' / '1-Papers/x/index\\|alias' -> ('1-Papers/x/index','alias')"""
    i = inner.find('|')
    if i == -1:
        return inner.replace('\\', '').strip(), ''
    target = inner[:i].replace('\\', '').strip()
    alias = inner[i + 1:].strip()
    return target, alias


def verify_one(vault, path, canon, material_dir):
    name = os.path.splitext(os.path.basename(path))[0]
    text = io.open(path, encoding='utf-8', errors='replace').read()
    fm, body = parse_frontmatter(text)
    errors, warns = [], []

    if fm is None:
        return name, ['缺少 frontmatter'], []

    if fm.get('type') != 'concept':
        errors.append(f"type 应为 concept，实为 {fm.get('type')!r}")
    if not fm.get('title'):
        errors.append('缺少 title')
    if fm.get('title') and fm['title'] != name:
        warns.append(f"title({fm['title']}) 与文件名({name}) 不一致")
    if not fm.get('updated'):
        errors.append('缺少 updated')
    if not fm.get('aliases'):
        warns.append('缺少 aliases')

    bad_tags = [t for t in fm['tags'] if t not in canon]
    if bad_tags:
        errors.append('tags 不在受控词表：' + ', '.join(bad_tags))

    # ---- wikilinks ----
    paper_links = []
    for m in WIKI_RE.finditer(body):
        target, alias = split_target(m.group(1))
        if target.startswith('1-Papers/'):
            ap = os.path.join(vault, target + ('' if target.endswith('.md') else '.md'))
            if not os.path.isfile(ap):
                errors.append(f'断链：[[{target}]]（不存在）')
                continue
            paper_links.append(target)
        elif target.startswith('2-Concepts/'):
            ap = os.path.join(vault, target + ('' if target.endswith('.md') else '.md'))
            if not os.path.isfile(ap):
                errors.append(f'断链：[[{target}]]（概念页不存在）')
        else:
            errors.append(f'wikilink 未指向 1-Papers/ 或 2-Concepts/：[[{m.group(1)}]]')

    # markdown 内部链接（概念页里不应出现相对链接）
    for m in MDLINK_RE.finditer(body):
        href = m.group(2).strip()
        if href.startswith(('http://', 'https://', 'mailto:')):
            continue
        errors.append(f'出现 markdown 内部链接（应改用 wikilink）：{href}')

    # ---- papers 计数 ----
    uniq = len(set(paper_links))
    try:
        declared = int(fm.get('papers') or 0)
    except ValueError:
        declared = -1
    if declared < uniq or declared > uniq + 3:
        warns.append(f'papers 字段={declared}，实际去重链接数={uniq}（允许 +1~3：目录名含特殊字符的论文以纯文本列出）')

    # ---- 数字溯源 ----
    # 数字必须出现在：① 概念素材；或 ② 本页所链接论文的 index.md（摘要本身已验收）
    mpath = os.path.join(material_dir, f'_concept_{fm.get("title") or name}.md')
    if os.path.isfile(mpath):
        pool = io.open(mpath, encoding='utf-8', errors='replace').read()
    else:
        pool = ''
        warns.append(f'找不到素材文件 {mpath}，只用所引论文做溯源')
    for target in set(paper_links):
        p = os.path.join(vault, target + ('' if target.endswith('.md') else '.md'))
        if os.path.isfile(p):
            pool += '\n' + io.open(p, encoding='utf-8', errors='replace').read()
    if pool:
        missing = sorted({tok for tok in NUM_RE.findall(body) if tok not in pool})
        if missing:
            warns.append('数字未在素材/所引论文中找到（需人工确认）：'
                         + ', '.join(missing[:15]) + (' …' if len(missing) > 15 else ''))

    # ---- 结构 ----
    for sec in ('## 定义与物理图像', '## 工程后果', '## 测量与评价方法',
                '## 各文献的贡献', '## 共识与分歧', '## 相关概念', '## 📄 相关论文'):
        if sec not in body:
            errors.append(f'缺少章节：{sec}')

    return name, errors, warns


def verify_index(vault, cdir):
    """校验 2-Concepts/_index.md 里的链接是否可达。"""
    path = os.path.join(cdir, '_index.md')
    if not os.path.isfile(path):
        return None
    errors = []
    text = io.open(path, encoding='utf-8', errors='replace').read()
    for m in WIKI_RE.finditer(text):
        target, _ = split_target(m.group(1))
        rel = target + '.md' if not target.endswith('.md') else target
        if not os.path.isfile(os.path.join(vault, rel)):
            errors.append(f'断链：[[{target}]]')
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--concept', default=None)
    ap.add_argument('--material-dir',
                    default=os.path.join(os.path.dirname(HERE), 'cache'))
    a = ap.parse_args()

    cdir = os.path.join(a.vault, '2-Concepts')
    if not os.path.isdir(cdir):
        print(f'❌ 不存在 {cdir}')
        return 1

    canon = load_canonical()
    files = sorted(f for f in os.listdir(cdir)
                   if f.endswith('.md') and not f.startswith('_'))
    if a.concept:
        files = [f for f in files if os.path.splitext(f)[0] == a.concept]
    if not files:
        print('没有找到概念页')
        return 1

    total_err = 0
    for f in files:
        name, errors, warns = verify_one(a.vault, os.path.join(cdir, f),
                                         canon, a.material_dir)
        status = '✅' if not errors else '❌'
        print(f'{status} {name}  （警告 {len(warns)}）')
        for e in errors:
            print(f'   ✗ {e}')
        for w in warns:
            print(f'   ⚠ {w}')
        total_err += len(errors)

    idx_errors = verify_index(a.vault, cdir)
    if idx_errors is not None:
        status = '✅' if not idx_errors else '❌'
        print(f'{status} _index.md（概念索引）')
        for e in idx_errors:
            print(f'   ✗ {e}')
        total_err += len(idx_errors)

    print(f'\n共 {len(files)} 页，错误 {total_err} 项')
    return 1 if total_err else 0


if __name__ == '__main__':
    sys.exit(main())
