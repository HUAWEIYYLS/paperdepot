window.__ModuleLoader__.load({
  id: 'paperdepot',
  factory: (require) => {
    const React = require('react')
    const h = React.createElement
    const { useEffect, useState, useCallback, useRef, useMemo } = React

    // DSH 主题 token（宿主有定义就用宿主的，浏览器/旧版用回退值）
    const T = {
      bg: 'var(--dsw-alias-bg-base, #17181c)',
      bg1: 'var(--dsw-alias-bg-layer-1, #1d1e23)',
      bg2: 'var(--dsw-alias-bg-layer-2, #23242a)',
      text: 'var(--dsw-alias-label-primary, #e9e9ec)',
      text2: 'var(--dsw-alias-label-secondary, #a6a6ae)',
      text3: 'var(--dsw-alias-label-tertiary, #7c7c84)',
      caption: 'var(--dsw-alias-label-caption, #6d6d75)',
      b1: 'var(--dsw-alias-border-l1, #2a2b31)',
      b2: 'var(--dsw-alias-border-l2, #35363d)',
      accent: 'var(--dsw-alias-state-business-primary, #4d6bfe)',
      brand: 'var(--dsw-alias-brand-primary, #4d6bfe)',
      brandText: 'var(--dsw-alias-label-primary-inverted, #ffffff)',
      success: 'var(--dsw-alias-state-success-primary, #22a06b)',
      warn: 'var(--dsw-alias-state-warn-primary, #d08a2c)',
      hover: 'var(--dsw-alias-interactive-bg-hover, rgba(127,127,127,0.12))',
      font: 'var(--dsw-font-family, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif)',
    }
    const ACCENT = T.accent
    const GREEN = T.success
    const ORANGE = T.warn
    const WARN_TEXT = 'var(--dsw-alias-state-warn-label, #b45309)'
    const ERROR_TEXT = 'var(--dsw-alias-state-error-primary, #d93a3a)'
    const muted = T.text2
    const faint = T.text2
    const line = T.b1
    const card = T.bg1
    const hoverBg = T.hover
    const mono = 'ui-monospace, "Cascadia Code", Consolas, monospace'

    // 8pt 栅格 + 14px 正文
    const FS = { caption: 13, body: 14, sub: 15.5, title: 18, page: 21, stat: 26 }
    const SP = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 }
    const R = { sm: 6, md: 10, lg: 14 }

    // 分类语义色：四类受控标签固定色，概念页单独一色。
    // 与 DOMAIN_COLORS（按领域名轮转的识别色）分工：分类色用于 chip / 标签，领域色用于列表里的领域点。
    const CAT_COLOR = { 领域: '#6ea8fe', 方法: '#4ec9a5', 应用: '#e6b450', 仪器: '#c792ea', 状态: '#8b90a0' }
    const CONCEPT_COLOR = '#ff8fab'
    const DOMAIN_COLORS = ['#60a5fa', '#34d399', '#fbbf24', '#a78bfa', '#38bdf8', '#fb923c', '#4ade80', '#e879f9', '#22d3ee', '#f87171', '#a3e635', '#f472b6']

    function hexA(hex, a) {
      const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ''))
      if (!m) return hex
      const n = parseInt(m[1], 16)
      return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
    }

    function tagCategory(tag) {
      const s = String(tag || '')
      const i = s.indexOf('/')
      if (i > 0) return s.slice(0, i)
      const j = s.indexOf('-')
      return j > 0 ? s.slice(0, j) : ''
    }

    function tagColor(tag) {
      return CAT_COLOR[tagCategory(tag)] || T.text3
    }

    function domainOfPaper(p) {
      const t = (p.tags || []).find((x) => x.startsWith('领域/'))
      return t ? t.slice(3) : ''
    }

    function domainColor(domain, domains) {
      const i = domains.indexOf(domain)
      return DOMAIN_COLORS[(i < 0 ? 0 : i) % DOMAIN_COLORS.length]
    }

    const fmt = (n) => (typeof n === 'number' ? n.toLocaleString('zh-CN') : '—')
    const api = (p) => fetch('/paperdepot/api' + p, { credentials: 'same-origin' })

    function Btn({ children, onClick, disabled, primary, ghost, small, title }) {
      const [hover, setHover] = useState(false)
      return h(
        'button',
        {
          onClick,
          disabled,
          title,
          onMouseEnter: () => setHover(true),
          onMouseLeave: () => setHover(false),
          style: {
            height: small ? 30 : 34,
            padding: small ? '0 10px' : '0 13px',
            borderRadius: R.sm,
            fontSize: small ? FS.caption : FS.body,
            fontWeight: primary ? 600 : 500,
            cursor: disabled ? 'not-allowed' : 'pointer',
            border: `1px solid ${primary ? T.brand : hover && !disabled ? T.b2 : line}`,
            background: primary ? T.brand : hover && !disabled ? hoverBg : ghost ? 'transparent' : 'transparent',
            color: primary ? T.brandText : ghost ? T.text2 : T.text,
            opacity: disabled ? 0.55 : 1,
            whiteSpace: 'nowrap',
            filter: primary && hover && !disabled ? 'brightness(0.96)' : 'none',
            transition: 'background .15s ease, border-color .15s ease',
          },
        },
        children,
      )
    }

    function Chip({ children, active, onClick, title }) {
      return h(
        'button',
        {
          onClick,
          title,
          style: {
            height: 30,
            padding: '0 12px',
            borderRadius: 999,
            fontSize: FS.caption,
            cursor: onClick ? 'pointer' : 'default',
            border: `1px solid ${active ? ACCENT : line}`,
            background: active ? 'rgba(77,107,254,0.16)' : 'transparent',
            color: 'inherit',
            whiteSpace: 'nowrap',
          },
        },
        children,
      )
    }

    function Card({ label, value, sub, accent }) {
      return h(
        'div',
        {
          style: {
            flex: '1 1 140px',
            minWidth: 130,
            padding: '16px 18px',
            borderRadius: R.lg,
            background: card,
            border: `1px solid ${line}`,
          },
        },
        h('div', { style: { fontSize: FS.stat, fontWeight: 700, lineHeight: 1.15, color: accent || 'inherit' } }, value),
        h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 6 } }, label),
        sub ? h('div', { style: { fontSize: 12.5, color: faint, marginTop: 2 } }, sub) : null,
      )
    }

    function Bars({ items, color }) {
      const max = Math.max(1, ...items.map((x) => x.value))
      return h(
        'div',
        { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
        items.map((x) =>
          h(
            'div',
            { key: x.key, style: { display: 'flex', alignItems: 'center', gap: 10, fontSize: FS.caption } },
            h('div', { style: { width: 132, textAlign: 'right', color: muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: '0 0 auto' }, title: x.key }, x.label),
            h('div', { style: { flex: '1 1 auto', height: 10, background: 'rgba(127,127,127,0.10)', borderRadius: 999, overflow: 'hidden' } },
              h('div', { style: { width: `${Math.round((x.value / max) * 100)}%`, height: '100%', background: x.color || color, borderRadius: 999 } })),
            h('div', { style: { width: 44, color: faint, flex: '0 0 auto', textAlign: 'right' } }, x.value),
          ),
        ),
      )
    }

    function Section({ title, right, children, style }) {
      return h(
        'div',
        { style: { marginTop: SP.xl, ...(style || {}) } },
        h('div', { style: { display: 'flex', alignItems: 'center', marginBottom: SP.sm } },
          h('div', { style: { fontSize: FS.sub, fontWeight: 600 } }, title),
          h('div', { style: { flex: '1 1 auto' } }),
          right || null),
        children,
      )
    }

    function Empty({ children }) {
      return h('div', { style: { padding: '28px 16px', textAlign: 'center', color: faint, fontSize: FS.body, border: `1px dashed ${line}`, borderRadius: R.lg } }, children)
    }

    // ---------------- 条目排版（论文 index.md / 概念页共用，无外部依赖） ----------------
    // 面板里直接塞 <pre> 会把 YAML、导航块、表格原文全部倒出来；这里做一层轻量渲染：
    // 去 frontmatter / 导航注释 / 由面板另行呈现的尾部小节，再按标题、列表、表格、引用排版。

    const MD_FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/
    const MD_HIDDEN_SECTIONS = ['标签', '相关文件', '全文', '原始文件', '所属概念', '分类', '相关论文']
    const MD_EMOJI_HEAD = /^[^\p{L}\p{N}\u4e00-\u9fff]+/u
    const MD_BLOCK_START = /^(#{1,6}\s|>\s?|\s*(?:[-*+]|\d+\.)\s+|\||!\[)/

    const LATEX_MAP = [
      [/\\times/g, '×'], [/\\cdot/g, '·'], [/\\pm/g, '±'], [/\\approx/g, '≈'], [/\\sim/g, '~'],
      [/\\leq?/g, '≤'], [/\\geq?/g, '≥'], [/\\neq?/g, '≠'], [/\\to/g, '→'], [/\\infty/g, '∞'],
      [/\\theta/g, 'θ'], [/\\phi/g, 'φ'], [/\\varphi/g, 'φ'], [/\\alpha/g, 'α'], [/\\beta/g, 'β'],
      [/\\gamma/g, 'γ'], [/\\delta/g, 'δ'], [/\\Delta/g, 'Δ'], [/\\lambda/g, 'λ'], [/\\mu/g, 'μ'],
      [/\\sigma/g, 'σ'], [/\\Sigma/g, 'Σ'], [/\\omega/g, 'ω'], [/\\Omega/g, 'Ω'], [/\\tau/g, 'τ'],
      [/\\rho/g, 'ρ'], [/\\nu/g, 'ν'], [/\\epsilon/g, 'ε'], [/\\psi/g, 'ψ'], [/\\circ/g, '°'],
      [/\\tan/g, 'tan'], [/\\log/g, 'log'], [/\\exp/g, 'exp'], [/\\sin/g, 'sin'], [/\\cos/g, 'cos'],
      [/\\mathrm\{([^}]*)\}/g, '$1'], [/\\text\{([^}]*)\}/g, '$1'],
      [/\\left[([|.]/g, '$1'], [/\\right[)\]|.]/g, '$1'],
      [/\\[,;: ]/g, ' '], [/\\!/g, ''], [/\\%/g, '%'], [/\\_/g, '_'], [/\\/g, ''],
    ]

    const LATEX_SUP = { 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹', '-': '⁻', '+': '⁺' }
    const LATEX_SUB = { 0: '₀', 1: '₁', 2: '₂', 3: '₃', 4: '₄', 5: '₅', 6: '₆', 7: '₇', 8: '₈', 9: '₉', '-': '₋' }
    const mapsTo = (m) => [...m].map((x) => LATEX_SUP[x] || x).join('')
    const mapsToSub = (m) => [...m].map((x) => LATEX_SUB[x] || x).join('')

    // 正文里也常出现未包 $ 的 10^{-6}、s^{-1}，顺手换成上/下标，避免花括号漏出来
    function prettyPlain(s) {
      return String(s || '')
        .replace(/\^\{([-+0-9]+)\}/g, (m, g) => mapsTo(g))
        .replace(/\^(-?[0-9]+)/g, (m, g) => mapsTo(g))
        .replace(/_\{([0-9]+)\}/g, (m, g) => mapsToSub(g))
    }

    function prettyMath(s) {
      let out = String(s || '')
      for (const [re, rep] of LATEX_MAP) out = out.replace(re, rep)
      out = out
        .replace(/\^\{([-+0-9]+)\}/g, (m, g) => mapsTo(g))
        .replace(/\^(-?[0-9]+)/g, (m, g) => mapsTo(g))
        .replace(/_\{([0-9]+)\}/g, (m, g) => mapsToSub(g))
        .replace(/_([0-9]+)/g, (m, g) => mapsToSub(g))
        .replace(/[{}]/g, '')
        .replace(/([µμ])\s+(?=[a-zA-Z])/g, '$1')
        .replace(/[ \t]+/g, ' ')
        .trim()
      return out
    }

    function parsePaperFrontmatter(md) {
      const m = MD_FRONTMATTER.exec(String(md || ''))
      const block = m ? m[1] : ''
      const scalar = (k) => {
        const r = new RegExp('^' + k + ':\\s*(.+?)\\s*$', 'm').exec(block)
        return r ? r[1].trim().replace(/^["']|["']$/g, '') : ''
      }
      const list = (k) => {
        const r = new RegExp('^' + k + ':\\s*\\n((?:[ \\t]*-[^\\n]*\\n?)+)', 'm').exec(block)
        if (!r) return []
        return r[1]
          .split(/\r?\n/)
          .map((x) => x.trim().replace(/^-\s*/, '').replace(/^["']|["']$/g, ''))
          .filter(Boolean)
      }
      const fm = {}
      for (const k of ['title', 'year', 'journal', 'doi', 'arxiv', 'pages', 'figures', 'status', 'citekey', 'updated']) fm[k] = scalar(k)
      fm.tags = list('tags')
      fm.aliases = list('aliases')
      return fm
    }

    function stripEntryChrome(md) {
      let s = String(md || '')
      s = s.replace(/<!--\s*[\w-]+:nav:start\s*-->[\s\S]*?<!--\s*[\w-]+:nav:end\s*-->/g, '')
      s = s.replace(/<!--[\s\S]*?-->/g, '')
      s = s.replace(MD_FRONTMATTER, '')
      const out = []
      let skip = false
      for (const line of s.split(/\r?\n/)) {
        const m = /^##\s+(.+?)\s*$/.exec(line)
        if (m) skip = MD_HIDDEN_SECTIONS.some((n) => m[1].includes(n))
        if (!skip) out.push(line)
      }
      return out.join('\n')
    }

    function splitTableRow(line) {
      return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
    }

    function renderInline(text, keyBase, opts) {
      const s = String(text == null ? '' : text)
      const re = /(\[\[[^\]\n]+\]\]|\*\*[^*\n]+\*\*|`[^`\n]+`|\$[^$\n]+\$|\[[^\]\n]+\]\([^)\n]+\)|\*[^*\n]+\*)/g
      const out = []
      let last = 0
      let n = 0
      let m
      while ((m = re.exec(s))) {
        if (m.index > last) out.push(prettyPlain(s.slice(last, m.index)))
        const tok = m[0]
        const key = keyBase + '-' + n++
        if (tok.startsWith('[[')) {
          const inner = tok.slice(2, -2)
          const cut = inner.indexOf('|')
          const target = (cut === -1 ? inner : inner.slice(0, cut)).trim()
          const alias = (cut === -1 ? inner : inner.slice(cut + 1)).trim()
          const open = opts && opts.onOpenPaper && /^1-Papers\//.test(target)
          if (target.startsWith('2-Concepts/')) {
            out.push(h(ConceptChip, { key, name: alias || target.slice('2-Concepts/'.length) }))
          } else if (target.startsWith('3-Taxonomy/')) {
            out.push(h(TaxChip, { key, id: (target.split('/')[1] || '').replace(/\.md$/, '') }))
          } else {
            out.push(
              h('span', {
                key,
                title: target,
                onClick: open ? () => opts.onOpenPaper(target.replace(/^1-Papers\//, '').replace(/\/index.*$/, '')) : undefined,
                style: { color: T.text2, borderBottom: `1px dotted ${T.b2}`, cursor: open ? 'pointer' : 'default' },
              }, alias || target),
            )
          }
        } else if (tok.startsWith('**')) {
          out.push(h('strong', { key, style: { fontWeight: 600, color: T.text } }, tok.slice(2, -2)))
        } else if (tok.startsWith('`')) {
          out.push(h('code', { key, style: { fontFamily: mono, fontSize: '0.92em', background: 'rgba(255,255,255,0.06)', padding: '1px 5px', borderRadius: 4 } }, tok.slice(1, -1)))
        } else if (tok.startsWith('$')) {
          out.push(h('span', { key, style: { fontFamily: mono, fontSize: '0.92em', color: '#c8c9d4' } }, prettyMath(tok.slice(1, -1))))
        } else if (tok.startsWith('[')) {
          const mm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)
          out.push(h('a', { key, href: mm[2], target: '_blank', rel: 'noreferrer', style: { color: '#8fa3ff', textDecoration: 'none' } }, mm[1]))
        } else {
          out.push(h('em', { key, style: { fontStyle: 'normal', color: T.text2 } }, tok.slice(1, -1)))
        }
        last = m.index + tok.length
      }
      if (last < s.length) out.push(prettyPlain(s.slice(last)))
      return out.length ? out : ['']
    }

    function mdTable(header, rows, keyBase) {
      const cell = (text, i) => {
        const isNum = /^[\d.,%×+\-–—\s/]+$/.test(text) && /\d/.test(text)
        return h('td', {
          key: keyBase + '-c' + i,
          style: {
            padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,0.05)', lineHeight: 1.6, verticalAlign: 'top',
            fontFamily: isNum ? mono : 'inherit', fontSize: isNum ? 12.5 : 13,
            fontVariantNumeric: isNum ? 'tabular-nums' : undefined, color: isNum ? T.text2 : 'inherit',
          },
        }, renderInline(text, keyBase + '-c' + i))
      }
      return h('table', { key: keyBase, style: { width: '100%', borderCollapse: 'collapse', margin: '10px 0 18px', fontSize: 13 } },
        h('thead', null, h('tr', null, header.map((c, i) => h('th', {
          key: keyBase + '-h' + i,
          style: { textAlign: 'left', fontSize: 12, fontWeight: 600, color: T.text3, padding: '7px 10px', borderBottom: '1px solid rgba(255,255,255,0.1)', whiteSpace: 'nowrap' },
        }, renderInline(c, keyBase + '-h' + i))))),
        h('tbody', null, rows.map((cells, r) => h('tr', { key: keyBase + '-r' + r }, cells.map(cell)))))
    }

    function mdList(items, ordered, keyBase) {
      return h('div', { key: keyBase, style: { margin: '0 0 14px' } },
        items.map((it, i) => h('div', { key: keyBase + '-' + i, style: { display: 'flex', gap: 8, marginBottom: 5 } },
          h('span', {
            style: {
              flex: '0 0 auto', minWidth: ordered ? 17 : 10, color: T.caption, lineHeight: 1.8,
              fontFamily: ordered ? mono : 'inherit', fontSize: ordered ? 12 : 13,
            },
          }, ordered ? (i + 1) + '.' : '–'),
          h('span', { style: { flex: '1 1 auto', lineHeight: 1.8 } }, renderInline(it, keyBase + '-' + i)))))
    }

    function mdLede(text, keyBase) {
      const clean = String(text || '').replace(/^(\*\*)?一句话(\*\*)?\s*[：:]\s*/, '')
      return h('div', {
        key: keyBase,
        style: { margin: '0 0 26px', padding: '2px 0 2px 18px', borderLeft: `2px solid ${ACCENT}`, fontSize: 16.5, lineHeight: 1.72, color: T.text },
      }, renderInline(clean, keyBase, null))
    }

    function mdQuote(text, keyBase) {
      const clean = String(text || '').replace(/^(\*\*)?一句话(\*\*)?\s*[：:]\s*/, '')
      return h('div', {
        key: keyBase,
        style: { margin: '0 0 14px', padding: '2px 0 2px 14px', borderLeft: `2px solid ${T.b2}`, color: T.text2, lineHeight: 1.8 },
      }, renderInline(clean, keyBase, null))
    }

    function Markdown({ source, ledeHeading, ledeFirstQuote, onOpenPaper }) {
      const src = stripEntryChrome(source)
      const lines = src.split(/\r?\n/)
      const blocks = []
      const opts = { onOpenPaper }
      let key = 0
      let ledeDone = false
      let sawSection = false
      const k = () => 'md' + key++
      let i = 0
      while (i < lines.length) {
        const line = lines[i]
        if (!line.trim()) {
          i += 1
          continue
        }
        if (line.trim().startsWith('|') && i + 1 < lines.length && /^\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1].trim())) {
          // 条目开头的基础信息表（页数/图数/作者…）与面板的元数据条重复，跳过
          if (!sawSection) {
            i += 2
            while (i < lines.length && lines[i].trim().startsWith('|')) i += 1
            continue
          }
          const header = splitTableRow(line)
          const rows = []
          i += 2
          while (i < lines.length && lines[i].trim().startsWith('|')) {
            rows.push(splitTableRow(lines[i]))
            i += 1
          }
          blocks.push(mdTable(header, rows, k()))
          continue
        }
        const hm = /^(#{1,6})\s+(.+?)\s*$/.exec(line)
        if (hm) {
          const level = hm[1].length
          const text = hm[2].replace(MD_EMOJI_HEAD, '').trim()
          i += 1
          if (level === 1) continue
          if (level === 2) sawSection = true
          if (level === 2 && ledeHeading && text.includes(ledeHeading) && !ledeDone) {
            const quote = []
            while (i < lines.length && (!lines[i].trim() || /^>\s?/.test(lines[i]))) {
              if (lines[i].trim()) quote.push(lines[i].replace(/^>\s?/, ''))
              i += 1
            }
            blocks.push(mdLede(quote.join(' '), k()))
            ledeDone = true
            continue
          }
          if (level === 2) {
            blocks.push(h('div', {
              key: k(),
              style: { margin: '30px 0 10px', paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: FS.sub, fontWeight: 600, color: T.text },
            }, text))
          } else {
            blocks.push(h('div', { key: k(), style: { margin: '20px 0 6px', fontSize: 13.5, fontWeight: 600, color: T.text2 } }, text))
          }
          continue
        }
        if (/^>\s?/.test(line)) {
          const quote = []
          while (i < lines.length && /^>\s?/.test(lines[i])) {
            quote.push(lines[i].replace(/^>\s?/, ''))
            i += 1
          }
          if (ledeFirstQuote && !ledeDone) {
            blocks.push(mdLede(quote.join(' '), k()))
            ledeDone = true
          } else {
            blocks.push(mdQuote(quote.join(' '), k()))
          }
          continue
        }
        if (/^\s*(?:[-*+]|\d+\.)\s+/.test(line)) {
          const ordered = /^\s*\d+\./.test(line)
          const items = []
          while (i < lines.length && /^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i])) {
            items.push(lines[i].replace(/^\s*(?:[-*+]|\d+\.)\s+/, ''))
            i += 1
            while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i])) {
              items[items.length - 1] += ' ' + lines[i].trim()
              i += 1
            }
          }
          blocks.push(mdList(items, ordered, k()))
          continue
        }
        const img = /^!\[([^\]]*)\]\(([^)]+)\)\s*$/.exec(line.trim())
        if (img) {
          blocks.push(h('div', { key: k(), style: { margin: '6px 0', fontSize: 12.5, color: T.caption } }, img[1] ? '图：' + img[1] : '［图］'))
          i += 1
          continue
        }
        if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
          blocks.push(h('div', { key: k(), style: { height: 1, background: 'rgba(255,255,255,0.06)', margin: '22px 0' } }))
          i += 1
          continue
        }
        const para = [line]
        i += 1
        while (i < lines.length && lines[i].trim() && !MD_BLOCK_START.test(lines[i])) {
          para.push(lines[i])
          i += 1
        }
        blocks.push(h('p', { key: k(), style: { margin: '0 0 12px', lineHeight: 1.85 } }, renderInline(para.join(' '), k(), opts)))
      }
      return h('div', { style: { color: '#dcdce2' } }, blocks)
    }

    // ---------------- 阅读区共用小组件 ----------------

    function MetaStrip({ items }) {
      const shown = (items || []).filter((x) => x && x.value)
      if (!shown.length) return null
      return h('div', { style: { marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: '14px 30px' } },
        shown.map((x) => h('div', { key: x.label, style: { display: 'flex', flexDirection: 'column', gap: 3 } },
          h('div', { style: { fontSize: 11.5, color: T.caption } }, x.label),
          h('div', { style: { fontFamily: mono, fontSize: 12.5, color: T.text2, fontVariantNumeric: 'tabular-nums' } }, x.value))))
    }

    function ConceptChip({ name, title }) {
      return h('span', {
        title: title || '概念 · ' + name,
        style: { display: 'inline-flex', alignItems: 'center', gap: 6, height: 25, padding: '0 9px', borderRadius: 6, background: hexA(CONCEPT_COLOR, 0.13), color: CONCEPT_COLOR, fontSize: 12, whiteSpace: 'nowrap' },
      }, h('span', { style: { width: 5, height: 5, borderRadius: '50%', background: CONCEPT_COLOR } }), name)
    }

    function TaxChip({ id }) {
      const color = tagColor(id)
      const label = String(id).replace(/^([^/-]+)[/-]/, '$1 · ')
      return h('span', {
        title: String(id),
        style: { display: 'inline-flex', alignItems: 'center', gap: 6, height: 25, padding: '0 9px', borderRadius: 6, background: hexA(color, 0.13), color, fontSize: 12, whiteSpace: 'nowrap' },
      }, h('span', { style: { width: 5, height: 5, borderRadius: '50%', background: color } }), label)
    }

    function RailHead({ title, count }) {
      return h('div', { style: { padding: '16px 16px 10px', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' } },
        h('div', { style: { fontSize: 13, fontWeight: 600, color: T.text2 } }, title),
        h('span', { style: { fontFamily: mono, fontSize: 12, color: T.caption, fontVariantNumeric: 'tabular-nums' } }, count))
    }

    function RailSearch({ value, onChange, placeholder }) {
      return h('div', {
        style: { margin: '0 12px 8px', height: 36, display: 'flex', alignItems: 'center', gap: 8, padding: '0 11px', background: T.bg2, border: '1px solid transparent', borderRadius: 8 },
      },
        h('svg', { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none', style: { flex: '0 0 auto', opacity: 0.55 } },
          h('circle', { cx: 7, cy: 7, r: 4.6, stroke: 'currentColor', strokeWidth: 1.5 }),
          h('path', { d: 'M10.5 10.5 14 14', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' })),
        h('input', {
          value,
          onChange: (e) => onChange(e.target.value),
          placeholder,
          style: { flex: '1 1 auto', minWidth: 0, border: 'none', background: 'transparent', color: T.text, fontSize: 13.5, fontFamily: 'inherit', caretColor: ACCENT },
        }))
    }

    function ReaderEmpty({ title, sub }) {
      return h('div', { style: { height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 24 } },
        h('div', { style: { fontSize: 14.5, fontWeight: 600, color: T.text2 } }, title),
        sub ? h('div', { style: { fontSize: 12.5, color: T.caption, textAlign: 'center' } }, sub) : null)
    }

    function ReaderPane({ children }) {
      return h('div', { style: { minHeight: 0, overflowY: 'auto' } },
        h('div', { style: { maxWidth: 760, padding: '30px 32px 72px', boxSizing: 'border-box' } }, children))
    }

    function DocActions({ children }) {
      return h('div', { style: { flex: '0 0 auto', display: 'flex', gap: 6, marginTop: 2 } }, children)
    }

    function H2({ children }) {
      return h('div', { style: { margin: '30px 0 10px', paddingTop: 14, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: FS.sub, fontWeight: 600, color: T.text } }, children)
    }

    function SetupCard({ setup, onSaved }) {
      const [key, setKey] = useState('')
      const [vault, setVault] = useState(setup.vault || '')
      const [dataRoot, setDataRoot] = useState(setup.dataRoot || '')
      const [toolsDir, setToolsDir] = useState(setup.toolsDir || '')
      const [msg, setMsg] = useState(null)
      const [busy, setBusy] = useState(false)

      const post = async (p, body) => {
        const r = await fetch('/paperdepot/api' + p, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        return { status: r.status, json: await r.json() }
      }

      const saveKey = async () => {
        setBusy(true)
        setMsg(null)
        try {
          const r = await post('/setup/key', { key: key.trim() })
          if (r.json.ok) {
            setMsg({ ok: true, text: '已保存，MinerU 验证通过：' + (r.json.probe && r.json.probe.message ? r.json.probe.message : 'ok') })
            setKey('')
            onSaved && onSaved()
          } else {
            setMsg({ ok: false, text: r.json.error || 'HTTP ' + r.status })
          }
        } catch (e) {
          setMsg({ ok: false, text: String(e) })
        }
        setBusy(false)
      }

      const saveVault = async () => {
        setBusy(true)
        setMsg(null)
        try {
          const r = await post('/setup/vault', { vault: vault.trim() })
          if (r.json.ok) {
            setMsg({ ok: true, text: '库路径已保存：' + r.json.vault })
            onSaved && onSaved()
          } else {
            setMsg({ ok: false, text: r.json.error || 'HTTP ' + r.status })
          }
        } catch (e) {
          setMsg({ ok: false, text: String(e) })
        }
        setBusy(false)
      }

      const savePaths = async () => {
        setBusy(true)
        setMsg(null)
        try {
          const r = await post('/setup/paths', { dataRoot: dataRoot.trim(), toolsDir: toolsDir.trim() })
          if (r.json.ok) {
            setMsg({ ok: true, text: '路径已保存' })
            onSaved && onSaved()
          } else {
            setMsg({ ok: false, text: r.json.error || 'HTTP ' + r.status })
          }
        } catch (e) {
          setMsg({ ok: false, text: String(e) })
        }
        setBusy(false)
      }

      return h(
        'div',
        { style: { marginTop: SP.lg, padding: '18px 20px', borderRadius: R.lg, border: `1px solid ${line}`, background: card } },
        h('div', { style: { fontSize: FS.title, fontWeight: 700 } }, setup.hasKey ? '⚙️ 论文库配置' : '👋 第一次用论文库，先做一次配置'),
        h(
          'div',
          { style: { fontSize: FS.body, color: muted, marginTop: SP.xs, lineHeight: 1.7 } },
          '论文库用 MinerU 把 PDF 解析成 Markdown。请使用你自己的 MinerU Token（免费额度足够日常用，也不会占用别人的配额）。',
        ),
        h(
          'ol',
          { style: { fontSize: FS.body, lineHeight: 1.9, margin: '10px 0 0 18px', padding: 0 } },
          h('li', null, '打开 ', h('a', { href: 'https://mineru.net', target: '_blank', rel: 'noreferrer', style: { color: ACCENT } }, 'mineru.net'), '，注册 / 登录'),
          h('li', null, '进控制台 → API 管理（Token），创建一个 Token'),
          h('li', null, '把 Token 粘到下面，点「保存并验证」；看到 ✅ 就能拖 PDF 导入了'),
        ),
        h(
          'div',
          { style: { display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' } },
          h('input', {
            value: key,
            onChange: (e) => setKey(e.target.value),
            placeholder: 'sk-...（只保存在本机配置文件里，不会上传）',
            type: 'password',
            style: { flex: '1 1 320px', height: 36, padding: '0 12px', borderRadius: R.sm, border: `1px solid ${line}`, background: 'transparent', color: 'inherit', fontSize: FS.body },
          }),
          h(Btn, { primary: true, disabled: busy || !key.trim(), onClick: saveKey }, busy ? '验证中…' : '保存并验证'),
        ),
        msg ? h('div', { style: { marginTop: SP.sm, fontSize: FS.body, color: msg.ok ? T.text : ERROR_TEXT } }, (msg.ok ? '✅ ' : '❌ ') + msg.text) : null,
        h(
          'div',
          { style: { marginTop: 14, paddingTop: 12, borderTop: `1px dashed ${line}` } },
          h('div', { style: { fontSize: FS.body, fontWeight: 600 } }, 'Obsidian 库路径'),
          h(
            'div',
            { style: { display: 'flex', gap: SP.sm, marginTop: 6, flexWrap: 'wrap' } },
            h('input', {
              value: vault,
              onChange: (e) => setVault(e.target.value),
              placeholder: 'C:\\Users\\<你>\\Documents\\ObsidianVault',
              style: { flex: '1 1 360px', height: 36, padding: '0 12px', borderRadius: R.sm, border: `1px solid ${line}`, background: 'transparent', color: 'inherit', fontSize: FS.body },
            }),
            h(Btn, { disabled: busy, onClick: saveVault }, '保存路径'),
          ),
          h('div', { style: { fontSize: FS.caption, color: muted, marginTop: SP.xs } }, setup.vaultExists ? '✓ 目录存在' : '⚠ 目录不存在（先建一个空文件夹也可以）'),
        ),
        h(
          'div',
          { style: { marginTop: 14, paddingTop: 12, borderTop: `1px dashed ${line}` } },
          h('div', { style: { fontSize: FS.body, fontWeight: 600 } }, '数据目录（MinerU 缓存 / digest / 收件箱）'),
          h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 2 } }, '默认：' + (setup.dataRoot || '') + '　（缓存可删可重建，可换到别的盘）'),
          h(
            'div',
            { style: { display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' } },
            h('input', {
              value: dataRoot,
              onChange: (e) => setDataRoot(e.target.value),
              style: { flex: '1 1 360px', height: 36, padding: '0 12px', borderRadius: R.sm, border: `1px solid ${line}`, background: 'transparent', color: 'inherit', fontSize: FS.body },
            }),
            h(Btn, { disabled: busy, onClick: savePaths }, '保存路径'),
          ),
          h('div', { style: { fontSize: FS.body, fontWeight: 600, marginTop: 10 } }, '流水线目录（论文库 tools/，需含 ingest.py）'),
          h(
            'div',
            { style: { display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' } },
            h('input', {
              value: toolsDir,
              onChange: (e) => setToolsDir(e.target.value),
              placeholder: '<仓库路径>\\tools',
              style: { flex: '1 1 360px', height: 36, padding: '0 12px', borderRadius: R.sm, border: `1px solid ${line}`, background: 'transparent', color: 'inherit', fontSize: FS.body },
            }),
            h(Btn, { disabled: busy, onClick: savePaths }, '保存路径'),
          ),
          h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 4 } },
            setup.pipelineOk ? '✓ 流水线就绪' : '⚠ 未找到 ingest.py：插件内置流水线缺失；源码运行请指向仓库 tools/ 目录'),
        ),
        h(
          'div',
          { style: { marginTop: 12, fontSize: FS.caption, color: muted, lineHeight: 1.8 } },
          `Python：${setup.python && setup.python.ok ? '✅ ' + (setup.python.version || '可用') : '❌ 未找到（' + ((setup.python && setup.python.exe) || 'python') + '）'}`,
          h('br'),
          `MinerU key：${setup.keySource === 'env' ? '来自环境变量 MINERU_API_KEY' : setup.hasKey ? '已保存（…' + setup.keyTail + '）' : '未配置'}`,
          h('br'),
          `密钥文件：${setup.secretsPath}`,
        ),
      )
    }

    function Guide() {
      const [open, setOpen] = useState(false)
      return h(
        'div',
        { style: { marginTop: 18 } },
        h(Btn, { onClick: () => setOpen(!open) }, open ? '收起使用指引' : '使用指引'),
        open
          ? h(
              'div',
              { style: { fontSize: FS.body, lineHeight: 2, color: muted, marginTop: SP.sm, padding: '12px 16px', borderRadius: R.md, background: card, border: `1px solid ${line}` } },
              h('b', null, '① 导入：'),
              '把 PDF 拖到「论文库」面板任意位置、点「选择 PDF」，或在输入框粘贴本地路径（D:\\...\\x.pdf）按回车。同一 PDF 已入库会按指纹跳过。',
              h('br'),
              h('b', null, '② 自动处理：'),
              'MinerU 解析 → 元数据 → LLM 摘要/标签 → 写入 Obsidian。单篇约 1–3 分钟，日志会实时显示。',
              h('br'),
              h('b', null, '③ 浏览：'),
              '「总览」看统计；「论文」页可搜索、按标签筛选、只看待补；「概念」页看概念页与相关论文。关系图在 Obsidian 原生 Graph 里看。',
              h('br'),
              h('b', null, '④ 在 Obsidian 里：'),
              '点「打开 Obsidian」或条目里的「在 Obsidian 打开」；图视图已按领域上色，金色是分类页、紫色是概念页；打开论文后用 ⋯ → Open local graph 看它的邻居。',
              h('br'),
              h('b', null, '⑤ 维护：'),
              '导入/补摘要会自动更新导航块；批量改动后点「重建导航」重跑分类页与颜色分组。',
            )
          : null,
      )
    }

    function ImportBar({ running, log, setLog, uploadFiles, startPolling, compact }) {
      const fileRef = useRef(null)
      const [showLog, setShowLog] = useState(true)
      const pick = () => {
        if (!running) fileRef.current && fileRef.current.click()
      }
      return h(
        'div',
        {
          style: {
            padding: compact ? '12px 14px' : SP.lg,
            borderRadius: R.lg,
            background: card,
            border: `1px solid ${line}`,
            display: 'flex',
            flexDirection: 'column',
            gap: SP.md,
          },
        },
        h(
          'div',
          { style: { display: 'flex', alignItems: 'center', gap: SP.md, flexWrap: 'wrap' } },
          h(
            'div',
            {
              style: {
                width: 40, height: 40, borderRadius: R.md, flex: '0 0 auto',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: running ? 'rgba(196,123,30,0.16)' : 'rgba(77,107,254,0.14)', fontSize: 20,
              },
            },
            running ? '⏳' : '📥',
          ),
          h(
            'div',
            { style: { flex: '1 1 220px', minWidth: 0 } },
            h('div', { style: { fontSize: FS.sub, fontWeight: 600 } }, running ? '正在导入…' : '导入 PDF'),
            h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 2 } },
              running ? 'MinerU 解析 → 元数据 → 组装条目 → 生成摘要 → 重建索引' : '拖入、粘贴或选择文件；已入库的同一 PDF 会按指纹自动跳过'),
          ),
          running ? null : h(Btn, { primary: true, onClick: pick }, '选择 PDF'),
        ),
        h('input', {
          ref: fileRef,
          type: 'file',
          accept: 'application/pdf',
          multiple: true,
          style: { display: 'none' },
          onChange: (e) => { const fs = e.target.files; if (!running) uploadFiles(fs); e.target.value = '' },
        }),
        compact
          ? null
          : h(
              'div',
              {
                onClick: pick,
                style: {
                  padding: '24px 16px',
                  border: `1.5px dashed ${running ? 'rgba(196,123,30,0.5)' : 'rgba(127,127,127,0.35)'}`,
                  borderRadius: R.md,
                  textAlign: 'center',
                  cursor: running ? 'not-allowed' : 'pointer',
                  background: 'rgba(127,127,127,0.03)',
                },
              },
              h('div', { style: { fontSize: FS.body, fontWeight: 600, color: running ? WARN_TEXT : 'inherit' } },
                running ? '处理中，请稍候…' : '把 PDF 拖到这里，或点击选择'),
              h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 4 } },
                '也可以复制 PDF 后在论文库面板里按 Ctrl+V'),
            ),
        log.length
          ? h(
              'div',
              null,
              h(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: SP.sm, marginBottom: SP.sm } },
                h('div', { style: { fontSize: FS.caption, color: muted } }, `运行日志（${log.length} 行）`),
                h('div', { style: { flex: '1 1 auto' } }),
                h(Btn, { small: true, ghost: true, onClick: () => setShowLog((v) => !v) }, showLog ? '收起' : '展开'),
              ),
              showLog
                ? h('pre', {
                    style: {
                      margin: 0,
                      maxHeight: 220,
                      overflow: 'auto',
                      fontSize: 12,
                      lineHeight: 1.6,
                      background: T.bg2,
                      border: `1px solid ${line}`,
                      borderRadius: R.md,
                      padding: '10px 12px',
                      fontFamily: mono,
                      whiteSpace: 'pre-wrap',
                      color: 'inherit',
                    },
                  }, log.join('\n'))
                : null,
            )
          : null,
      )
    }

    function ImportDialog({ open, onClose, running, log, uploadFiles }) {
      const fileRef = useRef(null)
      const [showLog, setShowLog] = useState(false)
      if (!open) return null
      const txt = log.join('\n')
      const stages = [
        { label: 'MinerU 解析', done: /缓存命中|MinerU|解析|页 \d|图 \d/.test(txt) },
        { label: '元数据', done: /元数据|DOI|arXiv/.test(txt) },
        { label: '摘要与标签', done: /摘要|标签|生成中/.test(txt) },
        { label: '写入索引', done: /索引|分类页|完成：/.test(txt) },
      ]
      const firstUndone = stages.findIndex((s) => !s.done)
      return h('div', {
        onClick: (e) => { if (e.target === e.currentTarget) onClose() },
        style: {
          position: 'fixed', inset: 0, zIndex: 50, background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
        },
      },
        h('div', {
          style: {
            width: 'min(560px, 100%)', borderRadius: R.lg, background: T.bg,
            border: `1px solid ${T.b2}`, boxShadow: '0 24px 60px rgba(0,0,0,0.45)',
            padding: 20, color: T.text, fontFamily: T.font, maxHeight: '92vh', overflowY: 'auto',
          },
        },
          h('div', { style: { fontSize: 17, fontWeight: 650 } }, '导入 PDF'),
          h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 4 } },
            '拖入、粘贴或选择文件；已入库的同一 PDF 会按指纹自动跳过。'),
          h('div', {
            onClick: () => { if (!running) fileRef.current && fileRef.current.click() },
            style: {
              marginTop: SP.lg, padding: '26px 16px', textAlign: 'center',
              border: `1.5px dashed ${running ? 'rgba(196,123,30,0.5)' : line}`,
              borderRadius: R.md, background: T.bg1,
              cursor: running ? 'not-allowed' : 'pointer',
            },
          },
            h('div', { style: { fontSize: FS.body, fontWeight: 600, color: running ? WARN_TEXT : T.text } },
              running ? '处理中，请稍候…' : '把 PDF 拖到这里，或点击选择'),
            h('div', { style: { fontSize: FS.caption, color: muted, marginTop: 3 } },
              '也可以复制 PDF 后在论文库面板里按 Ctrl+V'),
            h('input', {
              ref: fileRef, type: 'file', accept: 'application/pdf', multiple: true,
              style: { display: 'none' },
              onChange: (e) => { const fs = e.target.files; if (!running) uploadFiles(fs); e.target.value = '' },
            })),
          h('div', { style: { display: 'flex', gap: 6, marginTop: SP.lg } },
            stages.map((s, i) =>
              h('div', {
                key: s.label,
                style: {
                  flex: 1, paddingTop: 7,
                  borderTop: `2px solid ${s.done ? GREEN : running && i === firstUndone ? ACCENT : line}`,
                  fontSize: 12.5,
                  color: s.done ? T.text2 : running && i === firstUndone ? T.text : T.caption,
                },
              }, s.label))),
          running ? h('div', { style: { marginTop: 6, fontSize: 12.5, color: muted } }, '可以关闭此窗口，后台继续处理') : null,
          log.length
            ? h('div', { style: { marginTop: SP.md } },
                h(Btn, { small: true, ghost: true, onClick: () => setShowLog((v) => !v) }, showLog ? '收起日志' : `查看日志（${log.length} 行）`),
                showLog
                  ? h('pre', {
                      style: {
                        marginTop: SP.sm, marginBottom: 0, maxHeight: 200, overflow: 'auto',
                        fontSize: 12.5, lineHeight: 1.55, background: T.bg2,
                        border: `1px solid ${line}`, borderRadius: R.sm, padding: '8px 10px',
                        fontFamily: mono, whiteSpace: 'pre-wrap', color: 'inherit',
                      },
                    }, log.slice(-40).join('\n'))
                  : null)
            : null,
          h('div', { style: { marginTop: SP.lg, display: 'flex', justifyContent: 'flex-end', gap: SP.sm } },
            h(Btn, { ghost: true, onClick: onClose }, running ? '后台运行' : '关闭'))),
      )
    }

    function Overview({ d, onOpen }) {
      const tagItems = (d.tags || []).slice(0, 14).map((t) => ({ key: t.tag, label: t.tag, value: t.count, color: tagColor(t.tag) }))
      const yearItems = (d.years || []).slice(-14).map((y) => ({ key: String(y.year), label: String(y.year), value: y.count }))
      return h(
        'div',
        null,
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: SP.md } },
          h(Card, { label: '论文条目', value: fmt(d.papers) }),
          h(Card, { label: '概念页', value: fmt(d.concepts), accent: d.concepts ? CONCEPT_COLOR : undefined }),
          h(Card, { label: '待补元数据', value: fmt(d.pendingMeta), accent: d.pendingMeta ? WARN_TEXT : undefined }),
          h(Card, { label: '待生成摘要', value: fmt(d.pendingSummary), accent: d.pendingSummary ? WARN_TEXT : undefined, sub: d.pendingSummary ? '导入后未跑摘要' : '全部齐全' }),
        ),
        h(Section, { title: '最近入库' },
          (d.recent || []).length
            ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
                d.recent.slice(0, 6).map((r) =>
                  h('div', {
                    key: r.dir,
                    title: r.title,
                    onClick: () => onOpen && onOpen(r.dir),
                    style: {
                      display: 'flex', alignItems: 'center', gap: SP.md,
                      padding: '10px 12px', borderRadius: R.md,
                      background: card, border: `1px solid ${line}`,
                      cursor: 'pointer',
                    },
                  },
                    h('div', { style: { width: 46, flex: '0 0 auto', fontSize: FS.caption, color: faint } }, r.year || '—'),
                    h('div', { style: { flex: '1 1 auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: FS.body } }, r.title),
                    r.pending ? h(Chip, { title: '还没有摘要' }, '待总结') : null)))
            : h(Empty, null, '还没有论文，从上方导入第一篇 PDF')),
        h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: SP.xl } },
          h(Section, { title: `年份分布（${(d.years || []).length} 个年份）`, style: { marginTop: SP.xl } }, h(Bars, { items: yearItems, color: ACCENT })),
          h(Section, { title: `标签 Top ${tagItems.length}`, style: { marginTop: SP.xl } }, h(Bars, { items: tagItems, color: `color-mix(in srgb, ${GREEN} 55%, transparent)` })),
        ),
        h(Section, { title: '期刊 Top 10' }, h(Bars, { items: (d.journals || []).map((j) => ({ key: j.journal, label: j.journal, value: j.count })), color: `color-mix(in srgb, ${ORANGE} 60%, transparent)` })),
        (d.conceptNames || []).length
          ? h(Section, { title: `概念层（${d.concepts} 页）` },
              h('div', { style: { display: 'flex', gap: SP.sm, flexWrap: 'wrap' } },
                d.conceptNames.map((n) => h(ConceptChip, { key: n, name: n }))))
          : null,
      )
    }

    // 批量补摘要进度条：贴在内容区底部，任务结束后保留可收起
    function BatchBar({ job, onCancel, onClose }) {
      const failed = (job.failed || []).length
      const ok = Math.max(0, (job.done || 0) - failed)
      const label = job.state === 'running'
        ? `批量补摘要：${job.done || 0}/${job.total || 0}${failed ? `，失败 ${failed}` : ''}`
        : `批量补摘要结束：成功 ${ok}/${job.total || 0}${failed ? `，失败 ${failed}` : ''}${job.state === 'cancelled' ? '（已停止，再点继续）' : ''}`
      return h(
        'div',
        {
          style: {
            position: 'absolute', left: 20, right: 20, bottom: 24, zIndex: 30,
            background: T.bg1, border: `1px solid ${line}`, borderRadius: R.md,
            boxShadow: '0 10px 30px rgba(0,0,0,0.28)', padding: '10px 12px',
            display: 'flex', flexDirection: 'column', gap: 6,
          },
        },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: SP.md } },
          h('div', { style: { flex: '1 1 auto', fontSize: FS.body, fontWeight: 600 } }, label),
          job.state === 'running'
            ? h(Btn, { small: true, ghost: true, onClick: onCancel, title: '跑完当前这篇后停下，下次再点继续' }, '停止')
            : h(Btn, { small: true, ghost: true, onClick: onClose }, '收起')),
        h('div', {
          style: {
            fontFamily: mono, fontSize: 11.5, color: muted, lineHeight: 1.5,
            maxHeight: 88, overflowY: 'auto', whiteSpace: 'pre-wrap',
          },
        }, (job.lines || []).slice(-5).join('\n')))
    }

    function Papers({ papers, loading, onSelect, selected, selectedData, onSummarize, running, vaultName }) {
      const [q, setQ] = useState('')
      const [domain, setDomain] = useState('')
      const [onlyPending, setOnlyPending] = useState(false)
      const [hovered, setHovered] = useState('')
      const domains = [...new Set((papers || []).flatMap((p) => p.tags.filter((t) => t.startsWith('领域/')).map((t) => t.slice(3))))].sort((a, b) => a.localeCompare(b, 'zh'))
      const items = (papers || []).filter((p) => {
        if (onlyPending && !p.pending) return false
        if (domain && !p.tags.includes('领域/' + domain)) return false
        if (!q) return true
        return `${p.title} ${p.year} ${p.journal} ${p.tags.join(' ')}`.toLowerCase().includes(q.toLowerCase())
      })
      const rows = items.map((p) => {
        const on = selected === p.dir
        const dom = domainOfPaper(p)
        const domColor = domainColor(dom, domains)
        const meta = p.journal || dom || '—'
        return h(
          'div',
          {
            key: p.dir,
            onClick: () => onSelect(p.dir),
            onMouseEnter: () => setHovered(p.dir),
            onMouseLeave: () => setHovered(''),
            title: p.title,
            style: {
              position: 'relative', display: 'grid', gridTemplateColumns: '38px 1fr', gap: 10,
              padding: '10px 10px 11px', borderRadius: 8, cursor: 'pointer',
              background: on ? 'rgba(77,107,254,0.12)' : hovered === p.dir ? hoverBg : 'transparent',
            },
          },
          on ? h('div', { style: { position: 'absolute', left: 0, top: 9, bottom: 9, width: 2, borderRadius: 2, background: ACCENT } }) : null,
          h('div', { style: { fontFamily: mono, fontSize: 12, color: T.text3, paddingTop: 2, fontVariantNumeric: 'tabular-nums' } }, p.year || '—'),
          h('div', { style: { minWidth: 0 } },
            h('div', {
              style: {
                fontSize: 13.5, lineHeight: 1.45, fontWeight: 550, display: '-webkit-box',
                WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
              },
            }, p.title),
            h('div', { style: { marginTop: 4, display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, fontSize: 12, color: T.caption } },
              h('span', { style: { flex: '1 1 auto', display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 } },
                h('span', { style: { flex: '0 0 auto', display: 'inline-flex', alignItems: 'center', gap: 5, color: dom ? domColor : T.caption } },
                  h('span', { style: { width: 5, height: 5, borderRadius: '50%', background: dom ? domColor : 'transparent' } }), dom || '—'),
                h('span', { style: { flex: '1 1 auto', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, p.journal || '')),
              p.pending
                ? h('span', { style: { flex: '0 0 auto', color: ORANGE, display: 'inline-flex', alignItems: 'center', gap: 4 } },
                    h('span', { style: { width: 5, height: 5, borderRadius: '50%', background: 'currentColor' } }), '待总结')
                : null)))
      })
      const left = h(
        'div',
        { style: { minHeight: 0, display: 'flex', flexDirection: 'column', background: T.bg1, borderRight: `1px solid ${line}` } },
        h(RailHead, { title: '论文', count: fmt((papers || []).length) }),
        h(RailSearch, { value: q, onChange: setQ, placeholder: '搜索标题 / 年份 / 期刊 / 标签' }),
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px 10px' } },
          h('select', {
            value: domain,
            onChange: (e) => setDomain(e.target.value),
            style: {
              flex: '1 1 auto', minWidth: 0, height: 26, padding: '0 8px', border: 'none',
              borderRadius: 6, background: T.bg2, color: T.text2, fontSize: 12.5,
            },
          }, [h('option', { key: '', value: '' }, '全部领域')].concat(domains.map((d) => h('option', { key: d, value: d }, d)))),
          h('label', { style: { display: 'flex', alignItems: 'center', gap: 6, color: T.text2, cursor: 'pointer', whiteSpace: 'nowrap', fontSize: 12.5 } },
            h('input', { type: 'checkbox', checked: onlyPending, onChange: (e) => setOnlyPending(e.target.checked), style: { accentColor: ACCENT, margin: 0 } }),
            '只看待补')),
        h('div', { style: { padding: '0 16px 8px', fontSize: 12, color: T.caption, fontVariantNumeric: 'tabular-nums' } }, `显示 ${items.length} / ${(papers || []).length} 篇`),
        loading
          ? h('div', { style: { color: muted, fontSize: FS.body, padding: '8px 16px' } }, '加载中…')
          : h('div', { style: { flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '0 8px 32px' } }, rows),
      )
      const right = h(
        'div',
        { style: { minHeight: 0, overflowY: 'auto' } },
        selected && selectedData
          ? h(ReaderPane, null,
              selectedData.pending
                ? h('div', {
                    style: {
                      display: 'flex', alignItems: 'center', gap: SP.md, marginBottom: 20,
                      padding: '10px 14px', borderRadius: 8, background: 'rgba(196,123,30,0.10)', border: '1px solid rgba(196,123,30,0.30)',
                    },
                  },
                    h('span', { style: { fontSize: FS.body, flex: '1 1 auto' } }, '这篇条目还没有摘要与标签'),
                    h(Btn, { small: true, primary: true, disabled: running, onClick: () => onSummarize(selected) }, running ? '处理中…' : '生成摘要与标签'))
                : null,
              h(PaperPreview, { data: selectedData, onOpenPaper: onSelect }))
          : h(ReaderEmpty, { title: '从左侧选一篇论文', sub: '可搜索、按领域筛选、只看待补；条目内容按摘要排版显示' }),
      )
      return h('div', { style: { display: 'grid', gridTemplateColumns: '336px 1fr', height: '100%', minHeight: 0 } }, left, right)
    }

    // obsidian:// 只能由宿主侧拉起：桌面版对自定义协议的 window.open 一律 deny
    async function openObsidianApi(payload) {
      const r = await fetch('/paperdepot/api/open-obsidian', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      return await r.json()
    }

    function PaperPreview({ data, onOpenPaper }) {
      const [msg, setMsg] = useState('')
      if (!data) return null
      const fm = parsePaperFrontmatter(data.index)
      const rel = `1-Papers/${data.dir}/index.md`
      const copyPath = () => {
        try {
          navigator.clipboard && navigator.clipboard.writeText(rel)
        } catch {
          /* ignore */
        }
      }
      const openInObsidian = async () => {
        setMsg('')
        try {
          const j = await openObsidianApi({ dir: data.dir })
          if (!j.ok) {
            copyPath()
            setMsg('Obsidian 没响应（' + (j.error || '未知原因') + '），已复制条目路径')
          }
        } catch (e) {
          copyPath()
          setMsg('打开失败：' + String(e) + '，已复制条目路径')
        }
      }
      const meta = [
        { label: '年份', value: fm.year },
        { label: '期刊/会议', value: fm.journal },
        { label: 'DOI', value: fm.doi || (fm.arxiv ? 'arXiv ' + fm.arxiv : '') },
        { label: '篇幅', value: [fm.pages && fm.pages + ' 页', fm.figures && fm.figures + ' 图'].filter(Boolean).join(' · ') },
        { label: '引用键', value: fm.citekey },
      ]
      const concepts = data.concepts || []
      const taxonomy = (data.taxonomy || []).slice().sort((a, b) => {
        const order = ['领域', '方法', '应用', '仪器']
        return order.indexOf(tagCategory(a)) - order.indexOf(tagCategory(b))
      })
      return h(
        'div',
        null,
        h('div', { style: { display: 'flex', alignItems: 'flex-start', gap: 16 } },
          h('div', { style: { flex: '1 1 auto', fontSize: FS.page, lineHeight: 1.4, fontWeight: 650 } }, fm.title || data.dir),
          h(DocActions, null,
            h(Btn, { small: true, ghost: true, onClick: copyPath, title: '复制库内相对路径' }, '复制路径'),
            h(Btn, { small: true, onClick: openInObsidian, title: '用 Obsidian 打开这篇笔记' }, '在 Obsidian 打开'))),
        h(MetaStrip, { items: meta }),
        msg ? h('div', { style: { fontSize: FS.caption, color: ERROR_TEXT, marginTop: SP.xs } }, msg) : null,
        concepts.length || taxonomy.length
          ? h('div', { style: { marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 6 } },
              concepts.map((c) => h(ConceptChip, { key: 'c' + c, name: c })),
              taxonomy.map((t) => h(TaxChip, { key: 't' + t, id: t })))
          : null,
        h('div', { style: { marginTop: 26 } }, h(Markdown, { source: data.index, ledeHeading: '一句话总结', onOpenPaper })),
      )
    }

    function layoutGraph(data) {
      const W = 1000
      const H = 660
      const cx = W / 2
      const cy = H / 2
      const papers = data.papers || []
      const concepts = data.concepts || []
      const taxonomy = data.taxonomy || []
      const nodes = []

      // 论文：中心小环（数量少时聚在中心）
      const pr = papers.length <= 1 ? 0 : Math.min(110, 26 + Math.sqrt(papers.length) * 12)
      papers.forEach((p, i) => {
        const a = (i / Math.max(1, papers.length)) * Math.PI * 2 - Math.PI / 2
        nodes.push({ id: 'p:' + p.id, kind: 'paper', ref: p, x: cx + Math.cos(a) * pr, y: cy + Math.sin(a) * pr })
      })

      // 概念：内环
      concepts.forEach((c, i) => {
        const a = (i / Math.max(1, concepts.length)) * Math.PI * 2 - Math.PI / 2
        nodes.push({ id: 'c:' + c.id, kind: 'concept', ref: c, x: cx + Math.cos(a) * 155, y: cy + Math.sin(a) * 155 })
      })

      // 分类：按「领域/方法/应用/仪器」分四个扇区，各自扇形排布，避免成一团
      const catOrder = ['领域', '方法', '应用', '仪器']
      const groups = {}
      for (const t of taxonomy) {
        const cat = t.category || (t.title || '').split('-')[0] || '其他'
        ;(groups[cat] = groups[cat] || []).push(t)
      }
      const cats = catOrder.filter((c) => groups[c]).concat(Object.keys(groups).filter((c) => !catOrder.includes(c)))
      const span = (Math.PI * 2) / Math.max(1, cats.length)
      cats.forEach((cat, ci) => {
        const items = groups[cat].slice().sort((a, b) => (b.papers || []).length - (a.papers || []).length)
        const start = ci * span - Math.PI / 2 + 0.08
        const usable = span - 0.16
        items.forEach((t, i) => {
          const a = start + (usable * (i + 0.5)) / Math.max(1, items.length)
          const ring = 250 + (i % 2) * 72 + Math.min(70, Math.floor(i / 2) * 12)
          nodes.push({
            id: 't:' + t.id, kind: 'taxonomy', ref: t, angle: a,
            x: cx + Math.cos(a) * ring, y: cy + Math.sin(a) * ring,
          })
        })
      })

      const idx = new Map(nodes.map((n, i) => [n.id, i]))
      const links = []
      for (const e of data.edges || []) {
        const l = { a: idx.get('p:' + e.paper), b: idx.get('c:' + e.concept), kind: 'concept' }
        if (l.a != null && l.b != null) links.push(l)
      }
      for (const e of data.taxEdges || []) {
        const l = { a: idx.get('p:' + e.paper), b: idx.get('t:' + e.taxonomy), kind: 'taxonomy' }
        if (l.a != null && l.b != null) links.push(l)
      }
      const degree = new Map()
      for (const l of links) {
        degree.set(l.a, (degree.get(l.a) || 0) + 1)
        degree.set(l.b, (degree.get(l.b) || 0) + 1)
      }
      return { W, H, nodes, links, degree }
    }

    function GraphView({ onOpenPaper }) {
      const [data, setData] = useState(null)
      const [domain, setDomain] = useState('')
      const [focus, setFocus] = useState(null)
      const [hover, setHover] = useState(null)
      const [err, setErr] = useState('')

      useEffect(() => {
        ;(async () => {
          try {
            const d = await (await api('/graph')).json()
            if (d.ok) setData(d)
            else setErr(d.error || '加载失败')
          } catch (e) {
            setErr(String(e))
          }
        })()
      }, [])

      const domains = data ? [...new Set(data.papers.map((p) => p.domain || '其他'))].sort((a, b) => a.localeCompare(b, 'zh')) : []
      const sim = useMemo(() => (data ? layoutGraph(data) : null), [data])

      if (!data) return h('div', { style: { padding: 20, color: muted, fontSize: FS.body } }, err ? '读取失败：' + err : '正在计算关系图…')

      const conceptSet = (id) => new Set(((data.concepts || []).find((c) => c.id === id) || {}).papers || [])
      const taxSet = (id) => new Set(((data.taxonomy || []).find((t) => t.id === id) || {}).papers || [])
      const focusPapers = focus ? (focus.type === 'concept' ? conceptSet(focus.id) : taxSet(focus.id)) : null
      const visible = (p) => (!domain || (p.domain || '其他') === domain) && (!focusPapers || focusPapers.has(p.id))
      const paperById = new Map(data.papers.map((p) => [p.id, p]))
      const focusId = focus ? focus.type[0] + ':' + focus.id : ''
      const focusNeighbors = new Set()
      if (focusId) {
        focusNeighbors.add(focusId)
        for (const l of sim.links) {
          const a = sim.nodes[l.a]
          const b = sim.nodes[l.b]
          if (a.id === focusId) focusNeighbors.add(b.id)
          if (b.id === focusId) focusNeighbors.add(a.id)
        }
      }
      const trunc = (s, n) => {
        const t = String(s || '')
        return t.length > n ? t.slice(0, n) + '…' : t
      }
      const showTaxLabels = (data.taxonomy || []).length <= 14

      const toolbar = h('div', { style: { display: 'flex', alignItems: 'center', gap: SP.sm, flexWrap: 'wrap' } },
        h('span', { style: { fontSize: FS.caption, color: muted } }, '领域'),
        h('select', {
          value: domain,
          onChange: (e) => setDomain(e.target.value),
          style: { height: 30, padding: '0 9px', borderRadius: R.sm, border: `1px solid ${line}`, background: T.bg1, color: 'inherit', fontSize: FS.caption },
        }, [h('option', { key: '', value: '' }, '全部')].concat(domains.map((d) => h('option', { key: d, value: d }, d)))),
        h('span', { style: { fontSize: FS.caption, color: faint } },
          `论文 ${data.papers.length} · 概念 ${(data.concepts || []).length} · 分类 ${(data.taxonomy || []).length} · 边 ${sim.links.length}`),
        h('span', { style: { flex: '1 1 auto' } }),
        focus ? h(Btn, { small: true, onClick: () => setFocus(null) }, '取消聚焦') : null,
        h('span', { style: { fontSize: FS.caption, color: faint } }, '点分类/概念节点聚焦，点论文节点打开条目'))

      const dots = []
      for (const d of domains.slice(0, 10)) {
        dots.push(h('span', { key: 'd' + d, style: { display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: FS.caption, color: muted } },
          h('span', { style: { width: 8, height: 8, borderRadius: 999, background: domainColor(d, domains) } }), d || '其他'))
      }
      dots.push(h('span', { key: 'tax', style: { display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: FS.caption, color: muted } },
        h('span', { style: { width: 8, height: 8, borderRadius: 999, background: '#ffd700' } }), '分类'))
      dots.push(h('span', { key: 'con', style: { display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: FS.caption, color: muted } },
        h('span', { style: { width: 8, height: 8, borderRadius: 999, background: CONCEPT_COLOR } }), '概念'))

      const graph = (data.papers.length + (data.concepts || []).length) === 0
        ? h('div', { style: { height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: faint, fontSize: FS.body } }, '还没有论文或概念，导入几篇后这里会出现关系图')
        : h('svg', {
            viewBox: `0 0 ${sim.W} ${sim.H}`,
            preserveAspectRatio: 'xMidYMid meet',
            style: { width: '100%', height: '100%', display: 'block' },
          },
          sim.links.map((l, i) => {
            const a = sim.nodes[l.a]
            const b = sim.nodes[l.b]
            const hot = focusId ? a.id === focusId || b.id === focusId : false
            const active = !focus || hot
            return h('line', {
              key: 'l' + i,
              x1: a.x, y1: a.y, x2: b.x, y2: b.y,
              stroke: l.kind === 'taxonomy'
                ? (hot ? 'rgba(255,215,0,0.85)' : 'rgba(255,215,0,0.28)')
                : (hot ? 'rgba(167,139,250,0.9)' : 'rgba(167,139,250,0.30)'),
              strokeWidth: hot ? 1.6 : 1,
              opacity: active ? 1 : 0.15,
            })
          }),
          sim.nodes.map((n) => {
            const isConcept = n.kind === 'concept'
            const isTax = n.kind === 'taxonomy'
            const p = n.ref
            const linked = isConcept ? (data.concepts || []).find((c) => c.id === n.ref.id) : isTax ? (data.taxonomy || []).find((t) => t.id === n.ref.id) : null
            const vis = isConcept || isTax
              ? !domain || ((linked && linked.papers) || []).some((d) => visible(paperById.get(d) || { id: d }))
              : visible(p) || (!focus && !domain)
            const dim = focusId ? !focusNeighbors.has(n.id) : !vis
            const fill = isConcept ? CONCEPT_COLOR : isTax ? '#d5a94a' : domainColor(p.domain || '其他', domains)
            const deg = sim.degree.get(sim.nodes.indexOf(n)) || 0
            const r = isConcept ? 10 + Math.min(6, ((n.ref.papers || []).length || 0) / 8)
              : isTax ? 6 + Math.min(5, deg / 3)
                : 7
            const label = isConcept || isTax ? trunc(n.ref.title, 26) : trunc(p.title, 30)
            const showLabel = isConcept ? true : isTax ? (showTaxLabels || hover === n.id || focusId === n.id) : true
            const labelPos = isConcept
              ? { x: n.x, y: n.y - r - 7, anchor: 'middle' }
              : isTax
                ? { x: n.x + Math.cos(n.angle) * (r + 9), y: n.y + Math.sin(n.angle) * (r + 9), anchor: Math.cos(n.angle) >= 0 ? 'start' : 'end' }
                : { x: n.x, y: n.y + r + 14, anchor: 'middle' }
            return h('g', {
              key: n.id,
              style: { cursor: 'pointer', opacity: dim ? 0.18 : 1, transition: 'opacity .15s ease' },
              onMouseEnter: () => setHover(n.id),
              onMouseLeave: () => setHover((v) => (v === n.id ? null : v)),
              onClick: () => {
                if (isConcept || isTax) setFocus(focusId === n.id ? null : { type: isConcept ? 'concept' : 'taxonomy', id: n.ref.id })
                else onOpenPaper(p.id)
              },
            },
              h('circle', {
                cx: n.x, cy: n.y, r,
                fill,
                style: {
                  stroke: focusId === n.id ? T.accent : 'rgba(127,127,127,0.35)',
                  strokeWidth: focusId === n.id ? 2 : 1,
                },
              }),
              h('title', null, isConcept || isTax
                ? `${isConcept ? '概念' : '分类'}：${n.ref.title}（${((n.ref.papers || []).length)} 篇）`
                : `${p.title}（${p.year || '—'}）`),
              showLabel
                ? h('text', {
                    x: labelPos.x, y: labelPos.y, textAnchor: labelPos.anchor,
                    fontSize: isConcept ? 12 : 11.5,
                    style: {
                      pointerEvents: 'none',
                      fill: T.text2,
                      stroke: T.bg,
                      strokeWidth: 3,
                      paintOrder: 'stroke',
                    },
                  }, label)
                : null,
            )
          }),
        )

      return h('div', { style: { display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 } },
        toolbar,
        h('div', { style: { display: 'flex', gap: SP.md, flexWrap: 'wrap', marginTop: SP.sm } }, dots),
        h('div', {
          style: {
            flex: '1 1 auto', minHeight: 300, marginTop: SP.md,
            border: `1px solid ${line}`, borderRadius: R.lg,
            background: T.bg1, overflow: 'hidden',
          },
        }, graph))
    }

    function Concepts({ onOpenPaper, vaultName }) {
      const [items, setItems] = useState(null)
      const [active, setActive] = useState('')
      const [detail, setDetail] = useState(null)
      const [msg, setMsg] = useState('')
      const [q, setQ] = useState('')
      const [hovered, setHovered] = useState('')

      const rel = detail ? `2-Concepts/${detail.name}.md` : ''
      const openInObsidian = async () => {
        if (!detail) return
        setMsg('')
        try {
          const j = await openObsidianApi({ concept: detail.name })
          if (!j.ok) {
            try {
              navigator.clipboard && navigator.clipboard.writeText(rel)
            } catch {
              /* ignore */
            }
            setMsg('Obsidian 没响应（' + (j.error || '未知原因') + '），已复制概念页路径')
          }
        } catch (e) {
          setMsg('打开失败：' + String(e))
        }
      }
      const copyPath = () => {
        try {
          navigator.clipboard && navigator.clipboard.writeText(rel)
        } catch {
          /* ignore */
        }
      }

      useEffect(() => {
        ;(async () => {
          try {
            const d = await (await api('/concepts')).json()
            setItems(d.items || [])
          } catch {
            setItems([])
          }
        })()
      }, [])

      const open = async (name) => {
        setActive(name)
        try {
          const d = await (await api('/concept?name=' + encodeURIComponent(name))).json()
          if (d.ok) setDetail(d)
        } catch {
          /* ignore */
        }
      }

      const filtered = (items || []).filter((c) => {
        if (!q) return true
        const hay = `${c.name} ${c.title} ${(c.aliases || []).join(' ')} ${c.oneLiner || ''}`.toLowerCase()
        return hay.includes(q.toLowerCase())
      })

      const rows = filtered.map((c) => {
        const on = active === c.name
        return h(
          'div',
          {
            key: c.name,
            onClick: () => open(c.name),
            onMouseEnter: () => setHovered(c.name),
            onMouseLeave: () => setHovered(''),
            title: c.oneLiner || c.title,
            style: {
              position: 'relative', display: 'grid', gridTemplateColumns: '1fr auto', gap: 10,
              padding: '10px 10px 11px', borderRadius: 8, cursor: 'pointer',
              background: on ? 'rgba(77,107,254,0.12)' : hovered === c.name ? hoverBg : 'transparent',
            },
          },
          on ? h('div', { style: { position: 'absolute', left: 0, top: 9, bottom: 9, width: 2, borderRadius: 2, background: CONCEPT_COLOR } }) : null,
          h('div', { style: { minWidth: 0 } },
            h('div', { style: { display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 } },
              h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: CONCEPT_COLOR, flex: '0 0 auto' } }),
              h('div', { style: { fontSize: 14, fontWeight: 550, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, c.title || c.name)),
            c.oneLiner
              ? h('div', { style: { marginTop: 3, fontSize: 12, color: T.caption, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingLeft: 13 } }, c.oneLiner)
              : null),
          h('div', { style: { fontFamily: mono, fontSize: 12, color: hexA(CONCEPT_COLOR, 0.75), fontVariantNumeric: 'tabular-nums', paddingTop: 3 } }, String(c.papersCount || 0)))
      })

      const left = h(
        'div',
        { style: { minHeight: 0, display: 'flex', flexDirection: 'column', background: T.bg1, borderRight: `1px solid ${line}` } },
        h(RailHead, { title: '概念', count: items ? fmt(items.length) : '—' }),
        h(RailSearch, { value: q, onChange: setQ, placeholder: '搜索概念 / 别名' }),
        h('div', { style: { padding: '0 16px 8px', fontSize: 12, color: T.caption } }, '按引用论文数排序'),
        items
          ? h('div', { style: { flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '0 8px 32px' } }, rows)
          : h('div', { style: { color: muted, fontSize: FS.body, padding: '8px 16px' } }, '加载中…'),
      )

      const fm = detail ? parsePaperFrontmatter(detail.markdown) : {}
      const tags = (fm.tags || []).filter((t) => !t.startsWith('状态/'))
      const related = (detail && detail.papers ? detail.papers.slice() : []).sort((a, b) => (parseFloat(b.year || '0') || 0) - (parseFloat(a.year || '0') || 0))
      const right = h(
        'div',
        { style: { minHeight: 0, overflowY: 'auto' } },
        detail
          ? h(ReaderPane, null,
              h('div', { style: { display: 'flex', alignItems: 'flex-start', gap: 16 } },
                h('div', { style: { flex: '1 1 auto', fontSize: FS.page, lineHeight: 1.4, fontWeight: 650 } }, detail.title || detail.name),
                h(DocActions, null,
                  h(Btn, { small: true, ghost: true, onClick: copyPath, title: '复制库内相对路径' }, '复制路径'),
                  h(Btn, { small: true, onClick: openInObsidian, title: '用 Obsidian 打开概念页' }, '在 Obsidian 打开'))),
              h(MetaStrip, {
                items: [
                  { label: '类型', value: '概念页' },
                  { label: '引用', value: (detail.papersCount || 0) + ' 篇论文' },
                  { label: '别名', value: (fm.aliases || detail.aliases || []).slice(0, 4).join(' · ') },
                  { label: '更新', value: fm.updated },
                ],
              }),
              msg ? h('div', { style: { fontSize: FS.caption, color: ERROR_TEXT, marginTop: SP.xs } }, msg) : null,
              tags.length
                ? h('div', { style: { marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 6 } }, tags.map((t) => h(TaxChip, { key: t, id: t })))
                : null,
              h('div', { style: { marginTop: 26 } }, h(Markdown, { source: detail.markdown, ledeFirstQuote: true, onOpenPaper })),
              related.length
                ? h('div', null,
                    h(H2, null, '相关论文'),
                    h('div', null, related.map((p) => h('div', {
                      key: p.dir,
                      onClick: () => onOpenPaper(p.dir),
                      title: p.title,
                      onMouseEnter: () => setHovered('paper:' + p.dir),
                      onMouseLeave: () => setHovered(''),
                      style: {
                        display: 'grid', gridTemplateColumns: '42px 1fr', gap: 12, padding: '9px 8px', borderRadius: 7,
                        cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.045)',
                        background: hovered === 'paper:' + p.dir ? hoverBg : 'transparent',
                      },
                    },
                      h('div', { style: { fontFamily: mono, fontSize: 12, color: T.text3, paddingTop: 2, fontVariantNumeric: 'tabular-nums' } }, p.year || '—'),
                      h('div', { style: { fontSize: 13.5, lineHeight: 1.5 } }, p.title)))))
                : null)
          : h(ReaderEmpty, {
              title: items && items.length ? '从左侧选一个概念' : '还没有概念页',
              sub: items && items.length ? '概念页是跨论文综合，条目内容按摘要排版显示' : '概念页由 tools/ 下的素材、校验、索引脚本生成，规范见 config/CONCEPT_SPEC.md',
            }),
      )
      return h('div', { style: { display: 'grid', gridTemplateColumns: '300px 1fr', height: '100%', minHeight: 0 } }, left, right)
    }

    function PaperDepotView() {
      const [tab, setTab] = useState('papers')
      const [stats, setStats] = useState(null)
      const [papers, setPapers] = useState(null)
      const [papersLoading, setPapersLoading] = useState(false)
      const [selected, setSelected] = useState('')
      const [selectedData, setSelectedData] = useState(null)
      const [running, setRunning] = useState(false)
      const [log, setLog] = useState([])
      const [error, setError] = useState('')
      const [setup, setSetup] = useState(null)
      const [showSetup, setShowSetup] = useState(false)
      const [showImport, setShowImport] = useState(false)
      const [jobInfo, setJobInfo] = useState(null)


      const loadSetup = useCallback(async () => {
        try {
          setSetup(await (await api('/setup/status')).json())
        } catch {
          /* ignore */
        }
      }, [])

      const loadStats = useCallback(async () => {
        try {
          const d = await (await api('/stats')).json()
          setStats(d)
          setError('')
        } catch (e) {
          setError(String(e))
        }
      }, [])

      const loadPapers = useCallback(async () => {
        setPapersLoading(true)
        try {
          const d = await (await api('/papers?limit=1000')).json()
          setPapers(d.items || [])
        } catch (e) {
          setError(String(e))
        }
        setPapersLoading(false)
      }, [])

      const openPaper = useCallback(async (dir) => {
        setSelected(dir)
        try {
          const d = await (await api('/paper?dir=' + encodeURIComponent(dir))).json()
          if (d.ok) setSelectedData(d)
        } catch {
          /* ignore */
        }
      }, [])

      useEffect(() => { loadStats(); loadPapers(); loadSetup() }, [loadStats, loadPapers, loadSetup])

      const refreshAll = useCallback(() => { loadStats(); loadPapers() }, [loadStats, loadPapers])

      const startPolling = useCallback(async () => {
        setRunning(true)
        // 批量补摘要可能跑几个小时：轮询上限放到 ~3 小时，任务结束后立即退出
        for (let i = 0; i < 9000; i++) {
          await new Promise((r) => setTimeout(r, 1200))
          try {
            const j = await (await api('/job')).json()
            if (j.job) {
              setJobInfo(j.job)
              setLog((j.job.lines || []).slice(-300))
              if (j.job.state !== 'running') {
                setRunning(false)
                refreshAll()
                return
              }
            }
          } catch {
            /* keep polling */
          }
        }
        setRunning(false)
      }, [refreshAll, setLog, setRunning])

      // 面板级拖拽：整个「论文库」视图都可以接收 PDF，避免和底部对话输入框抢 drop
      const [dragOver, setDragOver] = useState(false)
      const uploadFiles = useCallback(async (files) => {
        const list = Array.from(files || []).filter((f) => /\.pdf$/i.test(f.name))
        if (!list.length) {
          setLog(['❌ 只支持 PDF 文件'])
          return
        }
        setLog([])
        setShowImport(true)
        for (const f of list) {
          setLog((old) => [...old, `↑ 上传 ${f.name}（${(f.size / 1024 / 1024).toFixed(1)} MB）`])
          try {
            const r = await fetch('/paperdepot/api/import?name=' + encodeURIComponent(f.name), {
              method: 'POST',
              credentials: 'same-origin',
              headers: { 'Content-Type': 'application/pdf' },
              body: f,
            })
            const j = await r.json()
            if (!j.ok) setLog((old) => [...old, `❌ ${j.error || r.status}`])
          } catch (err) {
            setLog((old) => [...old, `❌ 上传失败：${String(err)}`])
          }
        }
        await startPolling()
      }, [setLog, startPolling])

      // 粘贴导入：复制 PDF 文件后 Ctrl+V，或粘贴一个本地路径文本
      const importPath = useCallback(async (p) => {
        if (!p || running) return
        setLog([`▶ 按路径导入：${p}`])
        setShowImport(true)
        try {
          const r = await fetch('/paperdepot/api/import-path', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: p }),
          })
          const j = await r.json()
          if (!j.ok) {
            setLog((old) => [...old, `❌ ${j.error || r.status}`])
          } else {
            await startPolling()
          }
        } catch (e) {
          setLog((old) => [...old, `❌ ${String(e)}`])
        }
      }, [running, setLog, startPolling])

      const onPaste = useCallback((e) => {
        const cd = e.clipboardData
        if (!cd) return
        const files = cd.files
        if (files && files.length) {
          e.preventDefault()
          uploadFiles(files)
          return
        }
        const text = (cd.getData('text') || '').trim()
        if (/\.pdf$/i.test(text)) {
          e.preventDefault()
          importPath(text.replace(/^["']|["']$/g, ''))
        }
      }, [uploadFiles, importPath])

      const onSummarize = useCallback(async (dir) => {
        setLog([`▶ 生成摘要与标签：${dir}`])
        try {
          const r = await fetch('/paperdepot/api/summarize?dir=' + encodeURIComponent(dir), { method: 'POST', credentials: 'same-origin' })
          const j = await r.json()
          if (!j.ok) {
            setLog((old) => [...old, `❌ ${j.error || r.status}`])
            return
          }
          await startPolling()
          openPaper(dir)
        } catch (e) {
          setLog((old) => [...old, `❌ ${String(e)}`])
        }
      }, [startPolling, openPaper, setLog])

      // 批量补摘要：排队把「待生成」的条目跑完；中断后再点会从剩下的继续
      const onSummarizePending = useCallback(async () => {
        setJobInfo(null)
        try {
          const r = await fetch('/paperdepot/api/summarize-pending', { method: 'POST', credentials: 'same-origin' })
          const j = await r.json()
          if (!j.ok) {
            setLog([`❌ ${j.error || r.status}`])
            return
          }
          setLog([`▶ 批量补摘要：排队 ${j.total} 篇（库里待生成 ${j.pending} 篇）`])
          await startPolling()
        } catch (e) {
          setLog([`❌ ${String(e)}`])
        }
      }, [startPolling, setLog])

      const onCancelJob = useCallback(async () => {
        try {
          const r = await fetch('/paperdepot/api/job-cancel', { method: 'POST', credentials: 'same-origin' })
          const j = await r.json()
          if (!j.ok) setLog((old) => [...old, `❌ ${j.error || r.status}`])
        } catch (e) {
          setLog((old) => [...old, `❌ ${String(e)}`])
        }
      }, [setLog])

      const onSetupSaved = useCallback(async () => {
        try {
          const s = await (await api('/setup/status')).json()
          setSetup(s)
          if (s.hasKey) setShowSetup(false)
        } catch {
          /* ignore */
        }
        refreshAll()
      }, [refreshAll])

      const onRebuildNav = useCallback(async () => {
        setLog(['▶ 重建导航块 / 分类页 / 图颜色分组'])
        try {
          const r = await fetch('/paperdepot/api/rebuild-nav', { method: 'POST', credentials: 'same-origin' })
          const j = await r.json()
          if (!j.ok) {
            setLog((old) => [...old, `❌ ${j.error || r.status}`])
            return
          }
          await startPolling()
        } catch (e) {
          setLog((old) => [...old, `❌ ${String(e)}`])
        }
      }, [startPolling, setLog])

      const d = stats
      const vaultName = ((setup && setup.vault) || '').split(/[\\/]/).filter(Boolean).pop() || ''
      const openFromGraph = (dir) => {
        setTab('papers')
        openPaper(dir)
      }
      const openVault = async () => {
        try {
          const j = await openObsidianApi({})
          if (!j.ok) setLog([`❌ 打开 Obsidian 失败：${j.error || '未知原因'}`])
        } catch (e) {
          setLog([`❌ 打开 Obsidian 失败：${String(e)}`])
        }
      }
      const tabs = [
        ['overview', '总览', ''],
        ['papers', '论文', d ? String(d.papers) : ''],
        ['concepts', '概念', d ? String(d.concepts) : ''],
      ]
      const content = setup && !setup.hasKey
        ? h('div', { style: { height: '100%', overflowY: 'auto', padding: '20px 20px 72px', boxSizing: 'border-box' } }, h(SetupCard, { setup, onSaved: onSetupSaved }))
        : d
          ? tab === 'papers'
            ? h(Papers, { papers, loading: papersLoading, onSelect: openPaper, selected, selectedData, onSummarize, running, vaultName })
            : h('div', { style: { height: '100%', overflowY: 'auto', padding: '20px 20px 72px', boxSizing: 'border-box' } },
                tab === 'overview'
                  ? h(Overview, { d, onOpen: openFromGraph })
                  : h(Concepts, { onOpenPaper: openFromGraph, vaultName }))
          : h('div', { style: { padding: 20, color: muted, fontSize: FS.body } }, '正在读取论文库库…')

      return h(
        'div',
        {
          onDragOver: (e) => {
            const types = e.dataTransfer && e.dataTransfer.types
            if (types && Array.from(types).includes('Files')) {
              e.preventDefault()
              e.stopPropagation()
              if (!running) setDragOver(true)
            }
          },
          onDragLeave: (e) => {
            if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false)
          },
          onDrop: (e) => {
            e.preventDefault()
            e.stopPropagation()
            setDragOver(false)
            if (!running) uploadFiles(e.dataTransfer.files)
          },
          onPaste,
          style: {
            height: '100%', display: 'flex', flexDirection: 'column',
            background: T.bg, color: T.text, fontFamily: T.font,
            boxSizing: 'border-box', position: 'relative', overflow: 'hidden',
          },
        },
        dragOver
          ? h(
              'div',
              {
                style: {
                  position: 'absolute', inset: 0, zIndex: 40, pointerEvents: 'none',
                  border: `2px dashed ${ACCENT}`, background: 'rgba(77,107,254,0.10)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 24, fontWeight: 700, color: 'inherit',
                },
              },
              '松手导入 PDF',
            )
          : null,
        // 顶栏
        h('header', {
          style: {
            display: 'flex', alignItems: 'center', gap: SP.md, height: 58, flex: '0 0 auto',
            padding: '0 20px', borderBottom: `1px solid ${line}`,
          },
        },
          h('div', { style: { display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 } },
            h('div', { style: { fontSize: FS.page, fontWeight: 700, lineHeight: 1.15 } }, '论文库'),
            h('div', {
              style: {
                fontFamily: mono, fontSize: 12.5, color: faint,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '44vw',
              },
            }, d ? d.vault : '正在读取库…')),
          h('div', { style: { flex: '1 1 auto' } }),
          h('span', {
            style: {
              display: 'inline-flex', alignItems: 'center', gap: 6, height: 30, padding: '0 11px',
              borderRadius: 999, border: `1px solid ${setup && setup.hasKey ? line : 'rgba(196,123,30,0.45)'}`,
              fontSize: FS.caption, color: muted, whiteSpace: 'nowrap',
            },
          },
            h('span', { style: { width: 6, height: 6, borderRadius: '50%', background: setup && setup.hasKey ? GREEN : ORANGE } }),
            setup ? (setup.hasKey ? 'MinerU 已配置' : '未配置 MinerU') : '配置'),
          h(Btn, { primary: true, onClick: () => setShowImport(true) }, '导入 PDF'),
          h(Btn, { onClick: openVault, title: '在 Obsidian 里打开这个库' }, '打开 Obsidian'),
          h(Btn, { small: true, ghost: true, onClick: () => setShowSetup((s) => !s) }, '设置'),
          h(Btn, { small: true, ghost: true, onClick: refreshAll, disabled: running, title: '刷新' }, running ? '刷新中…' : '⟳')),
        error ? h('div', { style: { padding: '6px 20px', color: ERROR_TEXT, fontSize: FS.body } }, `读取失败：${error}`) : null,
        // 页签
        h('nav', {
          style: {
            display: 'flex', alignItems: 'center', gap: 2, padding: '8px 20px 0',
            flex: '0 0 auto', borderBottom: `1px solid ${line}`,
          },
        },
          tabs.map(([t, label, count]) =>
            h('button', {
              key: t,
              onClick: () => setTab(t),
              style: {
                height: 32, padding: '0 13px', border: 'none', background: 'transparent',
                borderBottom: `2px solid ${tab === t ? ACCENT : 'transparent'}`, marginBottom: -1,
                color: tab === t ? T.text : T.text2, fontSize: FS.body,
                fontWeight: tab === t ? 600 : 500, cursor: 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 6,
              },
            }, label, count && count !== '0' ? h('span', {
              style: { fontSize: 12.5, color: muted, background: T.bg2, padding: '1px 6px', borderRadius: 999, lineHeight: 1.5 },
            }, count) : null)),
          h('div', { style: { flex: '1 1 auto' } }),
          d && d.pendingSummary
            ? h(Btn, {
                small: true,
                ghost: true,
                onClick: onSummarizePending,
                disabled: running,
                title: '把「待生成」的条目排队跑完；可随时停止，下次再点会跳过已完成的',
              }, running
                ? `任务中（${jobInfo && jobInfo.kind === 'summarize-batch' ? `${jobInfo.done || 0}/${jobInfo.total || 0}` : '…'}）`
                : `批量补摘要（${d.pendingSummary}）`)
            : null,
          h(Btn, { small: true, ghost: true, onClick: onRebuildNav, disabled: running, title: '重建论文导航块、分类页与图颜色分组' }, running ? '重建中…' : '重建导航')),
        // 内容
        h('div', { style: { flex: '1 1 auto', minHeight: 0, position: 'relative' } }, content),
        // 底部安全区：flex 末尾的固定占位（等价 HarmonyOS 的 bottom safe area / Blank），
        // 让上方内容整体上移，不贴窗口下沿、不被任务栏压住；不放滚动区里，避免随内容滚走
        h('div', { style: { flex: '0 0 auto', height: 24 } }),
        showSetup && setup && setup.hasKey
          ? h('div', { style: { position: 'absolute', top: 58, right: 20, zIndex: 15, width: 540, maxWidth: '92vw', maxHeight: 'calc(100% - 80px)', overflowY: 'auto' } },
              h(SetupCard, { setup, onSaved: onSetupSaved }))
          : null,
        // 批量补摘要进度条：任务结束时保留，可收起
        jobInfo && jobInfo.kind === 'summarize-batch'
          ? h(BatchBar, { job: jobInfo, onCancel: onCancelJob, onClose: () => setJobInfo(null) })
          : null,
        h(ImportDialog, { open: showImport, onClose: () => setShowImport(false), running, log, uploadFiles }),
      )
    }

    // 左侧栏图标：契约只传 { size }，与官方插件市场 / 自动化任务一致
    function PaperDepotPanelIcon({ size }) {
      const s = typeof size === 'number' && size > 0 ? size : 20
      return h(
        'svg',
        { width: s, height: s, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': 'true', focusable: 'false' },
        h('path', { d: 'M4 4.6h5.2v10.8H4z', stroke: 'currentColor', strokeWidth: 1.5, strokeLinejoin: 'round' }),
        h('path', { d: 'M10.8 4.6H16v10.8h-5.2z', stroke: 'currentColor', strokeWidth: 1.5, strokeLinejoin: 'round' }),
        h('path', { d: 'M6.3 7.3h1.5M6.3 9.7h1.5M12.2 7.3h1.5M12.2 9.7h1.5', stroke: 'currentColor', strokeWidth: 1.2, strokeLinecap: 'round' }),
      )
    }

    // 视图级错误边界：渲染出错时显示错误而不是整块黑屏，方便排查
    class ViewBoundary extends React.Component {
      constructor(props) {
        super(props)
        this.state = { err: null }
      }
      static getDerivedStateFromError(err) {
        return { err }
      }
      componentDidCatch(err, info) {
        console.error('[paperdepot] view crashed:', err, info)
      }
      render() {
        if (this.state.err) {
          return h(
            'div',
            { style: { padding: 20, fontSize: 13, lineHeight: 1.7, color: '#e67e22', whiteSpace: 'pre-wrap' } },
            '论文库视图出错了：\n' + String((this.state.err && this.state.err.stack) || this.state.err),
          )
        }
        return this.props.children
      }
    }

    function PaperDepotPanel(props) {
      return h(ViewBoundary, null, h(PaperDepotView, props))
    }

    function apply(ctx) {
      try {
        // 左侧栏条目（图标 + label），和官方「插件 / 自动化任务」同一排
        ctx.slots.inject('sidebar.panellist', () =>
          ctx.slots.register(
            { name: 'sidebar.panellist', id: 'paperdepot', order: 20, label: () => '论文库' },
            PaperDepotPanelIcon,
          ),
        )
        // 选中左侧栏条目后，中间列渲染的整页内容（key 与左侧栏 id 相同）
        ctx.slots.inject('main', () =>
          ctx.slots.register({ name: 'main', key: 'paperdepot' }, PaperDepotPanel),
        )
      } catch (err) {
        console.error('[paperdepot] client apply failed:', err)
      }
    }

    return { name: 'paperdepot', inject: ['slots'], apply }
  },
})
