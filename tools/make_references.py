#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_references — 从 full.md 的参考文献段生成 references.md（纯规则，不调 LLM）

分两层，逐层回退（思路借自 Agentero 的 L1/L3）：
  L1 在线：有 DOI / arXiv 时问 Semantic Scholar references，再退 Crossref reference[]；
           结果是结构化的，写进 references.md 时同时注明 source=s2/crossref
  L3 离线：full.md 里的参考文献段按规则切分（默认，不联网）

设计原则：
  · 只读 full.md，不碰 PDF / 图片 / summary.md / tags.md
  · 解析失败不落文件，绝不把上游 ingest 搞失败
  · 在线拉取失败静默回退，不报错、不阻断
  · 相同 source_hash（+ source）且目标文件存在时 SKIP（幂等，在线结果也不重复联网）
  · 写 references.md / index.md 用临时文件 + os.replace（避免半截文件）

用法：
    python make_references.py --vault <vault> --entry "<条目目录名>"
    python make_references.py --vault <vault> --all [--force] [--offline|--online]
    python make_references.py --from-files <某个 full.md> [--doi 10.x/y] [--arxiv 2401.00001]

返回码：0 全成功；1 有条目失败但其余照跑；2 参数/环境错误。
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from _paths import lp
except Exception:  # 直接 import 或脚本目录不在 sys.path 时兜底
    def lp(p):
        if os.name != 'nt' or p.startswith('\\\\?\\'):
            return p
        return '\\\\?\\' + os.path.abspath(p)

# ── 解析规则 ──────────────────────────────────────────────────────────
# 参考文献标题：允许 1–4 级标题，忽略大小写；取【最后一个】命中行。
HEADING_RE = re.compile(
    r'^[ \t]{0,3}(#{1,4})[ \t]+(references?|bibliography|reference list|literature cited|参考文献)[ \t]*$',
    re.I | re.M,
)
# 真实 MinerU 文档里还有 "## 7. REFERENCES" / "## References and links" /
# "## 参考文献：" / "## References and Notes:" 等变体；精确匹配不到时再放宽。
LOOSE_HEADING_RE = re.compile(
    r'^[ \t]{0,3}(#{1,4})[ \t]*(?:\d+[.)]?[ \t]*)?'
    r'(references?|bibliography|reference list|literature cited|参考文献)'
    r'(?:[ \t]*(?:and|&)[ \t]+(?:links?|notes?))?[ \t]*[：:]?[ \t]*$',
    re.I | re.M,
)
ANY_HEADING_RE = re.compile(r'^[ \t]{0,3}(#{1,6})[ \t]+\S', re.M)

# 条目前缀：按优先级匹配，避免 "1.2" 之类被裸数字误切。
PREFIX_PATTERNS = (
    re.compile(r'^\[(\d{1,4})\][ \t]*'),               # [1]
    re.compile(r'^(\d{1,4})\.[ \t]+'),                  # 1.
    re.compile(r'^(\d{1,4})\)[ \t]*'),                  # 1)
    re.compile(r'^\$?\^\{[ \t]*(\d{1,4})[ \t]*\}\$?[ \t]*'),  # $^{1}$ / ^{1}
    re.compile(r'^(\d{1,4})[ \t]+(?=\S)'),              # 裸数字
)

# 没有前缀时按空行分块；分块仍不足 3 条则判定失败。
BLOCK_SPLIT_RE = re.compile(r'\n[ \t]*\n')

# 实测 439 条真实参考文献段是合法的，不能用 400 这种阈值误杀。
MAX_REFERENCES = 1000

# 脚注：原文一般是行首 \*（如 \*This research was supported…）。
# 只要求行首 \*；不再限制 <60 字符——实测这篇就有 113 字符。
NOTE_HEAD_RE = re.compile(r'^(?:\\\*|\*(?!\*))')

# 只用于识别参考文献段末尾的出版方说明/排版说明，不当成一条文献。
TAIL_NOTE_RE = re.compile(
    r'^(publisher[’\'"]?s note|this paper has been typeset|all rights reserved|copyright|©)',
    re.I,
)

# 不排除 ) / ;：DOI 本身可能含括号（如 10.1002/(SICI)…）和分号，
# 交给 _clean_doi 只削末尾标点/不配对的右括号。
DOI_RE = re.compile(r'10\.\d{4,9}/[^\s\]]+')
ARXIV_RE = re.compile(r'arXiv:\s*(\d{4}\.\d{4,5})(v\d+)?', re.I)
HTTP_RE = re.compile(r'https?://\S+', re.I)

REFS_MARKER_RE = re.compile(
    r'<!-- paperdepot:refs:start -->.*?<!-- paperdepot:refs:end -->',
    re.S,
)


# ── 基础工具 ──────────────────────────────────────────────────────────
def _norm_text(text):
    return str(text or '').replace('\r\n', '\n').replace('\r', '\n')


def _is_note_line(line):
    return bool(NOTE_HEAD_RE.match(line.lstrip()))


def _looks_like_tail_note(line):
    return len(line) < 400 and bool(TAIL_NOTE_RE.match(line.strip()))


def _match_prefix(line):
    """返回 (前缀结束位置, 原文编号, 类型) 或 None。"""
    for idx, rx in enumerate(PREFIX_PATTERNS):
        m = rx.match(line)
        if m:
            kind = 'bare' if idx == len(PREFIX_PATTERNS) - 1 else 'numbered'
            return m.end(), int(m.group(1)), kind
    return None


def _clean_doi(doi):
    """去掉 DOI 后面的句读；只去掉不配对的右括号，保留合法的 (...) 后缀。"""
    doi = doi.strip()
    while doi and doi[-1] in '.,;:':
        doi = doi[:-1]
    while doi.endswith(')') and doi.count('(') < doi.count(')'):
        doi = doi[:-1]
    return doi


def _append_links(text):
    """在条目末尾追加 DOI / arXiv 链接；已有对应 http(s) 链接则不重复包。"""
    out = text.rstrip()
    lower = out.lower()
    links = []
    urls = HTTP_RE.findall(out)

    m = DOI_RE.search(out)
    doi = _clean_doi(m.group(0)) if m else ''
    if doi and len(doi) > 6 and 'doi.org/' not in lower and not any(doi in u for u in urls):
        links.append('[DOI](https://doi.org/%s)' % quote(doi, safe='/-._~'))

    if 'arxiv.org/abs/' not in lower and 'arxiv.org/pdf/' not in lower:
        m = ARXIV_RE.search(out)
        if m:
            links.append('[arXiv](https://arxiv.org/abs/%s%s)' % (m.group(1), m.group(2) or ''))

    if links:
        out += ' ' + ' '.join(links)
    return out


def find_section(text):
    """定位最后一个参考文献标题，返回 body / heading / level；找不到返回 None。"""
    text = _norm_text(text)
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        matches = list(LOOSE_HEADING_RE.finditer(text))
    if not matches:
        return None
    m = matches[-1]
    level = len(m.group(1))
    start = m.end()
    end = len(text)
    for hm in ANY_HEADING_RE.finditer(text, start):
        if len(hm.group(1)) <= level:
            end = hm.start()
            break
    body = text[start:end].strip('\n')
    return {'body': body, 'heading': m.group(0).strip(), 'level': level}


def _split_prefixed(lines):
    """按 [1] / 1. / 1) / $^{1}$ / 裸数字切条目；无前缀行并入上一条或 notes。"""
    entries = []
    notes = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _is_note_line(line):
            notes.append(line)
            continue
        hit = _match_prefix(line)
        if hit:
            end, num, kind = hit
            # 裸数字很容易把页码/年份（如 "560 [10] ..."、"2010 PASP..."）当编号；
            # 只有它跟在上一条编号后面（或从 1 开始）时才认。
            expected = entries[-1]['num'] + 1 if entries and entries[-1].get('num') else 1
            if kind == 'bare' and num != expected:
                hit = None
            else:
                body = line[end:].strip()
                if body:
                    entries.append({'text': body, 'num': num})
                continue
        if entries:
            if _looks_like_tail_note(line):
                notes.append(line)
            else:
                entries[-1]['text'] = (entries[-1]['text'] + ' ' + line).strip()
        # 没有前缀、且还没进入第一条：这是段首说明，不塞进 notes，
        # 否则会和无前缀文献表兜底冲突（WEAVE 那种 439 条全被当 notes）。
    return entries, notes


def _split_blocks(body):
    """按空行分块兜底；适用于没有数字前缀的 author–year 文献表。"""
    entries = []
    notes = []
    for block in BLOCK_SPLIT_RE.split(body):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_is_note_line(ln) for ln in lines):
            notes.extend(lines)
            continue
        if len(lines) == 1 and _looks_like_tail_note(lines[0]):
            notes.append(lines[0])
            continue
        text = ' '.join(lines)
        if _is_note_line(lines[0]):
            notes.append(lines[0])
            text = ' '.join(lines[1:]).strip()
            if not text:
                continue
        hit = _match_prefix(text)
        if hit:
            text = text[hit[0]:].strip()
        if text:
            entries.append({'text': text, 'num': None})
    return entries, notes


def parse_references(text):
    """
    解析 full.md，返回：
      {ok, reason, count, entries:[{text,num}], notes:[str], hash, section}
    失败只返回 ok=False，不抛异常（供 build_entry / CLI / verify_vault 共用）。
    """
    text = _norm_text(text)
    section = find_section(text)
    if section is None:
        return {'ok': False, 'reason': 'no-heading', 'count': 0,
                'entries': [], 'notes': [], 'hash': '', 'section': None}

    body = section['body']
    if not body.strip():
        return {'ok': False, 'reason': 'empty-section', 'count': 0,
                'entries': [], 'notes': [], 'hash': '', 'section': section}

    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    entries, notes = _split_prefixed(lines)
    if len(entries) < 3:
        entries2, notes2 = _split_blocks(body)
        if len(entries2) >= len(entries):
            entries = entries2
            # 兜底模式下 notes 以分块结果为准，避免把前缀模式收集的
            # 脚注重复计入；notes2 为空时保留前缀模式识别的脚注。
            merged = notes2 + [n for n in notes if n not in notes2]
            notes = merged

    if len(entries) < 3:
        return {'ok': False, 'reason': 'too-few(%d)' % len(entries), 'count': len(entries),
                'entries': entries, 'notes': notes, 'hash': '', 'section': section}
    if len(entries) > MAX_REFERENCES:
        return {'ok': False,
                'reason': 'too-many(%d > %d)' % (len(entries), MAX_REFERENCES),
                'count': len(entries), 'entries': entries, 'notes': notes,
                'hash': '', 'section': section}

    # 末尾混进来的出版方说明/排版说明不占编号。
    clean_entries = [e for e in entries if not _looks_like_tail_note(e['text'])]
    if len(clean_entries) >= 3:
        entries = clean_entries

    digest = hashlib.sha1(body.strip().encode('utf-8')).hexdigest()[:16]
    return {'ok': True, 'reason': '', 'count': len(entries),
            'entries': entries, 'notes': notes, 'hash': digest, 'section': section}


# ── L1：在线补全（Semantic Scholar → Crossref）───────────────────────
# 只在 full.md 没有可用参考文献段、且条目有 DOI/arXiv 时才用。
# 任何网络/解析失败都返回 ok=False，由调用方静默回退，绝不影响入库。
S2_REF_URL = 'https://api.semanticscholar.org/graph/v1/paper/{pid}/references'
S2_REF_FIELDS = 'title,authors,year,venue,externalIds,url'
S2_REF_LIMIT = 1000
CROSSREF_WORK_URL = 'https://api.crossref.org/works/{doi}'
API_TIMEOUT = 15
# 单篇在线补全的总时限：在线是尽力而为，绝不能把 ingest / --all 拖慢到分钟级。
ONLINE_BUDGET = 12
# S2 免费共享池很挤，串行 + 最小间隔，别把批量跑成 429。
_ONLINE_LAST = [0.0]
ONLINE_MIN_INTERVAL = 1.2
# 连续被 429 后整轮跳过 S2，避免 8 篇每篇都等一轮退避。
_S2_COOLDOWN_UNTIL = [0.0]
S2_COOLDOWN = 180
ONLINE_NEGATIVE_TTL = 7 * 86400
ONLINE_MAX_AUTHORS = 6
# S2 个别记录的 title 其实是摘要片段；超过这个长度基本可以判定不是文献标题。
ONLINE_MAX_TITLE = 320
ONLINE_SOURCES = ('s2', 'crossref')
ONLINE_CACHE_NAME = '.refs-online.json'
UA = 'PaperDepot/1.0 (+https://github.com/HUAWEIYYLS/paperdepot)'


class _RateLimited(RuntimeError):
    pass


def read_ids(index_path):
    """从 index.md frontmatter 取 doi / arxiv（去引号、去 URL 前缀、小写 DOI）。"""
    ids = {'doi': '', 'arxiv': ''}
    text = _read_text(index_path)
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
    if not m:
        return ids
    fm = m.group(1)
    d = re.search(r'^doi:\s*(.+?)\s*$', fm, re.M)
    if d:
        v = d.group(1).strip().strip('"').strip("'").lower()
        ids['doi'] = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', v).strip()
    a = re.search(r'^arxiv:\s*(.+?)\s*$', fm, re.M)
    if a:
        v = a.group(1).strip().strip('"').strip("'")
        v = re.sub(r'^(?:arxiv:|https?://arxiv\.org/(?:abs|pdf)/)', '', v, flags=re.I)
        ids['arxiv'] = re.sub(r'\.pdf$', '', v, flags=re.I).strip()
    return ids


def _ids_key(ids):
    if ids.get('doi'):
        return 'doi:' + ids['doi']
    if ids.get('arxiv'):
        return 'arxiv:' + ids['arxiv']
    return ''


def _online_hash(ids):
    """在线结果的幂等键：只由 ids 决定，不必联网就能算出来比对。"""
    key = _ids_key(ids)
    if not key:
        return ''
    return hashlib.sha1(('online|' + key).encode('utf-8')).hexdigest()[:16]


def _online_allowed(online):
    """online: None=自动（默认允许）, True=强制允许, False=禁用。"""
    if online is False:
        return False
    if online is True:
        return True
    return (os.environ.get('PAPERDEPOT_NO_ONLINE_REFS') or '').strip().lower() not in (
        '1', 'true', 'yes', 'on')


def _online_gate():
    gap = time.time() - _ONLINE_LAST[0]
    if gap < ONLINE_MIN_INTERVAL:
        time.sleep(ONLINE_MIN_INTERVAL - gap)
    _ONLINE_LAST[0] = time.time()


def _http_json(url, accept='application/json', timeout=None, retries=1):
    """轻量 GET JSON：最多重试 retries 次，429 只短暂等待。

    不复用 fetch_metadata.http_get：那里的 429 退避是给元数据主链路用的
    （5/10/15/20 秒），用在「可有可无」的在线补全上会把批量拖到几分钟。
    """
    timeout = API_TIMEOUT if timeout is None else timeout
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': accept})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 429:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise _RateLimited('HTTP 429') from exc
            if 400 <= exc.code < 500:
                raise
            if attempt < retries:
                time.sleep(1.0)
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(1.0)
    raise last if last else RuntimeError('request failed')


def _short_authors(names):
    names = [str(n).strip() for n in (names or []) if n and str(n).strip()]
    if not names:
        return ''
    if len(names) > ONLINE_MAX_AUTHORS:
        return ', '.join(names[:ONLINE_MAX_AUTHORS]) + ', et al.'
    return ', '.join(names)


def _link_for(doi='', arxiv=''):
    if doi:
        return '[DOI](https://doi.org/%s)' % quote(doi, safe='/-._~')
    if arxiv:
        return '[arXiv](https://arxiv.org/abs/%s)' % arxiv
    return ''


def _clean_venue(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip().strip(' ,;:.')


def _compose_ref(authors, title, venue, year, link=''):
    """拼一条可读的文献：作者. 标题. 期刊, 年份. [链接]"""
    parts = []
    if authors:
        parts.append(authors.rstrip('.') + '.')
    t = (title or '').strip()
    if t:
        parts.append(t if t.endswith('.') else t + '.')
    tail = ', '.join(str(x) for x in (_clean_venue(venue), year) if x)
    if tail:
        parts.append(tail.rstrip('.') + '.')
    text = ' '.join(parts).strip()
    if link:
        text = (text + ' ' + link).strip()
    return text


def _tidy(text):
    """在线来源的常见粘连：`J.Shi` / `States1965` / 多余空白。只做无损的空格修补。"""
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    text = re.sub(r'\.(?=[A-Z])', '. ', text)              # J.Shi → J. Shi
    text = re.sub(r'([a-z])(\d{4})\b', r'\1 \2', text)     # States1965 → States 1965
    return re.sub(r'\s+', ' ', text).strip()


def _entries_from_s2(payload):
    entries = []
    for item in (payload.get('data') or []):
        paper = item.get('citedPaper') or {}
        title = re.sub(r'\s+', ' ', str(paper.get('title') or '')).strip()
        if not title or len(title) > ONLINE_MAX_TITLE:
            continue
        ids = paper.get('externalIds') or {}
        doi = str(ids.get('DOI') or '').strip()
        arxiv = str(ids.get('ArXiv') or '').strip()
        text = _compose_ref(
            _short_authors([a.get('name') for a in (paper.get('authors') or [])]),
            title, re.sub(r'\s+', ' ', str(paper.get('venue') or '')).strip(),
            paper.get('year'), _link_for(doi, arxiv))
        text = _tidy(text)
        if len(text) < 12:
            continue
        entries.append({'text': text, 'num': len(entries) + 1})
    return entries


def _compose_crossref(ref):
    """Crossref reference[] 常常只有 author/journal/volume/page/year（没有标题），
    按 ADS 风格拼成「作者. 期刊, 卷, 页 (年).」，比丢掉整条更有用。"""
    author = str(ref.get('author') or '').strip()
    title = str(ref.get('article-title') or ref.get('volume-title') or '').strip()
    journal = str(ref.get('journal-title') or '').strip()
    year = str(ref.get('year') or '').strip()
    volume = str(ref.get('volume') or '').strip()
    page = str(ref.get('first-page') or '').strip()

    parts = []
    if author:
        parts.append(author.rstrip('.') + '.')
    if title:
        parts.append(title if title.endswith('.') else title + '.')
    tail = [x for x in (journal, volume, page) if x]
    if tail:
        parts.append(', '.join(tail) + (' (%s).' % year if year else '.'))
    elif year:
        parts.append(year + '.')
    return ' '.join(parts).strip()


def _entries_from_crossref(work):
    refs = ((work.get('message') or {}).get('reference') or [])
    entries = []
    for ref in refs:
        raw = (ref.get('unstructured') or '').strip()
        doi = str(ref.get('DOI') or '').strip()
        if raw:
            text = raw
            if doi and 'doi.org/' not in text.lower() and doi.lower() not in text.lower():
                text = text.rstrip('.') + '. ' + _link_for(doi)
        else:
            text = _compose_crossref(ref)
            if text and doi:
                text = text + ' ' + _link_for(doi)
        text = _tidy(text)
        # 只有年份/期刊、完全没有可读信息的条目直接丢掉
        if len(text) < 12:
            continue
        entries.append({'text': text, 'num': len(entries) + 1})
    return entries


def fetch_online(doi='', arxiv='', budget=None):
    """
    在线补全参考文献。返回 {ok, source, entries, count, reason}；失败不抛异常。
    source ∈ {'s2','crossref'}；reason ∈ {'no-id','no-online-refs','rate-limited','budget'}。
    """
    ids = {'doi': doi, 'arxiv': arxiv}
    if not _ids_key(ids):
        return {'ok': False, 'source': '', 'entries': [], 'count': 0,
                'reason': 'no-id', 'transient': False}

    deadline = time.time() + (ONLINE_BUDGET if budget is None else budget)
    answered = False  # 是否至少有一个源返回了 200（决定能不能缓存否定结果）

    def _left():
        return max(0.0, deadline - time.time())

    def _fail(reason):
        return {'ok': False, 'source': '', 'entries': [], 'count': 0,
                'reason': reason, 'transient': not answered}

    pids = []
    if doi:
        pids.append('DOI:' + doi)
    if arxiv:
        pids.append('ARXIV:' + arxiv)
    for pid in pids:
        if _left() <= 0:
            return _fail('budget')
        if time.time() < _S2_COOLDOWN_UNTIL[0]:
            break  # 本轮已确认被限流，直接换 Crossref
        url = (S2_REF_URL.format(pid=quote(pid, safe=':/'))
               + '?fields=' + S2_REF_FIELDS + '&limit=%d' % S2_REF_LIMIT)
        try:
            _online_gate()
            payload = _http_json(url, timeout=min(API_TIMEOUT, max(2.0, _left())))
        except _RateLimited:
            _S2_COOLDOWN_UNTIL[0] = time.time() + S2_COOLDOWN
            break
        except Exception:
            continue
        answered = True
        entries = _entries_from_s2(payload)
        if len(entries) >= 3:
            return {'ok': True, 'source': 's2', 'entries': entries,
                    'count': len(entries), 'reason': '', 'transient': False}

    if doi and _left() > 0:
        url = CROSSREF_WORK_URL.format(doi=quote(doi, safe='/'))
        try:
            _online_gate()
            work = _http_json(url, timeout=min(API_TIMEOUT, max(2.0, _left())))
            answered = True
            entries = _entries_from_crossref(work)
        except Exception:
            entries = []
        if len(entries) >= 3:
            return {'ok': True, 'source': 'crossref', 'entries': entries,
                    'count': len(entries), 'reason': '', 'transient': False}

    return _fail('budget' if _left() <= 0 else 'no-online-refs')


def _online_cache_path(entry_dir):
    return os.path.join(entry_dir, ONLINE_CACHE_NAME)


def _read_online_negative(entry_dir, ids):
    """负缓存：同一个条目短期内不重复联网（只缓存「确实没有」，不缓存网络错误）。"""
    try:
        data = json.loads(_read_text(_online_cache_path(entry_dir)) or '{}')
    except Exception:
        return ''
    if data.get('ids') != _ids_key(ids):
        return ''
    try:
        if time.time() - float(data.get('at') or 0) > ONLINE_NEGATIVE_TTL:
            return ''
    except (TypeError, ValueError):
        return ''
    return str(data.get('reason') or 'no-online-refs')


def _write_online_negative(entry_dir, ids, reason):
    try:
        _atomic_write(_online_cache_path(entry_dir), json.dumps(
            {'ids': _ids_key(ids), 'reason': reason, 'at': time.time()},
            ensure_ascii=False, indent=1) + '\n')
    except OSError:
        pass


def _clear_online_negative(entry_dir):
    try:
        p = _online_cache_path(entry_dir)
        if os.path.isfile(lp(p)):
            os.remove(lp(p))
    except OSError:
        pass


def render_references(title, parsed):
    """生成 references.md 全文。"""
    alias = str(title or 'Untitled').replace('|', '｜').replace(']]', '')
    entries = parsed['entries']
    source = parsed.get('source') or 'full.md'
    if source == 'full.md':
        note = '共 %d 条，摘自 full.md，未改写原文。' % len(entries)
    else:
        label = {'s2': 'Semantic Scholar', 'crossref': 'Crossref'}.get(source, source)
        note = ('共 %d 条，原文没有可用的参考文献段，由 %s 结构化补全；'
                '条目为机器整理，顺序与格式可能与原文不同。' % (len(entries), label))
    lines = [
        '---',
        'title: %s' % json.dumps('参考文献', ensure_ascii=False),
        'paper: %s' % json.dumps('[[index|%s]]' % alias, ensure_ascii=False),
        'count: %d' % len(entries),
        'source: "%s"' % source,
        'source_hash: "%s"' % parsed['hash'],
        'generated_by: "paperdepot/make_references.py"',
        'generated_at: "%s"' % time.strftime('%Y-%m-%dT%H:%M:%S'),
        '---',
        '',
        '# 📚 参考文献',
        '',
        note,
        '',
    ]
    for i, entry in enumerate(entries, 1):
        lines.append('%d. %s' % (i, _append_links(entry['text'])))
    if parsed['notes']:
        lines += ['', '## 注释', '']
        lines += list(parsed['notes'])
    return '\n'.join(lines).rstrip() + '\n'


# ── 写盘 / index 标记 ─────────────────────────────────────────────────
def _atomic_write(path, text):
    tmp = path + '.tmp'
    with io.open(lp(tmp), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    # 云同步盘（华为云盘/Obsidian 打开）偶尔短暂锁住目标文件，重试几次。
    last = None
    for attempt in range(6):
        try:
            os.replace(lp(tmp), lp(path))
            return
        except OSError as exc:
            last = exc
            transient = isinstance(exc, PermissionError) or getattr(exc, 'winerror', None) in (5, 32)
            if not transient:
                break
            time.sleep(0.15 * (attempt + 1))
    try:
        os.remove(lp(tmp))
    except OSError:
        pass
    raise last


def _read_text(path):
    try:
        return io.open(lp(path), encoding='utf-8', errors='replace').read()
    except OSError:
        return ''


def _read_refs_meta(refs_path):
    """读出现有 references.md 的 source / source_hash / count，用于幂等判定。"""
    text = _read_text(refs_path)
    meta = {'hash': '', 'source': '', 'count': 0}
    h = re.search(r'^source_hash:\s*["\']?([0-9a-f]{16})["\']?', text, re.M)
    if h:
        meta['hash'] = h.group(1)
    s = re.search(r'^source:\s*["\']?([^"\'\n]+?)["\']?\s*$', text, re.M)
    if s:
        meta['source'] = s.group(1).strip()
    c = re.search(r'^count:\s*(\d+)', text, re.M)
    if c:
        meta['count'] = int(c.group(1))
    return meta


def _refs_marker(count):
    return ('<!-- paperdepot:refs:start -->\n'
            '[[references|📚 参考文献（%d 条）]]\n'
            '<!-- paperdepot:refs:end -->' % count)


def _has_refs_marker(index_path):
    return '<!-- paperdepot:refs:start -->' in _read_text(index_path)


def _upsert_refs_marker(index_path, count):
    """已存在则原位替换（清理重复），否则追加到 index.md 末尾。"""
    text = _read_text(index_path)
    block = _refs_marker(count)
    if REFS_MARKER_RE.search(text):
        return REFS_MARKER_RE.sub(block, text)
    return text.rstrip() + '\n\n' + block + '\n'


# ── 库内引用匹配：把引文连回库里已收录的论文 ─────────────────────────
# 文献库里最有信息量的边是「论文 → 论文」（引用关系）。references.md 里的引文
# 是纯文本，图谱看不到这些边，所以这里在 index.md 写一个 cites 标记块，把命中的
# 库内论文变成 wikilink。标记块由 apply_summary 的 MARKER_BLOCK_RE 保留。
CITES_MARKER_RE = re.compile(
    r'<!-- paperdepot:cites:start -->.*?<!-- paperdepot:cites:end -->', re.S)
# 匹配只用「目录名 / frontmatter title」，不用 aliases：alias 常是「最优提取」
# 「blind deconvolution」这种宽泛词组，会把任何含该词组的引文都吸过来。
# 纯包含匹配要求标题够长、词够多；短标题只有在引文里被引号完整括起时才算命中。
CITES_MIN_TITLE = 25
CITES_MIN_WORDS = 4
CITES_QUOTED_MIN = 10
TITLE_INDEX_CACHE = {}
QUOTE_RE = re.compile(r'[“"「『]([^”"」』]{6,})[”"」』]')


def _norm_title(text):
    """把标题/引文归一成可比较形式：去公式、去转义、去标点、压空白、转小写。"""
    s = text or ''
    s = re.sub(r'\$[^$]*\$', ' ', s)
    s = s.replace('\\', ' ')
    s = re.sub(r'[^\w]+', ' ', s, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', s).strip().lower()


def _title_variants(index_path, dir_name):
    """一个条目可被引文命中的标题写法：目录名 + frontmatter title（不含 aliases）。"""
    out = [dir_name]
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', _read_text(index_path), re.S)
    if m:
        t = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', m.group(1), re.M)
        if t:
            out.append(t.group(1).strip().strip('"\''))
    return out


def _quoted_norms(text):
    """引文里被引号完整括起的片段（归一化）——引号本身就是「这是标题」的信号。"""
    return [n for n in (_norm_title(m) for m in QUOTE_RE.findall(text or '')) if n]


def vault_title_index(vault):
    """vault → [(目录名, 归一化标题, 展示标题)]；按库路径缓存，--all 只扫一次。"""
    if not vault:
        return []
    key = os.path.abspath(vault)
    if key in TITLE_INDEX_CACHE:
        return TITLE_INDEX_CACHE[key]
    rows = []
    seen = set()
    for entry_dir in _iter_entries(key):
        dir_name = os.path.basename(entry_dir)
        index_path = os.path.join(entry_dir, 'index.md')
        if not os.path.isfile(lp(index_path)):
            continue
        display = read_title(index_path)
        for cand in _title_variants(index_path, dir_name):
            norm = _norm_title(cand)
            if len(norm) < CITES_QUOTED_MIN:
                continue
            if (dir_name, norm) in seen:
                continue
            seen.add((dir_name, norm))
            rows.append((dir_name, norm, display))
    TITLE_INDEX_CACHE[key] = rows
    return rows


def _strong_match(norm):
    """够长、够多词才允许「整串出现在引文任意位置」这种弱证据匹配。"""
    return len(norm) >= CITES_MIN_TITLE and len(norm.split()) >= CITES_MIN_WORDS


def match_in_vault(entries, vault, self_dir=''):
    """
    把引文条目匹配回库内论文。

    每条引文只认一个目标（取命中的最长标题）：一条引文就是一本书/一篇文章，
    取最长能避开「标题 A 是标题 B 子串」造成的重复命中。
    证据强度：引号内完整等强于「整串出现在句中」，短标题只接受前者。
    返回 [(目录名, 展示标题)]，按引文顺序去重。
    """
    index = vault_title_index(vault)
    if not index:
        return []
    hits = []
    seen = set()
    for entry in entries:
        raw = entry.get('text') or ''
        text = _norm_title(raw)
        if len(text) < CITES_QUOTED_MIN:
            continue
        quoted = _quoted_norms(raw)
        best = None
        best_rank = 0
        for dir_name, norm, display in index:
            if dir_name == self_dir or dir_name in seen:
                continue
            if norm in quoted:
                rank = 2
            elif _strong_match(norm) and norm in text:
                rank = 1
            else:
                continue
            # 先比证据强度，再比标题长度（长标题更具体）
            if rank > best_rank or (rank == best_rank and (best is None or len(norm) > len(best[1]))):
                best = (dir_name, norm, display)
                best_rank = rank
        if best is not None:
            seen.add(best[0])
            hits.append((best[0], best[2]))
    return hits



def _cites_block(hits):
    """生成 cites 标记块；没有命中时返回空串（调用方负责移除旧块）。"""
    if not hits:
        return ''
    lines = [
        '<!-- paperdepot:cites:start -->',
        '## 🔗 库内引用（%d 篇）' % len(hits),
        '',
    ]
    for dir_name, display in hits:
        alias = str(display or dir_name).replace('|', '｜').replace(']]', '')
        lines.append('- [[1-Papers/%s/index|%s]]' % (dir_name, alias))
    lines.append('<!-- paperdepot:cites:end -->')
    return '\n'.join(lines)


def _cites_dirty(text, block):
    """现有 index.md 的 cites 块是否需要重写。"""
    m = CITES_MARKER_RE.search(text)
    if not block:
        return m is not None
    if m is None:
        return True
    return m.group(0).strip() != block.strip()


def _upsert_cites(text, block):
    """在 index.md 文本里写入 / 替换 / 移除 cites 标记块。"""
    if not block:
        if not CITES_MARKER_RE.search(text):
            return text
        stripped = CITES_MARKER_RE.sub('', text)
        stripped = re.sub(r'\n{3,}', '\n\n', stripped)
        return stripped.rstrip() + '\n'
    if CITES_MARKER_RE.search(text):
        return CITES_MARKER_RE.sub(lambda _m: block, text)
    return text.rstrip() + '\n\n' + block + '\n'



def read_title(index_path):
    """从 index.md frontmatter / 一级标题取标题，供 CLI 使用。"""
    text = _read_text(index_path)
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if line.startswith('title:'):
                v = line[6:].strip().strip('"').strip("'")
                if v:
                    return v
    m = re.search(r'^#\s+(.+?)\s*$', text, re.M)
    if m:
        return m.group(1).strip()
    return os.path.basename(os.path.dirname(index_path))


def build_for_entry(entry_dir, title, full_md=None, force=False, online=None,
                    vault=None, cites=True):
    """
    生成 <entry_dir>/references.md 并维护 index.md 的 refs / cites 标记块。

    full_md: 已读好的 full.md 文本；为 None 时从 entry_dir/full.md 读取。
    online:  None=自动（离线失败且有条目 DOI/arXiv 时联网补全）
             True=允许联网；False=只用离线
    vault:   库根目录；None 时从 entry_dir 反推（1-Papers/<条目> → 库根）
    cites:   是否把引文匹配回库内论文（写 cites 标记块）
    返回 dict（ok / skipped / reason / count / hash / source / cites / path）；失败不抛异常。
    """
    entry_dir = os.path.abspath(entry_dir)
    refs_path = os.path.join(entry_dir, 'references.md')
    index_path = os.path.join(entry_dir, 'index.md')
    if vault is None:
        # entry_dir 形如 <vault>/1-Papers/<条目>
        vault = os.path.dirname(os.path.dirname(entry_dir))
    self_dir = os.path.basename(entry_dir)

    if full_md is None:
        full_path = os.path.join(entry_dir, 'full.md')
        if not os.path.isfile(lp(full_path)):
            return {'ok': False, 'reason': 'full.md missing', 'count': 0}
        full_md = _read_text(full_path)

    if not os.path.isfile(lp(index_path)):
        return {'ok': False, 'reason': 'index.md missing', 'count': 0}

    has_meta = os.path.isfile(lp(refs_path))
    meta = _read_refs_meta(refs_path) if has_meta else {'hash': '', 'source': '', 'count': 0}
    has_marker = _has_refs_marker(index_path)

    def _finish(parsed, source):
        parsed['source'] = source
        hits = match_in_vault(parsed['entries'], vault, self_dir) if cites else []
        block = _cites_block(hits)
        current = _read_text(index_path)
        if (not force and has_meta and has_marker
                and not _cites_dirty(current, block)):
            if meta['hash'] == parsed['hash'] and meta['source'] == source:
                return {'ok': True, 'skipped': True, 'count': parsed['count'],
                        'hash': parsed['hash'], 'source': source, 'cites': len(hits),
                        'path': refs_path}
        _atomic_write(refs_path, render_references(title, parsed))
        new_index = _upsert_refs_marker(index_path, len(parsed['entries']))
        new_index = _upsert_cites(new_index, block)
        if new_index:
            _atomic_write(index_path, new_index)
        return {'ok': True, 'skipped': False, 'count': len(parsed['entries']),
                'hash': parsed['hash'], 'source': source, 'cites': len(hits),
                'path': refs_path}


    # 1) 离线（full.md 有规范参考文献段）——绝大多数条目走这里，不联网
    parsed = parse_references(full_md)
    if parsed['ok']:
        return _finish(parsed, 'full.md')

    # 2) 在线兜底：需要有 DOI / arXiv
    ids = read_ids(index_path)
    if not _online_allowed(online) or not _ids_key(ids):
        return {'ok': False, 'reason': parsed['reason'], 'count': parsed['count']}

    want = _online_hash(ids)
    # 在线结果的 hash 由 ids 决定，命中时无需联网即可 SKIP
    if not force and has_meta and has_marker:
        if meta['hash'] == want and meta['source'] in ONLINE_SOURCES:
            return {'ok': True, 'skipped': True, 'count': meta['count'],
                    'hash': want, 'source': meta['source'], 'path': refs_path}

    if not force:
        negative = _read_online_negative(entry_dir, ids)
        if negative:
            return {'ok': False, 'reason': negative, 'count': 0}

    res = fetch_online(ids['doi'], ids['arxiv'])
    if not res['ok']:
        # 只有「两个源都明确说没有」才缓存否定结果；限流/超时下次还要重试。
        if not res.get('transient'):
            _write_online_negative(entry_dir, ids, res['reason'])
        return {'ok': False, 'reason': res['reason'], 'count': 0}
    _clear_online_negative(entry_dir)
    return _finish({'ok': True, 'reason': '', 'notes': [], 'entries': res['entries'],
                    'count': res['count'], 'hash': want, 'section': None}, res['source'])


# ── CLI ───────────────────────────────────────────────────────────────
def _iter_entries(vault):
    papers = os.path.join(vault, '1-Papers')
    if not os.path.isdir(lp(papers)):
        return
    for name in sorted(os.listdir(lp(papers))):
        path = os.path.join(papers, name)
        if os.path.isdir(lp(path)) and not name.startswith('_'):
            yield path


def _print_parse(label, parsed):
    if parsed['ok']:
        print('%s: ok count=%d notes=%d hash=%s' % (
            label, parsed['count'], len(parsed['notes']), parsed['hash']))
        if parsed['entries']:
            print('  first: %s' % parsed['entries'][0]['text'][:160])
            print('  last : %s' % parsed['entries'][-1]['text'][:160])
    else:
        print('%s: FAIL reason=%s count=%d' % (label, parsed['reason'], parsed['count']))


def main():
    ap = argparse.ArgumentParser(description='从 full.md 的参考文献段生成 references.md')
    ap.add_argument('--vault')
    ap.add_argument('--entry')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--from-files')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--online', action='store_true', help='允许联网补全（默认：离线失败且有条目 ID 时才联网）')
    ap.add_argument('--offline', action='store_true', help='只用 full.md，不联网')
    ap.add_argument('--doi', default='', help='配合 --from-files：直接给 DOI 试在线补全')
    ap.add_argument('--arxiv', default='', help='配合 --from-files：直接给 arXiv id 试在线补全')
    ap.add_argument('--no-cites', action='store_true',
                    help='不把引文匹配回库内论文（不写 index.md 的 cites 标记块）')
    args = ap.parse_args()

    if args.online and args.offline:
        ap.error('--online 与 --offline 不能同时使用')
    online = True if args.online else (False if args.offline else None)

    if args.from_files:
        if args.vault or args.entry or args.all:
            ap.error('--from-files 不能与 --vault / --entry / --all 同时使用')
        full_path = args.from_files
        if not os.path.isfile(lp(full_path)):
            print('full.md 不存在：%s' % full_path, file=sys.stderr)
            return 2
        parsed = parse_references(_read_text(full_path))
        if parsed['ok']:
            parsed['source'] = 'full.md'
            _print_parse(full_path, parsed)
            print('\n--- preview ---')
            print(render_references('调试标题', parsed)[:4000])
            return 0
        _print_parse(full_path, parsed)
        if not (args.doi or args.arxiv):
            return 1
        if not _online_allowed(online):
            print('离线模式（--offline / PAPERDEPOT_NO_ONLINE_REFS），跳过在线补全', file=sys.stderr)
            return 1
        print('\n--- 尝试在线补全 ---')
        res = fetch_online(args.doi.strip(), args.arxiv.strip())
        if not res['ok']:
            print('在线补全失败：%s' % res['reason'], file=sys.stderr)
            return 1
        print('source=%s count=%d' % (res['source'], res['count']))
        print('  first: %s' % res['entries'][0]['text'][:160])
        print('  last : %s' % res['entries'][-1]['text'][:160])
        out = render_references('调试标题', {'entries': res['entries'], 'notes': [],
                                            'hash': _online_hash({'doi': args.doi.strip(),
                                                                  'arxiv': args.arxiv.strip()}),
                                            'source': res['source']})
        print('\n--- preview ---')
        print(out[:4000])
        return 0

    if not args.vault:
        ap.error('需要 --vault <vault>（或使用 --from-files）')
    if not os.path.isdir(lp(args.vault)):
        print('vault 不存在：%s' % args.vault, file=sys.stderr)
        return 2

    if args.all and args.entry:
        ap.error('--all 与 --entry 不能同时使用')

    def _label(res):
        if res.get('skipped'):
            return 'SKIP'
        return 'OK[%s]' % res.get('source', '?')

    started = time.time()
    if args.entry:
        entry_dir = os.path.join(args.vault, '1-Papers', args.entry)
        if not os.path.isdir(lp(entry_dir)):
            print('条目不存在：%s' % entry_dir, file=sys.stderr)
            return 2
        title = read_title(os.path.join(entry_dir, 'index.md'))
        res = build_for_entry(entry_dir, title, force=args.force, online=online,
                              vault=args.vault, cites=not args.no_cites)
        if res['ok']:
            print('%s: %s count=%d cites=%d' % (
                args.entry, _label(res), res['count'], res.get('cites', 0)))
            return 0
        print('%s: FAIL reason=%s' % (args.entry, res.get('reason')), file=sys.stderr)
        return 1

    if args.all:
        ok = skip = fail = 0
        online_used = 0
        cites_total = 0
        for entry_dir in _iter_entries(args.vault):
            name = os.path.basename(entry_dir)
            try:
                title = read_title(os.path.join(entry_dir, 'index.md'))
                res = build_for_entry(entry_dir, title, force=args.force, online=online,
                                      vault=args.vault, cites=not args.no_cites)
            except Exception as exc:  # 单篇兜底，绝不让批量中断
                res = {'ok': False, 'reason': 'exception: %s' % exc}
            if not res.get('ok'):
                fail += 1
                print('  ❌ %s  (%s)' % (name[:70], res.get('reason')))
                continue
            cites_total += res.get('cites', 0)
            if res.get('skipped'):
                skip += 1
                print('  ↷ %s  SKIP' % name[:70])
            else:
                ok += 1
                if res.get('source') in ONLINE_SOURCES:
                    online_used += 1
                print('  ✅ %s  (%d 条%s)' % (
                    name[:70], res.get('count', 0),
                    '，%s' % res['source'] if res.get('source') in ONLINE_SOURCES else ''))
        elapsed = time.time() - started
        print('\n完成：ok=%d skip=%d fail=%d（其中在线补全 %d）  库内引用 %d 条  耗时 %.1f 秒' % (
            ok, skip, fail, online_used, cites_total, elapsed))
        return 0 if fail == 0 else 1

    ap.error('需要 --entry <目录名> 或 --all')
    return 2


if __name__ == '__main__':
    sys.exit(main())
