#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_vault — 条目完整性自检（只读检查 + 显式修复）

检查每篇论文：
  1. 必备文件是否齐全   index.md / full.md / paper.pdf / images/ / .entry.json
  2. frontmatter 是否可解析，关键字段是否缺失
  3. full.md 里的图片引用是否全部存在（这条直接对应"破图"）
  4. 目录名长度是否安全（≤120，防止路径超限）
  5. 是否有重复（同 fingerprint 或同 DOI）
  6. 参考文献覆盖率（只统计，不计入失败）

三种模式（借自 Agentero 的 Doctor 思路：只诊断 → 用户显式确认才修）：
  · 默认：只报告，绝不改任何文件
  · --ignore / --unignore：把「警告」记进忽略列表，下次不再计入
  · --fix-duplicates [--apply]：只对 paper.pdf 字节完全相同的重复做隔离；
    默认 dry-run，加 --apply 才真正移动到 0-Inbox/.paperdepot-dupes/<时间戳>/

用法：
    python verify_vault.py --vault <路径>
    python verify_vault.py --vault <路径> --json
    python verify_vault.py --vault <路径> --ignore "<条目目录名>"
    python verify_vault.py --vault <路径> --ignore-all --list-ignored
    python verify_vault.py --vault <路径> --unignore "<条目目录名>"
    python verify_vault.py --vault <路径> --fix-duplicates [--apply]

返回码：0 无错误；2 有条目错误（与旧行为一致）。
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

IMG_REF = re.compile(r'!\[[^\]]*\]\(images/([^)]+)\)')
FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.S)
REQUIRED = ['index.md', 'full.md', 'paper.pdf']
REQUIRED_DIRS = ['images']

STATE_DIR = '.paperdepot'
STATE_NAME = 'verify.json'
QUARANTINE_DIR = os.path.join('0-Inbox', '.paperdepot-dupes')

try:
    import make_references
except Exception:  # 旧安装包/单独运行时只跳过覆盖率统计
    make_references = None


def lp(p):
    """Windows 长路径前缀；POSIX 上原样返回"""
    if os.name != 'nt' or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def _read(path):
    try:
        return io.open(lp(path), encoding='utf-8', errors='replace').read()
    except OSError:
        return ''


def _fm(text):
    m = FM_RE.match(text)
    return m.group(1) if m else ''


def _fm_field(fm, key):
    m = re.search(r'^' + re.escape(key) + r':\s*(.+?)\s*$', fm, re.M)
    if not m:
        return ''
    return m.group(1).strip().strip('"').strip("'")


def _pdf_sha(base):
    """paper.pdf 的 sha256（前 16 位）；读不到返回空。用于判断重复是否真的同一份。"""
    p = os.path.join(base, 'paper.pdf')
    if not os.path.isfile(lp(p)):
        return ''
    h = hashlib.sha256()
    try:
        with open(lp(p), 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
    except OSError:
        return ''
    return h.hexdigest()[:16]


# ── 单条目检查 ────────────────────────────────────────────────────────
def verify_one(base: str) -> dict:
    r = {'dir': os.path.basename(base), 'issues': [], 'warn': [],
         'images': 0, 'broken': 0}

    names = set(os.listdir(lp(base)))
    for f in REQUIRED:
        if f not in names:
            r['issues'].append(f'缺 {f}')
    for d in REQUIRED_DIRS:
        if d not in names:
            r['issues'].append(f'缺 {d}/')

    # frontmatter
    idx = os.path.join(base, 'index.md')
    if os.path.isfile(lp(idx)):
        text = _read(idx)
        fm = _fm(text)
        if not fm:
            r['issues'].append('index.md 无 frontmatter')
        else:
            for k in ('title', 'source'):
                if (k + ':') not in fm:
                    r['warn'].append(f'frontmatter 缺 {k}')
            if 'needs_metadata' in fm:
                r['warn'].append('待补元数据')

    # 图片引用 + 参考文献覆盖率（后者只统计，不作为失败项）
    md = ''
    full = os.path.join(base, 'full.md')
    if os.path.isfile(lp(full)):
        md = _read(full)
        refs = IMG_REF.findall(md)
        r['images'] = len(refs)
        imgdir = os.path.join(base, 'images')
        have = set(os.listdir(lp(imgdir))) if os.path.isdir(lp(imgdir)) else set()
        missing = [x for x in refs if x not in have]
        r['broken'] = len(missing)
        if missing:
            r['issues'].append(f'{len(missing)} 张图引用不存在')

    r['refs_file'] = os.path.isfile(lp(os.path.join(base, 'references.md')))
    r['refs_parse_ok'] = None
    r['refs_reason'] = ''
    r['refs_count'] = 0
    if md and make_references is not None:
        try:
            parsed = make_references.parse_references(md)
            r['refs_parse_ok'] = bool(parsed.get('ok'))
            r['refs_reason'] = parsed.get('reason', '')
            r['refs_count'] = parsed.get('count', 0)
        except Exception as exc:
            r['refs_parse_ok'] = False
            r['refs_reason'] = 'exception: %s' % exc

    # 目录名长度
    if len(r['dir']) > 120:
        r['warn'].append(f'目录名 {len(r["dir"])} 字符（建议 ≤120）')

    # 路径总长
    deepest = os.path.join(base, 'images', 'fig99.jpg')
    if len(deepest) > 250:
        r['issues'].append(f'最深路径 {len(deepest)} 字符，接近上限')

    return r


# ── 重复检测 / 修复计划 ───────────────────────────────────────────────
def _entry_rank(base):
    """重复时保留哪一条：有摘要 > 有参考文献 > 文件更全 > 名称更短 > 字典序。"""
    text = _read(os.path.join(base, 'index.md'))
    fm = _fm(text)
    summarized = 1 if 'summarized: true' in fm else 0
    has_refs = 1 if os.path.isfile(lp(os.path.join(base, 'references.md'))) else 0
    try:
        n_files = len(os.listdir(lp(base)))
    except OSError:
        n_files = 0
    return (-summarized, -has_refs, -n_files, len(os.path.basename(base)), base)


def collect_duplicates(dirs):
    fps = defaultdict(list)
    dois = defaultdict(list)
    for d in dirs:
        e = {}
        ej = os.path.join(d, '.entry.json')
        if os.path.isfile(lp(ej)):
            try:
                e = json.loads(_read(ej) or '{}')
            except Exception:
                e = {}
        if e.get('fingerprint'):
            fps[e['fingerprint']].append(d)
        doi = (e.get('doi') or _fm_field(_fm(_read(os.path.join(d, 'index.md'))), 'doi')).lower()
        if doi:
            dois[doi].append(d)

    groups = []
    for kind, mapping in (('fingerprint', fps), ('doi', dois)):
        for key in sorted(mapping):
            items = mapping[key]
            if len(items) > 1:
                groups.append({'kind': kind, 'key': key, 'dirs': sorted(items)})
    return groups


def plan_fixes(groups):
    """只自动处理「paper.pdf 字节完全相同」的重复；其余交给人工判断。

    DOI 相同但 PDF 不同，可能是预印本/正式版、也可能是 DOI 误配，
    自动删除有风险，所以只列出来。
    """
    auto, manual = [], []
    for g in groups:
        shas = {d: _pdf_sha(d) for d in g['dirs']}
        if all(shas.values()) and len(set(shas.values())) == 1:
            ordered = sorted(g['dirs'], key=_entry_rank)
            auto.append({'kind': g['kind'], 'key': g['key'],
                         'keep': ordered[0], 'remove': ordered[1:],
                         'pdf_sha': list(shas.values())[0]})
        else:
            manual.append({'kind': g['kind'], 'key': g['key'],
                           'dirs': [{'dir': os.path.basename(d), 'pdf_sha': shas[d]}
                                    for d in g['dirs']]})
    return auto, manual


def apply_fixes(vault, auto):
    """把多余的重复目录移到 0-Inbox 隔离区（可恢复，不删除）。"""
    stamp = time.strftime('%Y%m%d-%H%M%S')
    dest_root = os.path.join(vault, QUARANTINE_DIR, stamp)
    os.makedirs(lp(dest_root), exist_ok=True)
    moved = []
    for item in auto:
        for src in item['remove']:
            dest = os.path.join(dest_root, os.path.basename(src))
            n = 2
            while os.path.exists(lp(dest)):
                dest = os.path.join(dest_root, '%s-%d' % (os.path.basename(src), n))
                n += 1
            os.rename(lp(src), lp(dest))
            moved.append({'from': src, 'to': dest})
    return dest_root, moved


# ── 忽略列表状态 ──────────────────────────────────────────────────────
def state_path(vault, override=None):
    return override or os.path.join(vault, STATE_DIR, STATE_NAME)


def load_state(path):
    try:
        data = json.loads(_read(path) or '{}')
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    ignored = data.get('ignored')
    if not isinstance(ignored, dict):
        ignored = {}
    data['ignored'] = ignored
    return data


def save_state(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(lp(parent), exist_ok=True)
    tmp = path + '.tmp'
    with io.open(lp(tmp), 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + '\n')
    os.replace(lp(tmp), lp(path))


def apply_ignores(results, state):
    """把忽略列表里的警告从 warn 移到 ignored_warn（issues 永不被忽略）。"""
    ignored = state['ignored']
    for r in results:
        allowed = set((ignored.get(r['dir']) or {}).get('warn') or [])
        r['ignored_warn'] = [w for w in r['warn'] if w in allowed]
        r['warn'] = [w for w in r['warn'] if w not in allowed]


# ── 输出 ──────────────────────────────────────────────────────────────
def build_summary(results, groups, auto, manual):
    ok = [r for r in results if not r['issues']]
    bad = [r for r in results if r['issues']]
    warn = [r for r in results if r['warn'] and not r['issues']]
    ignored = [r for r in results if r.get('ignored_warn') and not r['issues']]

    refs_present = [r for r in results if r.get('refs_file')]
    refs_parseable = [r for r in results if r.get('refs_parse_ok')]
    refs_to_generate = [r for r in refs_parseable if not r.get('refs_file')]
    refs_no_heading = [r for r in results if r.get('refs_parse_ok') is False
                       and r.get('refs_reason') == 'no-heading']
    refs_errors = [r for r in results if r.get('refs_parse_ok') is False
                   and r.get('refs_reason') != 'no-heading']

    return {
        'entries': len(results),
        'ok': len(ok),
        'warn': len(warn),
        'ignored': len(ignored),
        'issues': len(bad),
        'images': sum(r['images'] for r in results),
        'broken': sum(r['broken'] for r in results),
        'refs': {
            'files': len(refs_present),
            'missing': len(results) - len(refs_present),
            'parseable': len(refs_parseable),
            'total': sum(r.get('refs_count', 0) for r in refs_present),
            'noHeading': len(refs_no_heading),
            'errors': len(refs_errors),
            'toGenerate': len(refs_to_generate),
        },
        'duplicates': {
            'groups': len(groups),
            'fingerprint': sum(1 for g in groups if g['kind'] == 'fingerprint'),
            'doi': sum(1 for g in groups if g['kind'] == 'doi'),
            'fixable': len(auto),
            'manual': len(manual),
        },
    }


def print_human(s, results, groups, auto, manual, state_file, state):
    bad = [r for r in results if r['issues']]
    warn = [r for r in results if r['warn'] and not r['issues']]

    print('=' * 70)
    print(f'条目总数      : {s["entries"]}')
    print(f'完全正常      : {s["ok"]}')
    print(f'有警告        : {s["warn"]}' + (f'（另有 {s["ignored"]} 篇的警告被忽略）' if s['ignored'] else ''))
    print(f'有错误        : {s["issues"]}')
    print(f'图片引用总数  : {s["images"]}')
    print(f'其中断链      : {s["broken"]}')
    r = s['refs']
    print(f'参考文献文件  : {r["files"]} 篇有 / {r["missing"]} 篇无')
    print(f'参考文献解析  : full.md 能解析出文献段 {r["parseable"]} 篇'
          f'（已生成 {r["files"]} 篇，共 {r["total"]} 条）')
    print(f'              : {r["noHeading"]} 篇无文献段 / {r["errors"]} 篇解析异常')
    if r['toGenerate']:
        print(f'              : {r["toGenerate"]} 篇可生成但还没有 references.md'
              f'（python tools/make_references.py --vault <vault> --all）')
    print('=' * 70)

    if bad:
        print('\n【错误】')
        for x in bad[:30]:
            print(f'  ❌ {x["dir"][:60]}')
            for i in x['issues']:
                print(f'       {i}')
        if len(bad) > 30:
            print(f'  … 另有 {len(bad)-30} 个')

    warn_groups = Counter()
    for x in warn:
        for w in x['warn']:
            warn_groups[w] += 1
    if warn_groups:
        print('\n【警告汇总】')
        for w, n in warn_groups.most_common():
            print(f'  ⚠ {w}: {n} 个')

    if groups:
        print('\n【重复】')
        if auto:
            print(f'  可自动修复（paper.pdf 完全相同）: {len(auto)} 组')
            for item in auto:
                print(f'     [{item["kind"]}] {item["key"]}  保留 {os.path.basename(item["keep"])[:52]}')
                for d in item['remove']:
                    print(f'        将移入隔离区: {os.path.basename(d)[:60]}')
        if manual:
            print(f'  需人工判断（PDF 不同，可能是预印本/正式版或 DOI 误配）: {len(manual)} 组')
            for item in manual:
                print(f'     [{item["kind"]}] {item["key"]}')
                for d in item['dirs']:
                    print(f'        {d["dir"][:60]}  pdf={d["pdf_sha"] or "无"}')
        if auto:
            print('\n  以上「可自动修复」默认不执行；确认后加 --apply：')
            print(f'    python tools/verify_vault.py --vault <vault> --fix-duplicates --apply')

    print(f'\n忽略列表：{state_file}'
          + (f'（{len(state["ignored"])} 篇）' if state.get('ignored') else ''))


# ── CLI ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='论文库条目完整性自检')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--json', action='store_true', help='输出 JSON（stderr 之外的机器可读结果）')
    ap.add_argument('--state', help='忽略列表文件路径（默认 <vault>/.paperdepot/verify.json）')
    ap.add_argument('--ignore', action='append', default=[], metavar='DIR',
                    help='忽略该条目当前的警告（可重复）')
    ap.add_argument('--ignore-all', action='store_true', help='忽略所有条目当前的警告')
    ap.add_argument('--unignore', action='append', default=[], metavar='DIR',
                    help='恢复该条目的警告（可重复）')
    ap.add_argument('--unignore-all', action='store_true', help='清空整份忽略列表')
    ap.add_argument('--list-ignored', action='store_true', help='只打印忽略列表')
    ap.add_argument('--fix-duplicates', action='store_true',
                    help='检查 paper.pdf 完全相同的重复（默认 dry-run）')
    ap.add_argument('--apply', action='store_true', help='配合 --fix-duplicates 真正移动到隔离区')
    args = ap.parse_args()

    vault = args.vault
    papers = os.path.join(vault, '1-Papers')
    if not os.path.isdir(lp(papers)):
        print('没有 1-Papers', file=sys.stderr)
        return 1

    state_file = state_path(vault, args.state)
    state = load_state(state_file)

    if args.list_ignored:
        if not state['ignored']:
            print('忽略列表为空')
            return 0
        for name in sorted(state['ignored']):
            item = state['ignored'][name] or {}
            print(f'  {name}')
            for w in item.get('warn') or []:
                print(f'      - {w}')
            if item.get('at'):
                print(f'      （{item["at"]}）')
        return 0

    if args.unignore_all:
        state['ignored'] = {}
        save_state(state_file, state)
        print('已清空忽略列表')
        return 0

    if args.unignore:
        changed = 0
        for name in args.unignore:
            if state['ignored'].pop(name, None) is not None:
                changed += 1
        save_state(state_file, state)
        print(f'已恢复 {changed} 个条目的警告')
        return 0

    dirs = [os.path.join(papers, d) for d in sorted(os.listdir(lp(papers)))
            if os.path.isdir(lp(os.path.join(papers, d))) and not d.startswith('_')]
    results = [verify_one(d) for d in dirs]

    if args.ignore or args.ignore_all:
        targets = [os.path.basename(d) for d in dirs] if args.ignore_all else list(args.ignore)
        known = {r['dir'] for r in results}
        added = 0
        for name in targets:
            if name not in known:
                print(f'跳过（没有这个条目）：{name}', file=sys.stderr)
                continue
            item = results[[r['dir'] for r in results].index(name)]
            if not item['warn']:
                continue
            state['ignored'][name] = {'warn': sorted(item['warn']),
                                      'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
            added += 1
        save_state(state_file, state)
        print(f'已忽略 {added} 个条目的警告（{state_file}）')

    # 清理已不存在条目的忽略项
    dead = [k for k in state['ignored'] if k not in {r['dir'] for r in results}]
    for k in dead:
        state['ignored'].pop(k, None)
    if dead:
        save_state(state_file, state)

    apply_ignores(results, state)

    groups = collect_duplicates(dirs)
    auto, manual = plan_fixes(groups)
    summary = build_summary(results, groups, auto, manual)

    if args.fix_duplicates:
        if args.apply and auto:
            dest_root, moved = apply_fixes(vault, auto)
            summary['duplicates']['moved'] = len(moved)
            summary['duplicates']['quarantine'] = dest_root
            if not args.json:
                print(f'已移动 {len(moved)} 个重复目录到 {dest_root}\n')
            # 移动后重新统计，避免把已隔离的条目算进报告
            dirs = [os.path.join(papers, d) for d in sorted(os.listdir(lp(papers)))
                    if os.path.isdir(lp(os.path.join(papers, d))) and not d.startswith('_')]
            results = [verify_one(d) for d in dirs]
            apply_ignores(results, state)
            groups = collect_duplicates(dirs)
            auto, manual = plan_fixes(groups)
            summary = build_summary(results, groups, auto, manual)
            summary['duplicates']['moved'] = len(moved)
            summary['duplicates']['quarantine'] = dest_root

    if args.json:
        report = {
            'ok': summary['issues'] == 0,
            'vault': vault,
            'checked': len(results),
            'summary': summary,
            'entries': [{
                'dir': r['dir'],
                'issues': r['issues'],
                'warn': r['warn'],
                'ignoredWarn': r.get('ignored_warn') or [],
                'images': r['images'],
                'broken': r['broken'],
                'refs': {
                    'file': r.get('refs_file'),
                    'parseOk': r.get('refs_parse_ok'),
                    'reason': r.get('refs_reason'),
                    'count': r.get('refs_count', 0),
                },
            } for r in results],
            'duplicates': {'groups': groups, 'auto': auto, 'manual': manual},
            'statePath': state_file,
        }
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if summary['issues'] == 0 else 2

    print_human(summary, results, groups, auto, manual, state_file, state)
    return 0 if summary['issues'] == 0 else 2


if __name__ == '__main__':
    sys.exit(main())