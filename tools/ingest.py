#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingest — 一条命令把 PDF 变成一个 Obsidian 论文条目

流水线：
    PDF → MinerU 解析（缓存）→ 查元数据 → 组装条目 → 写入 vault

区别于旧版：
  · 图片重命名 fig01.jpg（解决 Obsidian 长路径破图，实测验证）
  · PDF 原件随条目存放，固定名 paper.pdf
  · 元数据写进 index.md 的 frontmatter（Obsidian properties 可读）
  · 元数据查询优先用 MinerU 正文标题，回退文件名
  · Crossref 限速 + Jaccard/覆盖率双重校验，拒绝静默错配

用法：
    python ingest.py <pdf> [<pdf>...] --vault <路径>
    python ingest.py --from-storage --limit 10 --vault <路径>
    python ingest.py --from-dir <目录> --vault <路径>
"""
import argparse
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_entry
import doi_from_pdf
import fetch_metadata
import mineru_parse
import _paths

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STORAGE = (os.environ.get('ZOTERO_STORAGE') or '').strip()


def resolve_metadata(parsed: dict, pdf_path: str) -> dict:
    """
    元数据获取，四级回退（实测 2026-10-21 定的顺序）：

      ① PDF 首页直接读 DOI   → Crossref 精确查询（最可靠，不走模糊搜索）
      ② PDF 首页读 arXiv 号  → arXiv API（预印本没有 DOI 时走这条）
      ③ full.md 里找 DOI     → 同上精确查询
      ④ 正文标题模糊搜索     → 有 Jaccard + 覆盖率双重校验，宁可拒绝也不错配

    为什么不用标题搜索打头：
      实测 MUSE / Rapid FRD / PINN 等长标题，Crossref 模糊搜索相似度只有
      0.30~0.54，而且频繁 429。但它们的首页都印着 DOI 或 arXiv 号，
      直接读出来做精确查询，又快又准。
    """
    # ① / ② 从 PDF 正文提取标识
    try:
        info = doi_from_pdf.extract(pdf_path)
    except Exception:
        info = {'dois': [], 'arxiv': None}

    if info.get('dois'):
        doi = doi_from_pdf.best_doi(pdf_path)
        if doi:
            try:
                m = fetch_metadata.from_doi(doi)
                print(f'   元数据[PDF内DOI]: {m["title"][:66]} ({m["year"]})')
                return m
            except Exception as exc:
                print(f'   DOI {doi} 查询失败：{str(exc).splitlines()[0][:60]}')

    if info.get('arxiv'):
        try:
            m = fetch_metadata.from_arxiv(info['arxiv'])
            print(f'   元数据[PDF内arXiv]: {m["title"][:62]} ({m["year"]})')
            return m
        except Exception as exc:
            print(f'   arXiv {info["arxiv"]} 查询失败：{str(exc).splitlines()[0][:60]}')

    # ③ full.md 里找 DOI
    full_md = os.path.join(parsed.get('out_dir', ''), 'full.md')
    if os.path.isfile(full_md):
        try:
            text = io.open(full_md, encoding='utf-8', errors='replace').read(20000)
            for raw in doi_from_pdf.DOI_RE.findall(text):
                d = doi_from_pdf._clean_doi(raw)
                if doi_from_pdf._looks_valid(d):
                    try:
                        m = fetch_metadata.from_doi(d)
                        print(f'   元数据[正文DOI]: {m["title"][:66]} ({m["year"]})')
                        return m
                    except Exception:
                        continue
        except Exception:
            pass

    # ④ 标题模糊搜索
    queries = []
    if parsed.get('title'):
        queries.append(('正文标题', parsed['title']))
    fn = fetch_metadata.title_from_filename(pdf_path)
    if fn and fn.lower() not in [q.lower() for _, q in queries]:
        queries.append(('文件名', fn))

    last = None
    for label, q in queries:
        try:
            m = fetch_metadata.from_title(q)
            print(f'   元数据[{label}]: {m["title"][:66]} ({m["year"]}) '
                  f'相似{m.get("match_score")}/覆盖{m.get("match_cover")}')
            return m
        except Exception as exc:
            last = exc
            print(f'   元数据[{label}] 未通过：{str(exc).splitlines()[0][:76]}')

    print('   → 标记 needs_metadata，等待人工补 DOI')
    return {'source': 'mineru-fallback', 'title': parsed.get('title'),
            'authors': [], 'year': '', 'doi': ''}


def scan_fingerprints(vault: str) -> dict:
    """扫一遍库里已有条目的指纹 → 目录名，用于导入前查重（同一 PDF 不重复建条目）。"""
    out = {}
    papers = os.path.join(vault, '1-Papers')
    if not os.path.isdir(papers):
        return out
    for d in os.listdir(papers):
        p = os.path.join(papers, d, 'index.md')
        if not os.path.isfile(p):
            continue
        try:
            head = io.open(p, encoding='utf-8', errors='replace').read(4000)
        except OSError:
            continue
        m = re.search(r'^fingerprint:\s*(.+?)\s*$', head, re.M)
        if m:
            out[m.group(1).strip().strip('"\'')] = d
    return out


def ingest_one(pdf_path: str, vault: str, cache: str, overwrite=False,
               fp_index=None) -> dict:
    t0 = time.time()
    print(f'\n{"━" * 72}')
    print(f'📥 {os.path.basename(pdf_path)}')
    print('━' * 72)

    # 导入前查重：同一份 PDF（内容 sha256 指纹相同）直接跳过，不耗 MinerU 配额
    fp = mineru_parse.pdf_fingerprint(pdf_path)
    if fp_index is not None and fp in fp_index and not overwrite:
        print(f'   ⏭ 同一 PDF 已入库，跳过: {fp_index[fp]}')
        return {'slug': fp_index[fp], 'skipped': True, 'dup_of': fp_index[fp],
                'seconds': round(time.time() - t0, 1)}

    parsed = mineru_parse.parse(pdf_path, cache)
    meta = resolve_metadata(parsed, pdf_path)
    r = build_entry.build_entry(meta, parsed, pdf_path, vault, overwrite)
    if fp_index is not None and not r.get('skipped'):
        fp_index[fp] = r['slug']

    if r.get('skipped'):
        print(f'   ⏭ 已存在，跳过: {r["slug"]}')
    else:
        print(f'   ✅ {r["slug"]}')
        meta_note = '待补元数据' if r['needs_meta'] else (r['doi'] or '无DOI')
        print(f'      页 {r["pages"]} / 图 {r["figures"]} / {meta_note}')
        if r.get('unref'):
            print(f'      （{r["unref"]} 张未被正文引用的图已跳过）')
    r['seconds'] = round(time.time() - t0, 1)
    return r


def scan_storage() -> list:
    out = []
    if not STORAGE:
        print('未配置 Zotero storage：请设置环境变量 ZOTERO_STORAGE，或改用 --from-dir', file=sys.stderr)
        return out
    if not os.path.isdir(STORAGE):
        print(f'Zotero storage 目录不存在：{STORAGE}', file=sys.stderr)
        return out
    for d in sorted(os.listdir(STORAGE)):
        dp = os.path.join(STORAGE, d)
        if not os.path.isdir(dp):
            continue
        try:
            for f in os.listdir(dp):
                if f.lower().endswith('.pdf'):
                    out.append(os.path.join(dp, f))
        except OSError:
            pass
    return out


def scan_dir(path: str) -> list:
    out = []
    for root, dirs, files in os.walk(path):
        for f in files:
            if f.lower().endswith('.pdf'):
                out.append(os.path.join(root, f))
    return out


def main():
    ap = argparse.ArgumentParser(description='PDF → Obsidian 条目')
    ap.add_argument('pdfs', nargs='*')
    ap.add_argument('--from-storage', action='store_true')
    ap.add_argument('--from-dir')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--skip', type=int, default=0)
    ap.add_argument('--vault', default=_paths.default_vault())
    ap.add_argument('--cache', default=mineru_parse.DEFAULT_CACHE)
    ap.add_argument('--overwrite', action='store_true')
    a = ap.parse_args()

    targets = list(a.pdfs)
    if a.from_storage:
        allp = scan_storage()
        print(f'Zotero storage 内 PDF: {len(allp)} 个')
        targets += allp
    if a.from_dir:
        allp = scan_dir(a.from_dir)
        print(f'目录内 PDF: {len(allp)} 个')
        targets += allp
    if a.skip:
        targets = targets[a.skip:]
    if a.limit:
        targets = targets[:a.limit]

    if not targets:
        print('没有可处理的 PDF', file=sys.stderr)
        return 1

    os.makedirs(os.path.join(a.vault, '1-Papers'), exist_ok=True)
    fp_index = scan_fingerprints(a.vault)
    print(f'待处理: {len(targets)} 篇 → {a.vault}'
          + (f'（库内已有指纹 {len(fp_index)} 个）' if fp_index else ''))

    results = []
    t_start = time.time()
    for i, p in enumerate(targets, 1):
        print(f'\n[{i}/{len(targets)}]', end='')
        try:
            results.append(ingest_one(p, a.vault, a.cache, a.overwrite, fp_index))
        except mineru_parse.QuotaExhausted as exc:
            print(f'\n🛑 {exc}')
            print(f'   已完成 {len(results)} 篇，剩余 {len(targets) - i + 1} 篇留待明日')
            break
        except Exception as exc:
            print(f'   ❌ {type(exc).__name__}: {exc}')
            results.append({'slug': os.path.basename(p), 'error': str(exc)})

    ok = [r for r in results if not r.get('error') and not r.get('skipped')]
    skip = [r for r in results if r.get('skipped')]
    err = [r for r in results if r.get('error')]
    el = time.time() - t_start

    print(f'\n{"═" * 72}')
    print(f'完成：成功 {len(ok)} / 跳过 {len(skip)} / 失败 {len(err)}   '
          f'总耗时 {el/60:.1f} 分钟')
    print('═' * 72)
    for r in ok:
        print(f'  ✅ {r["slug"][:58]}  ({r.get("pages")}页/{r.get("figures")}图)')
    for r in err:
        print(f'  ❌ {r["slug"][:58]}: {r["error"][:70]}')

    needs = [r for r in ok if r.get('needs_meta')]
    if needs:
        print(f'\n⚠ {len(needs)} 篇需补元数据：')
        for r in needs:
            print(f'   · {r["slug"][:66]}')

    rep = os.path.join(a.vault, '_ingest_report.json')
    json.dump({'finished_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
               'total': len(targets), 'ok': len(ok), 'skipped': len(skip),
               'failed': len(err), 'seconds': round(el, 1), 'results': results},
              io.open(rep, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n报告: {rep}')
    return 0 if not err else 2


if __name__ == '__main__':
    sys.exit(main())
