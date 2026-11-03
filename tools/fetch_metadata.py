#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_metadata — 用 DOI / arXiv ID / 标题 查文献元数据

这是「Zotero 退场」后替代 Zotero Connector 抓取元数据的积木。
只负责"查元数据"，不负责"下载 PDF"、不负责"入库"。

数据源优先级：
  1. DOI       → Crossref（最权威，期刊论文首选）
  2. arXiv ID  → arXiv API（预印本），失败退到 abs 页面 HTML meta
  3. 标题      → Crossref 模糊搜索（用于中文论文等无 DOI 情况）

本机实测（2026-10-20）：
  · Crossref      ✅ 200
  · OpenAlex      ✅ 200
  · arXiv API     ⚠️ 有限流，必须间隔 ≥3 秒，批量用 id_list=
  · arXiv abs 页  ✅ 200（API 挂了时的 fallback）

用法：
    python fetch_metadata.py --doi 10.1086/521816
    python fetch_metadata.py --arxiv 2401.12345
    python fetch_metadata.py --title "The photonic lantern"
    python fetch_metadata.py --pdf <路径>        # 从文件名猜测标题再查
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_CONTACT = (os.environ.get('PAPERDEPOT_CONTACT_EMAIL') or '').strip()
UA = (f'PaperDepot/1.0 (mailto:{_CONTACT})' if _CONTACT
      else 'PaperDepot/1.0 (+https://github.com/OWNER/paperdepot)')
TIMEOUT = 30

# arXiv 官方要求：单连接、间隔 3 秒。裸调会被限流（实测 10 次里 4 次失败）
_ARXIV_LAST = [0.0]
ARXIV_MIN_INTERVAL = 3.0

# Crossref 礼貌池：连续批量请求实测 5 篇内就 429。
# 官方建议加 mailto（已在 UA 里），并保持 ≤ 1 req/s。这里留 1.5s 余量。
_CROSSREF_LAST = [0.0]
CROSSREF_MIN_INTERVAL = 3.0


class MetadataError(RuntimeError):
    pass


def throttle(kind: str):
    """按服务分别限速，避免批量时被 429"""
    if kind == 'arxiv':
        gap = time.time() - _ARXIV_LAST[0]
        if gap < ARXIV_MIN_INTERVAL:
            time.sleep(ARXIV_MIN_INTERVAL - gap)
        _ARXIV_LAST[0] = time.time()
    else:
        gap = time.time() - _CROSSREF_LAST[0]
        if gap < CROSSREF_MIN_INTERVAL:
            time.sleep(CROSSREF_MIN_INTERVAL - gap)
        _CROSSREF_LAST[0] = time.time()


def http_get(url: str, accept: str = '*/*', retries: int = 4) -> bytes:
    """带退避的 GET。不设置任何代理，直连。429 单独退避更久。"""
    headers = {'User-Agent': UA, 'Accept': accept}
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:                 # 限流：指数退避
                wait = 5 * (attempt + 1)
                print(f'    Crossref 429，等待 {wait}s 后重试…', file=sys.stderr)
                time.sleep(wait)
                continue
            if 400 <= exc.code < 500:           # 其它客户端错误不重试
                raise MetadataError(f'HTTP {exc.code}: {exc.reason}') from exc
            time.sleep(2 * (attempt + 1))
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise MetadataError(f'请求失败: {last}')


def _clean_title(title: str) -> str:
    """剥掉 Crossref 返回标题里的 HTML 标签和多余空白"""
    if not title:
        return ''
    t = re.sub(r'<[^>]+>', '', title)          # <i> </i> <sub> 等
    t = t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    t = re.sub(r'\s+', ' ', t).strip()
    return t.rstrip('.')


def _norm_authors(author_list) -> list:
    out = []
    for a in author_list or []:
        if not isinstance(a, dict):
            continue
        if a.get('family'):
            name = f"{a.get('given', '')} {a['family']}".strip()
        else:
            name = a.get('name', '')
        if name:
            out.append(name)
    return out


def _year_from(part) -> str:
    """
    从 Crossref 的日期结构里取年份。

    实测会遇到畸形结构（如 date-parts 被写成 [2021.0]），
    直接 [0][0] 会抛 'float' object is not subscriptable。
    """
    try:
        if isinstance(part, list):
            if not part:
                return ''
            part = part[0]
        if not isinstance(part, dict):
            return ''
        dp = part.get('date-parts')
        if not dp or not isinstance(dp, list):
            return ''
        first = dp[0]
        if isinstance(first, list):
            if not first or first[0] is None:
                return ''
            return str(int(first[0]))
        if isinstance(first, (int, float)):
            return str(int(first))
        return ''
    except (TypeError, ValueError, IndexError):
        return ''


# ── Crossref ──────────────────────────────────────────────────────────
def from_doi(doi: str) -> dict:
    doi = doi.strip()
    doi = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', doi, flags=re.I)
    throttle('crossref')
    url = f'https://api.crossref.org/works/{urllib.parse.quote(doi)}'
    msg = json.loads(http_get(url, 'application/json'))['message']

    return {
        'source': 'crossref',
        'doi': msg.get('DOI') or doi,
        'title': _clean_title((msg.get('title') or [''])[0]),
        'authors': _norm_authors(msg.get('author')),
        'year': _year_from(msg.get('published-print') or msg.get('published-online')
                           or msg.get('issued')),
        'journal': _clean_title((msg.get('container-title') or [''])[0]),
        'publisher': msg.get('publisher', ''),
        'volume': msg.get('volume', ''),
        'issue': msg.get('issue', ''),
        'page': msg.get('page', ''),
        'type': msg.get('type', ''),
        'abstract': re.sub(r'<[^>]+>', '', msg.get('abstract', '') or '').strip()[:2000],
        'url': msg.get('URL', ''),
        'references_count': msg.get('reference-count', 0),
    }


def _similarity(a: str, b: str) -> float:
    """
    标题相似度 = Jaccard（交集/并集）。

    ⚠️ 为什么不用 交集/min(len)（曾用，有致命缺陷）：
       查询 "The 2.5 m telescope of the sloan digital sky survey"
       候选 "Sloan Digital Sky Survey"（AccessScience 百科词条）
       交集/min = 4/4 = 1.0 → 被当成完美匹配，静默写入错误 DOI。
       Jaccard 下这条只有 4/6 = 0.67，而正确标题是 6/6 = 1.0，
       排序就能把正确结果顶上来。
    """
    def norm(s):
        s = _clean_title(s).lower()
        s = re.sub(r'[^a-z0-9\u4e00-\u9fff ]+', ' ', s)
        return {w for w in s.split() if len(w) > 2 or re.match(r'[\u4e00-\u9fff]', w)}
    sa, sb = norm(a), norm(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _coverage(query: str, cand: str) -> float:
    """查询词有多大比例被候选覆盖 —— 防止候选标题过短却混过阈值"""
    def norm(s):
        s = _clean_title(s).lower()
        s = re.sub(r'[^a-z0-9\u4e00-\u9fff ]+', ' ', s)
        return {w for w in s.split() if len(w) > 2 or re.match(r'[\u4e00-\u9fff]', w)}
    sq, sc = norm(query), norm(cand)
    if not sq:
        return 0.0
    return len(sq & sc) / len(sq)


def _crossref_search(query: str, field: str, rows: int) -> list:
    """Crossref 检索。field='title' 命中率远高于 'bibliographic'。"""
    throttle('crossref')
    params = {field: query, 'rows': rows,
              'select': 'DOI,title,author,issued,container-title,publisher,type'}
    url = 'https://api.crossref.org/works?' + urllib.parse.urlencode(params)
    try:
        return json.loads(http_get(url, 'application/json'))['message']['items']
    except (KeyError, json.JSONDecodeError):
        return []


def from_title(query: str, rows: int = 8, min_score: float = 0.60,
               min_cover: float = 0.75) -> dict:
    """
    标题检索，双重校验。

    实测关键差异（2026-10-21，本机）：
        query.bibliographic 查 "The 2.5 m Telescope of the SDSS"
            → 返回的全是 "Sloan Digital Sky Survey" 百科词条，正确的**根本不在结果里**
        query.title 查同一句
            → 第 4 条就是 10.1086/500975，Jaccard = 1.00
      ⇒ 必须用 query.title；bibliographic 只作为兜底。

    两道校验（见 _similarity 注释里的真实事故）：
      · min_score : Jaccard ≥ 0.60（排序用，避免子集匹配霸榜）
      · min_cover : 查询词覆盖率 ≥ 0.75（过滤掉过短的泛化条目）
    低于阈值就报错，绝不静默接受。
    """
    best = None
    tried = []

    # 退化查询防护（实测事故 2026-10-23）：
    #   · 文件名 "509.pdf" → 查询 "509" → 匹配到 1917 年同名数学论文（DOI 完全不对）
    #   · 章节名 "Case studies" → 匹配到图书馆学书的一章
    #   过短、词数过少的查询没法唯一定位，宁可拒绝也不瞎猜。
    plain = re.sub(r'[^A-Za-z\u4e00-\u9fff0-9 ]', ' ', query or '').strip()
    words = [w for w in plain.split() if w]
    if len(plain) < 12 or len(words) < 3:
        raise MetadataError(
            f'查询串过于简短/泛化，拒绝模糊匹配\n'
            f'      查询: {query!r}（{len(words)} 个词，{len(plain)} 字符）\n'
            f'      → 请用 --doi / --arxiv 精确指定，或手工填写元数据')

    for field in ('query.title', 'query.bibliographic'):
        items = _crossref_search(query, field, rows)
        tried.append(f'{field}={len(items)}条')
        scored = []
        for it in items:
            try:
                t = _clean_title((it.get('title') or [''])[0])
                if not t:
                    continue
                scored.append((_similarity(query, t), _coverage(query, t), t, it))
            except Exception:
                # 单条畸形记录不能毁掉整次查询（实测会偶发 date-parts 为 float）
                continue
        if not scored:
            continue
        scored.sort(key=lambda x: (-x[0], -x[1]))
        # best 本身就是 (score, cover, title, item) 元组，比较时取 best[0] 即 score
        if best is None or scored[0][0] > best[0]:
            best = scored[0]
            best_all = scored
        # 已经拿到高质量匹配就不必再试第二个字段
        if scored[0][0] >= 0.85 and scored[0][1] >= 0.85:
            break

    if best is None:
        raise MetadataError(f'Crossref 无结果: {query!r}')

    best_score, best_cover, best_title, item = best
    if best_score < min_score or best_cover < min_cover:
        raise MetadataError(
            f'Crossref 结果与查询不匹配（相似 {best_score:.2f}/覆盖 {best_cover:.2f}）\n'
            f'      查询: {query[:90]}\n'
            f'      最像: {best_title[:90]}\n'
            f'      已试: {", ".join(tried)}\n'
            f'      → 拒绝静默接受，请用 --doi 精确指定')

    result = {
        'source': 'crossref-title',
        'doi': item.get('DOI', ''),
        'title': best_title,
        'authors': _norm_authors(item.get('author')),
        'year': _year_from(item.get('issued')),
        'journal': _clean_title((item.get('container-title') or [''])[0]),
        'publisher': item.get('publisher', ''),
        'type': item.get('type', ''),
        'match_score': round(best_score, 2),
        'match_cover': round(best_cover, 2),
        'query': query,
    }
    others = [{'doi': it.get('DOI', ''), 'title': t, 'year': _year_from(it.get('issued')),
               'score': round(s, 2)}
              for s, c, t, it in best_all[1:]
              if s >= min_score and c >= min_cover * 0.9]
    if others:
        result['other_candidates'] = others[:3]
    return result


# ── arXiv ─────────────────────────────────────────────────────────────
def _arxiv_throttle():
    throttle('arxiv')


def from_arxiv(arxiv_id: str) -> dict:
    aid = re.sub(r'^(arxiv:|https?://arxiv\.org/(abs|pdf)/)', '',
                 arxiv_id.strip(), flags=re.I).removesuffix('.pdf')
    try:
        _arxiv_throttle()
        url = f'http://export.arxiv.org/api/query?id_list={urllib.parse.quote(aid)}'
        xml_bytes = http_get(url, 'application/atom+xml')
        root = ET.fromstring(xml_bytes)
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        entry = root.find('a:entry', ns)
        if entry is None:
            raise MetadataError('arXiv 无 entry')
        title = (entry.findtext('a:title', '', ns) or '').strip()
        if not title or 'Error' in title:
            raise MetadataError('arXiv 返回错误条目')
        authors = [(e.findtext('a:name', '', ns) or '').strip()
                   for e in entry.findall('a:author', ns)]
        published = entry.findtext('a:published', '', ns) or ''
        return {
            'source': 'arxiv-api',
            'arxiv_id': aid,
            'title': re.sub(r'\s+', ' ', title),
            'authors': [a for a in authors if a],
            'year': published[:4],
            'abstract': re.sub(r'\s+', ' ', entry.findtext('a:summary', '', ns) or '').strip(),
            'url': f'https://arxiv.org/abs/{aid}',
            'doi': entry.findtext('{http://arxiv.org/schemas/atom}doi', '', ns) or '',
        }
    except (MetadataError, ET.ParseError, OSError) as exc:
        # 退到 abs 页面 HTML meta（文档 6 说这条路可用）
        print(f'    arXiv API 失败（{exc}），回退 abs 页面…', file=sys.stderr)
        html = http_get(f'https://arxiv.org/abs/{aid}', 'text/html').decode('utf-8', 'replace')
        meta = dict(re.findall(
            r'<meta\s+name="(citation_\w+)"\s+content="([^"]*)"', html, re.I))
        if not meta.get('citation_title'):
            raise MetadataError(f'arXiv 两条路都失败: {aid}') from exc
        return {
            'source': 'arxiv-abs-page',
            'arxiv_id': aid,
            'title': meta.get('citation_title', '').strip(),
            'authors': re.findall(
                r'<meta\s+name="citation_author"\s+content="([^"]*)"', html, re.I),
            'year': (meta.get('citation_date') or '')[:4],
            'url': f'https://arxiv.org/abs/{aid}',
            'doi': meta.get('citation_doi', ''),
        }


# ── 从 PDF 文件名猜标题 ───────────────────────────────────────────────
def title_from_filename(path: str) -> str:
    """
    Zotero 保存的通常是 "作者 等 - 年份 - 标题.pdf" 或 "作者 - 年份 - 标题.pdf"。
    剥掉前后缀，只留标题部分。
    """
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r'\(\d+\)$', '', base).strip()          # 冲突副本后缀
    parts = [p.strip() for p in base.split(' - ')]
    if len(parts) >= 3 and re.fullmatch(r'(19|20)\d{2}', parts[1]):
        return ' - '.join(parts[2:])
    if len(parts) >= 2:
        return parts[-1]
    return base


# ── 主流程 ────────────────────────────────────────────────────────────
def resolve(doi=None, arxiv=None, title=None, pdf=None) -> dict:
    if doi:
        return from_doi(doi)
    if arxiv:
        return from_arxiv(arxiv)
    if title or pdf:
        return from_title(title or title_from_filename(pdf))
    raise MetadataError('必须提供 --doi / --arxiv / --title / --pdf 之一')


def main():
    ap = argparse.ArgumentParser(description='查文献元数据（Crossref / arXiv）')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--doi')
    g.add_argument('--arxiv')
    g.add_argument('--title')
    g.add_argument('--pdf')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    try:
        m = resolve(a.doi, a.arxiv, a.title, a.pdf)
    except MetadataError as exc:
        print(f'❌ {exc}', file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return 0

    print('─' * 62)
    print(f"  来源    : {m.get('source')}")
    print(f"  标题    : {m.get('title')}")
    au = m.get('authors') or []
    print(f"  作者    : {', '.join(au[:4])}" + (' …' if len(au) > 4 else ''))
    print(f"  年份    : {m.get('year')}")
    for k, label in (('journal', '期刊'), ('doi', 'DOI'), ('arxiv_id', 'arXiv'),
                     ('volume', '卷期'), ('page', '页码'), ('type', '类型')):
        if m.get(k):
            print(f"  {label:<8}: {m[k]}")
    if m.get('other_candidates'):
        print(f"  ⚠ 另有 {len(m['other_candidates'])} 个候选，可用 --json 查看")
    print('─' * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
