#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repair_metadata — 只修元数据，不碰 MinerU 产物

用途：
    批量入库后，一部分条目因 Crossref 模糊搜索失败被标记 needs_metadata。
    本脚本用「PDF 内 DOI → PDF 内 arXiv → 正文 DOI → 标题搜索」四级回退
    重新解析元数据，然后**只重写 index.md**，不动 full.md / images / paper.pdf。

    不消耗 MinerU 配额，不重新下载图片，秒级完成。

用法：
    python repair_metadata.py --vault <路径>
    python repair_metadata.py --vault <路径> --all        # 已解析的也重查一遍
    python repair_metadata.py --vault <路径> --dry-run
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_entry
import doi_from_pdf
import fetch_metadata

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def read_index(path: str) -> str:
    return io.open(build_entry.lp(path), encoding='utf-8', errors='replace').read()


def is_needs_metadata(text: str) -> bool:
    return 'status: "needs_metadata"' in text or 'status: needs_metadata' in text


def resolve(pdf_path: str, fallback_title: str) -> dict:
    """四级回退，与 ingest.resolve_metadata 一致"""
    info = {'dois': [], 'arxiv': None}
    try:
        info = doi_from_pdf.extract(pdf_path)
    except Exception:
        pass

    if info.get('dois'):
        doi = doi_from_pdf.best_doi(pdf_path)
        if doi:
            try:
                m = fetch_metadata.from_doi(doi)
                print(f'      ← PDF内DOI {doi}')
                return m
            except Exception as e:
                print(f'      DOI失败 {str(e).splitlines()[0][:50]}')

    if info.get('arxiv'):
        try:
            m = fetch_metadata.from_arxiv(info['arxiv'])
            print(f'      ← PDF内arXiv {info["arxiv"]}')
            return m
        except Exception as e:
            print(f'      arXiv失败 {str(e).splitlines()[0][:50]}')

    queries = []
    if fallback_title:
        queries.append(fallback_title)
    for q in queries:
        try:
            m = fetch_metadata.from_title(q)
            print(f'      ← 标题搜索 相似{m.get("match_score")}/覆盖{m.get("match_cover")}')
            return m
        except Exception as e:
            print(f'      标题搜索失败 {str(e).splitlines()[0][:56]}')
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--all', action='store_true', help='已解析的也重查')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    papers = os.path.join(a.vault, '1-Papers')
    if not os.path.isdir(papers):
        print('vault 里没有 1-Papers', file=sys.stderr)
        return 1

    dirs = sorted(d for d in os.listdir(papers)
                  if os.path.isdir(os.path.join(papers, d)))
    targets = []
    for d in dirs:
        ip = os.path.join(papers, d, 'index.md')
        if not os.path.isfile(build_entry.lp(ip)):
            continue
        txt = read_index(ip)
        if a.all or is_needs_metadata(txt):
            targets.append(d)

    print(f'条目总数 {len(dirs)}，待修 {len(targets)}'
          f'{"（--all）" if a.all else "（仅 needs_metadata）"}')
    if not targets:
        return 0

    fixed = unchanged = failed = 0
    for i, d in enumerate(targets, 1):
        base = os.path.join(papers, d)
        ij = os.path.join(base, '.entry.json')
        if not os.path.isfile(build_entry.lp(ij)):
            print(f'\n[{i}/{len(targets)}] ⚠ 无 .entry.json，跳过: {d[:50]}')
            failed += 1
            continue
        ent = json.load(io.open(build_entry.lp(ij), encoding='utf-8'))
        pdf = ent.get('source_pdf', '')
        if not pdf or not os.path.isfile(pdf):
            # 退回条目内的 paper.pdf
            pdf = os.path.join(base, 'paper.pdf')

        print(f'\n[{i}/{len(targets)}] {d[:64]}')
        m = resolve(pdf, ent.get('title', ''))
        if not m:
            print('      ✗ 仍无法确认，保留待补标记')
            failed += 1
            continue

        if a.dry_run:
            print(f'      将更新为: {m.get("title")[:70]} | {m.get("doi") or m.get("arxiv_id")}')
            fixed += 1
            continue

        parsed = {
            'fingerprint': ent.get('fingerprint', ''),
            'layout_pages': ent.get('pages'),
            'md_chars': ent.get('chars'),
            'parsed_at': ent.get('built_at', ''),
            'title': ent.get('title', ''),
        }
        new_index = build_entry.build_index_md(m, parsed, ent.get('figures', 0))
        io.open(build_entry.lp(os.path.join(base, 'index.md')), 'w',
                encoding='utf-8').write(new_index)

        ent['meta_source'] = m.get('source')
        ent['doi'] = m.get('doi', '')
        ent['title'] = m.get('title') or ent.get('title')
        io.open(build_entry.lp(ij), 'w', encoding='utf-8').write(
            json.dumps(ent, ensure_ascii=False, indent=1))
        fixed += 1
        print(f'      ✅ {m.get("doi") or m.get("arxiv_id") or "无标识"}')

    print(f'\n{"═" * 60}')
    print(f'修复 {fixed} / 仍失败 {failed}')
    print('═' * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
