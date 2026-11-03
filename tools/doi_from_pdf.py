#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doi_from_pdf — 从 PDF 首页/次页正文里直接提取 DOI

为什么优先用这个（实测 2026-10-21）：
    Crossref 标题模糊搜索对长标题、副标题、带上下标的标题排序很差，
    MUSE / Rapid FRD / PINN 等实测相似度只有 0.30~0.54，被校验拒绝。
    而期刊论文首页几乎都印着 DOI，直接读出来就能用 Crossref 的精确查询，
    不消耗模糊匹配、不会错配、也不受 429 限流影响。

顺带从正文提取：
    · 年份（首页常印 © 2016 / Received 2016）
    · arXiv 编号

只用 PyMuPDF 读前 2 页，速度与 PDF 体积无关。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DOI_RE = re.compile(r'\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')
ARXIV_RE = re.compile(r'arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?', re.I)
YEAR_RE = re.compile(r'\b(19[5-9]\d|20[0-4]\d)\b')

# DOI 末尾常粘连标点或后续字符，需要裁剪
TAIL_STRIP = '.,;:)]}>"\''


def _clean_doi(d: str) -> str:
    d = d.rstrip(TAIL_STRIP)
    # 切断后面误粘的单词（doi 里不会出现大写开头的长串紧跟小写）
    m = re.match(r'^(.*?)(?:\s|$)', d)
    return m.group(1) if m else d


def _looks_valid(d: str) -> bool:
    if len(d) < 8 or len(d) > 120:
        return False
    if d.lower().startswith('10.0000'):     # 占位符
        return False
    # 必须有注册者前缀 + 后缀
    body = d[4:]
    return '/' in body and len(body.split('/')[-1]) >= 3


def extract(pdf_path: str, pages: int = 2) -> dict:
    """
    返回 {'dois': [...], 'arxiv': str|None, 'years': [...]}
    读不到就返回空列表，不抛异常。
    """
    out = {'dois': [], 'arxiv': None, 'years': []}
    if not os.path.isfile(pdf_path):
        return out
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            return out

    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return out

    try:
        n = min(pages, doc.page_count)
        text = '\n'.join(doc.load_page(i).get_text('text') for i in range(n))
    except Exception:
        doc.close()
        return out
    finally:
        try:
            doc.close()
        except Exception:
            pass

    seen = []
    for raw in DOI_RE.findall(text):
        d = _clean_doi(raw)
        if _looks_valid(d) and d.lower() not in [s.lower() for s in seen]:
            seen.append(d)
    out['dois'] = seen

    m = ARXIV_RE.search(text)
    if m:
        out['arxiv'] = m.group(1)

    out['years'] = sorted(set(YEAR_RE.findall(text)))[-3:]
    return out


def best_doi(pdf_path: str) -> str:
    """取最像论文 DOI 的一个（优先含期刊常见前缀、长度适中的）"""
    r = extract(pdf_path)
    dois = r['dois']
    if not dois:
        return ''
    # 排除常见非论文 DOI（数据集、软件）
    def score(d):
        low = d.lower()
        s = 0
        if any(k in low for k in ('10.1051/', '10.1086/', '10.1093/',
                                  '10.1117/', '10.1088/', '10.3847/',
                                  '10.1364/', '10.1016/', '10.1093/',
                                  '10.1063/', '10.1109/', '10.1007/')):
            s += 2
        if 'zenodo' in low or 'figshare' in low:
            s -= 3
        return s
    dois.sort(key=lambda d: -score(d))
    return dois[0]


if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = extract(p)
        print(os.path.basename(p))
        print('  DOIs :', r['dois'][:5])
        print('  arXiv:', r['arxiv'])
        print('  years:', r['years'])
