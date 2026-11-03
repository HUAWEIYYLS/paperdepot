"""校验一个条目的摘要/标签是否符合论文库 SKILL 契约。

用法：
    python validate_summary.py --vault <vault> --entry <条目目录名>

检查项：
  1. index.md 是否存在，摘要小节是否齐全（一句话总结 / 背景 / 方法 / 结果 / 结论）
  2. frontmatter 标签是否全部属于受控词表（tagmap_*.json）
  3. 四类标签是否每类至少 2 个
  4. 一句话总结长度是否合理
  5. 摘要里的关键数字能否在 full.md 找到（只告警，不阻断）

退出码：结构/标签错误 → 1；只有告警 → 0。插件只把非 0 当作提示，不阻断入库。
"""
import argparse
import io
import json
import os
import re
import sys

SECTIONS = [
    '## 一句话总结',
    '## 研究背景',
    '## 研究方法',
    '## 主要结果',
    '## 结论与贡献',
]
CATS = ['领域', '方法', '应用', '仪器']
TAG_RE = re.compile(r'^\s*-\s*["\']?(领域|方法|应用|仪器|状态)/\s*(.+?)["\']?\s*$')
NUM_RE = re.compile(r'\d+(?:\.\d+)?%?')


def lp(p):
    if os.name != 'nt':
        return p
    if p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)


def read_text(p):
    with io.open(lp(p), encoding='utf-8', errors='replace') as f:
        return f.read()


def load_canon(config_dir):
    canon = {c: set() for c in CATS}
    for cat in CATS:
        path = os.path.join(config_dir, f'tagmap_{cat}.json')
        if not os.path.isfile(lp(path)):
            continue
        obj = json.load(io.open(lp(path), encoding='utf-8'))
        canon[cat] = set((obj.get('mapping') or {}).values())
    return canon


def split_frontmatter(text):
    if not text.startswith('---'):
        return '', text
    end = text.find('\n---', 3)
    if end < 0:
        return '', text
    return text[3:end], text[end + 4:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vault', required=True)
    ap.add_argument('--entry', required=True)
    ap.add_argument('--config', help='config 目录（默认 <repo>/config）')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    config_dir = a.config or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
    entry_dir = os.path.join(a.vault, '1-Papers', a.entry)
    index_path = os.path.join(entry_dir, 'index.md')
    full_path = os.path.join(entry_dir, 'full.md')

    errors, warns = [], []

    if not os.path.isfile(lp(index_path)):
        print(f'❌ 缺少 index.md: {a.entry}')
        return 1

    index_md = read_text(index_path)
    fm, body = split_frontmatter(index_md)
    canon = load_canon(config_dir)

    # 1) 小节结构
    for sec in SECTIONS:
        if sec not in index_md:
            errors.append(f'缺少小节：{sec}')

    # 2) 一句话总结
    one_liner = ''
    m = re.search(r'## 一句话总结\s*\n+>\s*(.+)', index_md)
    if m:
        one_liner = m.group(1).strip()
    if not one_liner:
        errors.append('一句话总结为空')
    elif len(one_liner) < 20:
        warns.append(f'一句话总结偏短（{len(one_liner)} 字）：{one_liner[:40]}')
    elif len(one_liner) > 200:
        warns.append(f'一句话总结偏长（{len(one_liner)} 字）')

    # 3) 标签
    tags = []
    for line in fm.splitlines():
        tm = TAG_RE.match(line)
        if tm:
            val = tm.group(2).strip().strip('"').strip("'")
            tags.append((tm.group(1), val))
    if not tags:
        errors.append('frontmatter 里没有任何标签')
    by_cat = {c: [] for c in CATS}
    for cat, val in tags:
        if cat in by_cat:
            by_cat[cat].append(val)
            allowed = canon.get(cat) or set()
            if allowed and val not in allowed:
                errors.append(f'标签不在受控词表：{cat}/{val}')
    for cat in CATS:
        if len(by_cat[cat]) < 2:
            errors.append(f'{cat} 标签少于 2 个（当前 {len(by_cat[cat])}）')

    # 4) 检索字段（只告警：旧条目没有也算可用）
    for field in ('aliases', 'keywords', 'citekey'):
        if not re.search(r'^' + field + r':', fm, re.M):
            warns.append(f'缺少检索字段：{field}（建议重跑摘要）')

    # 4) 关键数字可追溯（只告警）
    if os.path.isfile(lp(full_path)):
        full_md = read_text(full_path)
        for num in set(NUM_RE.findall(one_liner)):
            core = num.rstrip('%')
            if len(core) < 2:
                continue
            if core not in full_md and core not in index_md.replace(num, ''):
                warns.append(f'数字「{num}」在 full.md 里找不到（请人工核对）')

    if not a.quiet:
        sec_ok = 'ok' if not [e for e in errors if e.startswith('缺少小节')] else 'FAIL'
        tag_ok = 'ok' if not [e for e in errors if '标签' in e] else 'FAIL'
        print(f'条目：{a.entry}')
        print(f'  小节：{sec_ok}  标签：{tag_ok}  一句话：{len(one_liner)} 字')
        for e in errors:
            print(f'  [E] {e}')
        for w in warns:
            print(f'  [W] {w}')

    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
