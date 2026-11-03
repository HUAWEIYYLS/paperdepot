#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mineru_parse — 把 PDF 变成结构化产物（full.md + images/ + layout.json）

这是「Zotero 退场」后流水线的第一块积木。只负责"解析"，不负责"入库"。

设计要点（全部经本机实测验证）：
  1. 上传必须用 http.client，只发 Content-Length
     —— urllib / requests 会自动加 Content-Type，破坏 OSS 签名 → 403
  2. 轮询：3s 起步，5 分钟后 15s，30 分钟后 60s
  3. ZIP 下载：cdn-mineru.openxlab.org.cn 的 TLS 证书已过期，
     必须换成 mineru.oss-cn-shanghai.aliyuncs.com
  4. ZIP 内文件名带 UUID 前缀，不能用固定名，必须 glob
  5. 当前 API 版本（_version_name 3.4.4）**没有 manifest.json**，
     版面结构在 layout.json 的 pdf_info[] 里

缓存目录：vault/.mineru-cache/<id>/   （点开头，Obsidian 不索引）

用法：
    python mineru_parse.py <pdf路径>
    python mineru_parse.py <pdf路径> --keep-zip
    python mineru_parse.py <pdf路径> --out <目录>
"""
import argparse
import glob
import hashlib
import http.client
import io
import json
import os
import re
import shutil
import sys
import time
import zipfile
from urllib.parse import urlparse
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 配置 ──────────────────────────────────────────────────────────────
def _load_api_key() -> str:
    """按优先级取 MinerU key：环境变量 → config/secrets.local.json（不进 git）。"""
    key = (os.environ.get('MINERU_API_KEY') or '').strip()
    if key:
        return key
    import json as _json
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'config', 'secrets.local.json')
    try:
        with io.open(p, encoding='utf-8') as f:
            return (_json.load(f).get('mineru_api_key') or '').strip()
    except Exception:
        return ''


API_KEY = _load_api_key()
BASE = 'https://mineru.net/api/v4'

# 已知 CDN 证书过期，只替换这一个 host
ZIP_HOST_FALLBACK = {
    'cdn-mineru.openxlab.org.cn': 'mineru.oss-cn-shanghai.aliyuncs.com',
}

# 轮询节奏（实测 16 页约 10 秒完成，这些阈值基本不会触发）
POLL_FAST, POLL_FAST_UNTIL = 3, 300
POLL_MED, POLL_MED_UNTIL = 15, 1800
POLL_SLOW = 60
TIMEOUT = 40 * 60

TERMINAL_CODES = {'A0202', 'A0211', '-60012', '-60013'}
DAILY_LIMIT_CODE = '-60018'

# 缓存放在项目工作区 cache/ 下，不放进 vault。
# （曾放在云盘 vault 的 .mineru-cache，占 1.25 GB 且全部参与云同步，已迁出）
DEFAULT_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'cache', 'mineru')

# 缓存格式版本：旧缓存（没有这个字段）按 1 处理，保持向后兼容；
# 未来格式变更时提升版本号，读到不认识的版本就重新解析。
CACHE_VERSION = 1


# ── 工具 ──────────────────────────────────────────────────────────────
class MineruError(RuntimeError):
    pass


class QuotaExhausted(MineruError):
    """每日配额用尽 —— 必须终止整个队列，不是单篇失败"""
    pass


def safe_ascii_name(name: str) -> str:
    """MinerU 后端不处理 unicode 文件名，必须 ASCII 化"""
    n = re.sub(r'[^\x20-\x7E]', '_', name)
    if not n.lower().endswith('.pdf'):
        n += '.pdf'
    return n


def pdf_fingerprint(path: str) -> str:
    """用内容 sha256 前 16 位做缓存 key，同一 PDF 不重复上传"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


def api_call(path: str, method: str = 'GET', payload=None, timeout: int = 120) -> dict:
    if not API_KEY:
        raise MineruError('未配置 MinerU key：请设置环境变量 MINERU_API_KEY，或写 config/secrets.local.json（模板见 config/secrets.example.json）')
    url = f'{BASE}{path}'
    headers = {'Authorization': f'Bearer {API_KEY}', 'Accept': '*/*'}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def upload_pdf(upload_url: str, pdf_path: str) -> None:
    """
    上传 PDF 到 OSS。

    关键：绝不能带 Content-Type。
      · urllib.request 带 data 时会自动加 application/x-www-form-urlencoded
      · requests 同样会加
      → 所以只能用 http.client 手工控制请求头
    skip_accept_encoding=True 也必要，否则加 Accept-Encoding 同样破坏签名。
    """
    with open(pdf_path, 'rb') as f:
        data = f.read()
    u = urlparse(upload_url)
    path_q = u.path + (('?' + u.query) if u.query else '')
    conn = http.client.HTTPSConnection(u.hostname, timeout=300)
    try:
        conn.putrequest('PUT', path_q, skip_accept_encoding=True)
        conn.putheader('Content-Length', str(len(data)))
        conn.endheaders()
        conn.send(data)
        resp = conn.getresponse()
        body = resp.read()
        if resp.status not in (200, 201):
            raise MineruError(
                f'上传失败 HTTP {resp.status}: {body[:400].decode("utf-8", "replace")}')
    finally:
        conn.close()


def download_zip(url: str, dst: str) -> None:
    """
    下载 ZIP。

    实测结论（2026-10-20，本机）：
      · cdn-mineru.openxlab.org.cn 的 TLS 证书确实已过期
      · 但把它换到 OSS host 后，经常 read timeout（OSS 对大 zip 慢）
      · 原 host 虽然证书过期，用系统 CA 却常常能下成功

    → 策略反过来：**先试原 host，失败再换**。
      文档说"必须替换"，实测替换反而更慢。
    """
    host = urlparse(url).hostname
    attempts = [(url, '原 host')]
    if host in ZIP_HOST_FALLBACK:
        attempts.append((url.replace(host, ZIP_HOST_FALLBACK[host], 1), 'OSS 备用 host'))

    last = None
    for target, label in attempts:
        try:
            with urllib.request.urlopen(target, timeout=90) as r:
                raw = r.read()
            if raw[:2] != b'PK':
                raise MineruError(f'{label} 返回的不是 ZIP')
            with open(dst, 'wb') as f:
                f.write(raw)
            if label != '原 host':
                print(f'       （原 host 失败，已用 {label}）')
            return
        except Exception as exc:
            last = exc
            if len(attempts) > 1 and label == attempts[0][1]:
                print(f'       原 host 失败（{type(exc).__name__}），换 OSS 重试…')
    raise MineruError(f'ZIP 下载失败: {last}')


# ── UI 摘要生成 ───────────────────────────────────────────────────────
def build_summary(out_dir: str) -> dict:
    """
    从解析产物里提取元信息。
    注意：产物文件名带 UUID 前缀，必须 glob。
    """
    info = {}
    md_path = os.path.join(out_dir, 'full.md')
    if os.path.isfile(md_path):
        text = open(md_path, encoding='utf-8', errors='replace').read()
        info['md_chars'] = len(text)
        m = re.search(r'^#\s+(.+)$', text, re.M)
        info['title'] = m.group(1).strip() if m else None
        info['image_refs'] = len(re.findall(r'!\[[^\]]*\]\(images/[^)]+\)', text))
    img_dir = os.path.join(out_dir, 'images')
    if os.path.isdir(img_dir):
        info['images'] = len([f for f in os.listdir(img_dir)
                              if os.path.isfile(os.path.join(img_dir, f))])
    for pat, key in ((config_glob('content_list.json'), 'content_list'),
                     (config_glob('model.json'), 'model'),
                     (config_glob('origin.pdf'), 'origin_pdf')):
        hits = glob.glob(os.path.join(out_dir, pat))
        if hits:
            info[key] = os.path.basename(hits[0])
    lay = os.path.join(out_dir, 'layout.json')
    if os.path.isfile(lay):
        try:
            d = json.load(open(lay, encoding='utf-8'))
            info['layout_pages'] = len(d.get('pdf_info', []))
            info['layout_version'] = d.get('_version_name')
        except Exception:
            pass
    mf = os.path.join(out_dir, 'manifest.json')
    info['has_manifest'] = os.path.isfile(mf)
    return info


def config_glob(suffix: str) -> str:
    return f'*_{suffix}'


# ── 主流程 ────────────────────────────────────────────────────────────
def cache_compatible(cached: dict) -> bool:
    """旧缓存没有 cache_version，按 1 处理（路径已在命中时改写，兼容搬家）。"""
    return cached.get('cache_version', 1) == CACHE_VERSION


def _cache_selftest() -> int:
    """离线自检：陈旧 out_dir 的缓存应命中、路径应改写，版本判定应正确。不消耗 API。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix='paperdepot-cache-selftest-')
    try:
        cache = os.path.join(tmp, 'cache')
        pdf = os.path.join(tmp, 'x.pdf')
        with open(pdf, 'wb') as f:
            f.write(b'%PDF-1.4 cache-selftest')
        fp = pdf_fingerprint(pdf)
        d = os.path.join(cache, fp)
        os.makedirs(os.path.join(d, 'images'))
        io.open(os.path.join(d, 'full.md'), 'w', encoding='utf-8').write('# t\n')
        open(os.path.join(d, '.done'), 'w').close()
        io.open(os.path.join(d, '.meta.json'), 'w', encoding='utf-8').write(
            json.dumps({'out_dir': 'D:\\gone\\old-cache', 'title': 't'}))
        s = parse(pdf, cache)
        assert s.get('from_cache') is True, s
        assert os.path.normcase(s['out_dir']) == os.path.normcase(d), (s['out_dir'], d)
        assert cache_compatible({}) and cache_compatible({'cache_version': CACHE_VERSION})
        assert not cache_compatible({'cache_version': CACHE_VERSION + 1})
        print('✅ cache selftest ok')
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def parse(pdf_path: str, cache_dir: str, keep_zip: bool = False) -> dict:
    if not os.path.isfile(pdf_path):
        raise MineruError(f'PDF 不存在: {pdf_path}')

    fp = pdf_fingerprint(pdf_path)
    out_dir = os.path.join(cache_dir, fp)
    done_marker = os.path.join(out_dir, '.done')

    # 缓存命中直接返回
    if os.path.isfile(done_marker):
        print(f'✅ 缓存命中: {out_dir}')
        try:
            cached = json.load(open(os.path.join(out_dir, '.meta.json'), encoding='utf-8'))
            if not cache_compatible(cached):
                print(f"  ⚠ 缓存版本不匹配（{cached.get('cache_version')} != {CACHE_VERSION}），重新解析")
            else:
                # .meta.json 里的 out_dir 是生成缓存时写入的绝对路径；缓存被搬过目录
                # （例如从云盘 vault 的 .mineru-cache 迁到仓库 cache/）后必须改回当前路径
                cached['out_dir'] = out_dir
                cached['from_cache'] = True
                cached['parse_seconds'] = 0.0
                if os.path.isfile(os.path.join(out_dir, 'full.md')):
                    return cached
                print('  ⚠ 缓存缺 full.md，重新解析')
        except Exception:
            pass

    os.makedirs(cache_dir, exist_ok=True)
    tmp_dir = os.path.join(cache_dir, f'_tmp_{fp}')
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)

    name = safe_ascii_name(os.path.basename(pdf_path))
    size_mb = os.path.getsize(pdf_path) / 1048576
    print(f'📄 {os.path.basename(pdf_path)}  ({size_mb:.2f} MB)')
    print(f'   上传名: {name}')

    # 1. 建批次
    print('  [1/4] 建批次…')
    resp = api_call('/file-urls/batch', 'POST', {
        'enable_formula': True,
        'enable_table': True,
        'language': 'ch',
        'model_version': 'vlm',
        'files': [{'name': name, 'is_ocr': False}],
    })
    if resp.get('code') != 0:
        raise MineruError(f'建批次失败: {resp}')
    batch_id = resp['data']['batch_id']
    upload_url = resp['data']['file_urls'][0]

    # 2. 上传
    print('  [2/4] 上传…')
    upload_pdf(upload_url, pdf_path)

    # 3. 轮询
    print('  [3/4] 解析中…')
    t0 = time.time()
    state = None
    result = None
    while True:
        elapsed = time.time() - t0
        if elapsed > TIMEOUT:
            raise MineruError(f'超时 {TIMEOUT}s')

        try:
            resp = api_call(f'/extract-results/batch/{batch_id}')
        except Exception as exc:
            print(f'    轮询异常: {exc}')
            time.sleep(POLL_FAST)
            continue

        code = resp.get('code')
        if code != 0:
            c = str(code)
            if c == DAILY_LIMIT_CODE:
                raise QuotaExhausted('每日配额用尽（-60018）—— 必须停止整个队列，明日再跑')
            if c in TERMINAL_CODES:
                raise MineruError(f'终态错误 {c}: {resp.get("msg")}')
            time.sleep(POLL_FAST)
            continue

        items = resp['data'].get('extract_result') or []
        if not items:
            time.sleep(POLL_FAST)
            continue

        r0 = items[0]
        st = r0.get('state')
        if st != state:
            print(f'       [ {elapsed:5.1f}s ] {st}')
            state = st

        if st == 'done':
            result = r0
            break
        if st == 'failed':
            raise MineruError(f'解析失败: {r0.get("err_msg")}')

        prog = r0.get('extract_progress') or {}
        if prog.get('total_pages') and st == 'running':
            print(f'       {prog.get("extracted_pages")}/{prog.get("total_pages")} 页')

        if elapsed < POLL_FAST_UNTIL:
            wait = POLL_FAST
        elif elapsed < POLL_MED_UNTIL:
            wait = POLL_MED
        else:
            wait = POLL_SLOW
        time.sleep(wait)

    parse_time = time.time() - t0

    # 4. 下载 + 解压
    print('  [4/4] 下载 ZIP…')
    zip_url = result['full_zip_url']
    zip_path = os.path.join(tmp_dir, 'result.zip')
    download_zip(zip_url, zip_path)

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp_dir)
        names = z.namelist()
    img_count = len([n for n in names if n.startswith('images/') and not n.endswith('/')])
    print(f'       解压完成：{len(names)} 条目，{img_count} 张图')

    # 落盘（去掉 tmp 里的 zip）
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    if not keep_zip:
        try:
            os.remove(zip_path)
        except OSError:
            pass
    shutil.move(tmp_dir, out_dir)

    summary = build_summary(out_dir)
    summary['cache_version'] = CACHE_VERSION
    summary.update({
        'source_pdf': os.path.abspath(pdf_path),
        'fingerprint': fp,
        'batch_id': batch_id,
        'parse_seconds': round(parse_time, 1),
        'zip_url': zip_url,
        'out_dir': out_dir,
        'parsed_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    })
    with open(os.path.join(out_dir, '.meta.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    open(done_marker, 'w').close()

    return summary


def main():
    ap = argparse.ArgumentParser(description='MinerU 解析 PDF（Zotero 退场后的解析积木）')
    ap.add_argument('pdf', nargs='?', help='PDF 文件路径')
    ap.add_argument('--out', default=DEFAULT_CACHE, help=f'缓存根目录（默认 {DEFAULT_CACHE}）')
    ap.add_argument('--keep-zip', action='store_true', help='保留原始 ZIP')
    ap.add_argument('--json', action='store_true', help='只输出 JSON 摘要')
    ap.add_argument('--selftest-cache', action='store_true', help='离线自检缓存迁移逻辑（不耗 API）')
    args = ap.parse_args()

    if args.selftest_cache:
        return _cache_selftest()
    if not args.pdf:
        ap.error('缺少 PDF 路径')

    try:
        s = parse(args.pdf, args.out, args.keep_zip)
    except MineruError as exc:
        print(f'❌ {exc}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0

    print()
    print('─' * 62)
    print('✅ 解析完成')
    print(f"  输出目录   : {s['out_dir']}")
    print(f"  耗时       : {s['parse_seconds']} 秒")
    print(f"  标题       : {s.get('title')}")
    print(f"  正文字符   : {s.get('md_chars', 0):,}")
    print(f"  图片       : {s.get('images', 0)} 张"
          f"（引用 {s.get('image_refs', 0)} 处）")
    if s.get('layout_pages'):
        print(f"  layout.json: {s['layout_pages']} 页  (v{s.get('layout_version')})")
    print(f"  manifest   : {'有' if s.get('has_manifest') else '无（此 API 版本不产出）'}")
    print('─' * 62)
    return 0


if __name__ == '__main__':
    sys.exit(main())
