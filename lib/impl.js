// paperdepot — host 实现的动态半边
//
// lib/host.js 每次请求按 mtime 重新 import 本文件（带 ?v= 破缓存），
// 所以改这里能立刻生效，不需要重启 DSH。
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __implUrl = new URL(import.meta.url)
__implUrl.search = ''
__implUrl.hash = ''
const HERE = path.dirname(fileURLToPath(__implUrl))
const PACKAGE_ROOT = path.resolve(HERE, '..') // 扁平布局：插件包根 = 仓库根

/** 开发布局：仓库根有 tools/ingest.py；安装布局：只有插件包内的 pipeline/tools。 */
function isRepoLayout(root) {
  return fs.existsSync(path.join(root, 'tools', 'ingest.py'))
}
/** 数据/配置根：开发时就是仓库根；安装后落到用户目录。 */
function defaultHomeRoot() {
  if (process.env.PAPERDEPOT_HOME) return process.env.PAPERDEPOT_HOME
  return isRepoLayout(PACKAGE_ROOT) ? PACKAGE_ROOT : path.join(os.homedir(), '.dsh', 'paperdepot')
}

let PLUGIN_VERSION = ''
try {
  PLUGIN_VERSION = JSON.parse(fs.readFileSync(path.join(PACKAGE_ROOT, 'package.json'), 'utf8')).version || ''
} catch {
  /* ignore */
}
/** 打包到插件包里的流水线（npm publish 前由 scripts/pack-pipeline.mjs 生成）。 */
function bundledPipelineRoot() {
  const p = path.join(PACKAGE_ROOT, 'pipeline')
  return isRepoLayout(p) ? p : null
}

const STATE_KEY = Symbol.for('paperdepot.job')
const DEFAULT_VAULT =
  process.env.PAPERDEPOT_VAULT || path.join(os.homedir(), 'Documents', 'ObsidianVault')

const MAX_BODY = 200 * 1024 * 1024
const STATS_TTL = 8000
let statsCache = { at: 0, vault: '', data: null }

// ---------------- 基础工具 ----------------

function listDirs(dir) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name)
  } catch {
    return []
  }
}

function listFiles(dir, suffix) {
  try {
    return fs.readdirSync(dir, { withFileTypes: true }).filter((d) => d.isFile() && d.name.endsWith(suffix)).map((d) => d.name)
  } catch {
    return []
  }
}

function parseEntry(file) {
  const txt = fs.readFileSync(file, 'utf8')
  const m = /^---\s*\n([\s\S]*?)\n---\s*\n?/.exec(txt)
  const fm = m ? m[1] : ''
  const body = m ? txt.slice(m[0].length) : txt
  const field = (k) => {
    const r = new RegExp('^' + k + ':\\s*(.+?)\\s*$', 'm').exec(fm)
    return r ? r[1].trim().replace(/^"|"$/g, '') : ''
  }
  const tags = []
  const tm = /^tags:\s*\n((?:[ \t]*-[^\n]*\n?)+)/m.exec(fm)
  if (tm) {
    for (const line of tm[1].split(/\r?\n/)) {
      const s = line.trim().replace(/^-\s*/, '').replace(/^"|"$/g, '')
      if (s) tags.push(s)
    }
  }
  const sm = /^## 一句话总结\s*\n+([\s\S]*?)(?=\n## |$)/m.exec(body)
  const summary = sm ? sm[1].trim() : ''
  return {
    title: field('title'),
    year: field('year'),
    journal: field('journal'),
    status: field('status'),
    doi: field('doi'),
    pages: Number(field('pages')) || 0,
    figures: Number(field('figures')) || 0,
    chars: Number(field('chars')) || 0,
    tags,
    summary,
    pending: /待生成|待建立/.test(summary || ''),
  }
}

function computeStats(vault) {
  const papersDir = path.join(vault, '1-Papers')
  const dirs = listDirs(papersDir).filter((d) => !d.startsWith('_'))
  const years = new Map()
  const tags = new Map()
  const journals = new Map()
  const recent = []
  let pages = 0
  let figures = 0
  let pendingSummary = 0
  let pendingMeta = 0
  for (const dir of dirs) {
    const file = path.join(papersDir, dir, 'index.md')
    let e
    let mtime = 0
    try {
      mtime = fs.statSync(file).mtimeMs
      e = parseEntry(file)
    } catch {
      continue
    }
    pages += e.pages
    figures += e.figures
    if (e.pending) pendingSummary += 1
    if (e.status === 'needs_metadata') pendingMeta += 1
    years.set(e.year || '—', (years.get(e.year || '—') || 0) + 1)
    journals.set(e.journal || '—', (journals.get(e.journal || '—') || 0) + 1)
    for (const t of e.tags) {
      if (t.startsWith('状态/')) continue
      tags.set(t, (tags.get(t) || 0) + 1)
    }
    recent.push({ dir, title: e.title || dir, year: e.year, pending: e.pending, mtime })
  }
  recent.sort((a, b) => b.mtime - a.mtime)
  const conceptNames = listFiles(path.join(vault, '2-Concepts'), '.md').filter((f) => !f.startsWith('_')).map((f) => f.replace(/\.md$/, ''))
  return {
    ok: true,
    vault,
    updatedAt: new Date().toISOString(),
    papers: dirs.length,
    concepts: conceptNames.length,
    conceptNames: conceptNames.sort(),
    pages,
    figures,
    pendingSummary,
    pendingMeta,
    duplicates: listDirs(path.join(vault, '_duplicates')).length,
    years: [...years.entries()].map(([year, count]) => ({ year, count })).filter((x) => x.year !== '—').sort((a, b) => a.year.localeCompare(b.year)),
    tags: [...tags.entries()].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count),
    journals: [...journals.entries()].map(([journal, count]) => ({ journal, count })).filter((x) => x.journal !== '—').sort((a, b) => b.count - a.count).slice(0, 10),
    recent: recent.slice(0, 8).map(({ dir, title, year, pending }) => ({ dir, title, year, pending })),
  }
}

// ---------------- 概念层（2-Concepts） ----------------

function parseConceptFile(file, name) {
  const txt = fs.readFileSync(file, 'utf8')
  const fm = /^---\s*\n([\s\S]*?)\n---/.exec(txt)
  const block = fm ? fm[1] : ''
  const field = (k) => {
    const r = new RegExp('^' + k + ':\\s*(.+?)\\s*$', 'm').exec(block)
    return r ? r[1].trim().replace(/^"|"$/g, '') : ''
  }
  const list = (k) => {
    const out = []
    const m = new RegExp('^' + k + ':\\s*\\n((?:[ \\t]*-[^\\n]*\\n?)+)', 'm').exec(block)
    if (m) {
      for (const line of m[1].split(/\r?\n/)) {
        const s = line.trim().replace(/^-\s*/, '').replace(/^"|"$/g, '')
        if (s) out.push(s)
      }
    }
    return out
  }
  let oneLiner = ''
  const q = /^>\s*\*\*一句话\*\*[：:]\s*(.+)$/m.exec(txt)
  if (q) oneLiner = q[1].trim()
  else {
    const q2 = /^>\s*(?!\*\*)(.+)$/m.exec(txt)
    if (q2) oneLiner = q2[1].trim()
  }
  const papers = []
  const re = /\[\[1-Papers\/([^|\]]+?)\/index\b[^\]]*\]\]/g
  let m
  while ((m = re.exec(txt))) {
    const d = m[1].trim()
    if (d && !papers.includes(d)) papers.push(d)
  }
  return { name, title: field('title') || name, aliases: list('aliases'), tags: list('tags'), papers, papersCount: papers.length, oneLiner }
}

function getConcepts(vault) {
  const dir = path.join(vault, '2-Concepts')
  if (!fs.existsSync(dir)) return []
  return listFiles(dir, '.md')
    .filter((f) => !f.startsWith('_'))
    .map((f) => {
      try {
        return parseConceptFile(path.join(dir, f), f.replace(/\.md$/, ''))
      } catch {
        return null
      }
    })
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
}

function paperConcepts(vault) {
  const map = new Map()
  for (const c of getConcepts(vault)) {
    for (const d of c.papers) {
      if (!map.has(d)) map.set(d, [])
      map.get(d).push(c.name)
    }
  }
  return map
}

function getTaxonomy(vault) {
  const dir = path.join(vault, '3-Taxonomy')
  if (!fs.existsSync(dir)) return []
  return listFiles(dir, '.md')
    .filter((f) => !f.startsWith('_'))
    .map((f) => {
      const txt = fs.readFileSync(path.join(dir, f), 'utf8')
      const fm = /^---\s*\n([\s\S]*?)\n---/.exec(txt)
      const block = fm ? fm[1] : ''
      const field = (k) => {
        const r = new RegExp('^' + k + ':\\s*(.+?)\\s*$', 'm').exec(block)
        return r ? r[1].trim().replace(/^"|"$/g, '') : ''
      }
      const papers = []
      const re = /\[\[1-Papers\/([^|\]]+?)\/index\b[^\]]*\]\]/g
      let m
      while ((m = re.exec(txt))) {
        const d = m[1].trim()
        if (d && !papers.includes(d)) papers.push(d)
      }
      return { id: f.replace(/\.md$/, ''), title: field('title') || f, category: field('category'), value: field('value'), papers }
    })
    .sort((a, b) => a.category.localeCompare(b.category, 'zh') || a.title.localeCompare(b.title, 'zh'))
}

function paperTaxonomy(vault) {
  const map = new Map()
  for (const t of getTaxonomy(vault)) {
    for (const d of t.papers) {
      if (!map.has(d)) map.set(d, [])
      map.get(d).push(t.id)
    }
  }
  return map
}

function getGraph(vault) {
  const dir = path.join(vault, '1-Papers')
  const papers = []
  for (const name of listDirs(dir).filter((d) => !d.startsWith('_'))) {
    try {
      const e = parseEntry(path.join(dir, name, 'index.md'))
      const domain = (e.tags.find((t) => t.startsWith('领域/')) || '').replace(/^领域\//, '')
      papers.push({ id: name, title: e.title || name, year: e.year, domain, tags: e.tags })
    } catch {
      /* ignore */
    }
  }
  const concepts = getConcepts(vault).map((c) => ({ id: c.name, title: c.title, papers: c.papers, tags: c.tags }))
  const known = new Set(papers.map((p) => p.id))
  const edges = []
  for (const c of concepts) {
    for (const p of c.papers) {
      if (known.has(p)) edges.push({ paper: p, concept: c.id })
    }
  }
  const taxonomy = getTaxonomy(vault)
  const taxEdges = []
  for (const t of taxonomy) {
    for (const p of t.papers) {
      if (known.has(p)) taxEdges.push({ paper: p, taxonomy: t.id })
    }
  }
  return { ok: true, papers, concepts, edges, taxonomy, taxEdges, updatedAt: new Date().toISOString() }
}

function getStats(vault) {
  const now = Date.now()
  if (statsCache.data && statsCache.vault === vault && now - statsCache.at < STATS_TTL) return statsCache.data
  const data = computeStats(vault)
  statsCache = { at: now, vault, data }
  return data
}

function sendJson(res, code, obj) {
  const body = JSON.stringify(obj)
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' })
  res.end(body)
}

// ---------------- 任务（单并发） ----------------

function jobState() {
  if (!globalThis[STATE_KEY]) {
    globalThis[STATE_KEY] = { job: null }
  }
  return globalThis[STATE_KEY]
}

function trimLog(job) {
  if (job.lines.length > 400) job.lines.splice(0, job.lines.length - 400)
}

function runCommand(job, cmd, args, cwd) {
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(cmd, args, { cwd, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } })
    } catch (err) {
      job.lines.push(`❌ 无法启动：${err.message}`)
      return resolve(-1)
    }
    const onData = (buf) => {
      for (const line of String(buf).split(/\r?\n/)) {
        if (line.trim()) {
          job.lines.push(line.replace(/\x1b\[[0-9;]*m/g, ''))
          trimLog(job)
        }
      }
    }
    child.stdout.on('data', onData)
    child.stderr.on('data', onData)
    child.on('error', (err) => {
      job.lines.push(`❌ ${err.message}`)
      resolve(-1)
    })
    child.on('close', (code) => resolve(code ?? -1))
  })
}

// ---------------- 首次配置 / 自检（onboarding） ----------------

function secretsPathOf(cfg) {
  return cfg.secretsPath || path.join(cfg.configDir || path.join(cfg.homeRoot, 'config'), 'secrets.local.json')
}
function statePathOf(cfg) {
  return cfg.statePath || path.join(cfg.configDir || path.join(cfg.homeRoot, 'config'), 'paperdepot.local.json')
}

function readJson(p) {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'))
  } catch {
    return {}
  }
}

function currentKey(cfg) {
  const env = (process.env.MINERU_API_KEY || '').trim()
  if (env) return { key: env, source: 'env' }
  const k = String(readJson(secretsPathOf(cfg)).mineru_api_key || '').trim()
  return { key: k, source: k ? 'file' : 'none' }
}

async function probeMineru(key) {
  try {
    const r = await fetch('https://mineru.net/api/v4/extract-results/batch/00000000-0000-0000-0000-000000000000', {
      headers: { Authorization: 'Bearer ' + key, Accept: '*/*' },
      signal: AbortSignal.timeout(15000),
    })
    if (r.status === 401 || r.status === 403) return { ok: false, message: `key 无效或已过期（HTTP ${r.status}）` }
    if (!r.ok) return { ok: false, message: `MinerU 返回 HTTP ${r.status}` }
    return { ok: true, message: 'key 可用（MinerU 已响应）' }
  } catch (err) {
    return { ok: false, message: '连接 MinerU 失败：' + String((err && err.message) || err) }
  }
}

let pyCache = { at: 0, exe: '', res: null }
function pythonInfo(cfg) {
  const now = Date.now()
  if (pyCache.res && pyCache.exe === cfg.python && now - pyCache.at < 60_000) return pyCache.res
  let res
  try {
    const r = spawnSync(cfg.python, ['--version'], { encoding: 'utf8', timeout: 10000 })
    res = { ok: r.status === 0, version: String(r.stdout || r.stderr || '').trim() }
  } catch (err) {
    res = { ok: false, version: '', error: String((err && err.message) || err) }
  }
  pyCache = { at: now, exe: cfg.python, res }
  return res
}

function setupStatus(cfg) {
  const { key, source } = currentKey(cfg)
  const vaultExists = fs.existsSync(cfg.vault)
  let counts = null
  try {
    const s = getStats(cfg.vault)
    counts = { papers: s.papers, concepts: s.concepts, pendingSummary: s.pendingSummary }
  } catch {
    /* ignore */
  }
  return {
    ok: true,
    hasKey: !!key,
    keySource: source,
    keyTail: key ? key.slice(-4) : '',
    secretsPath: secretsPathOf(cfg),
    vault: cfg.vault,
    vaultExists,
    vaultReady: fs.existsSync(path.join(cfg.vault, '1-Papers')),
    homeRoot: cfg.homeRoot,
    dataRoot: cfg.dataRoot,
    inboxDir: cfg.inboxDir,
    digestDir: cfg.digestDir,
    mineruCache: cfg.mineruCache,
    toolsDir: cfg.toolsDir,
    pipelineRoot: cfg.pipelineRoot,
    pipelineOk: fs.existsSync(path.join(cfg.toolsDir, 'ingest.py')),
    specOk: fs.existsSync(path.join(cfg.pipelineConfigDir, 'SUMMARY_SPEC.md')),
    repoLayout: isRepoLayout(PACKAGE_ROOT),
    pluginVersion: PLUGIN_VERSION,
    platform: process.platform,
    defaultVault: DEFAULT_VAULT,
    python: { ...pythonInfo(cfg), exe: cfg.python },
    counts,
    mineruSite: 'https://mineru.net',
  }
}

// ---------------- LLM 摘要（P2） ----------------

function getLlm(host) {
  const ctx = host && host.ctx
  if (!ctx) return null
  try {
    if (typeof ctx.get === 'function') {
      const svc = ctx.get('llm')
      if (svc) return svc
    }
    return ctx.llm || null
  } catch {
    return null
  }
}

async function callLlm(host, cfg, prompt) {
  const llm = getLlm(host)
  if (!llm || typeof llm.stream !== 'function') throw new Error('LLM 服务不可用（host 未拿到 ctx.llm）')
  let lastErr = null
  for (let attempt = 0; attempt < 3; attempt++) {
    let out = ''
    let finishError = null
    try {
      const stream = llm.stream({
        provider: cfg.provider,
        model: cfg.model,
        // opencode-go 之类的中转要求带会话标识（x-opencode-session），否则 400 MissingSessionID
        sessionId: cfg.sessionId || 'paperdepot-' + Date.now().toString(36) + '-' + attempt,
        messages: [{ role: 'user', content: [{ type: 'text', text: prompt }] }],
      })
      for await (const chunk of stream) {
        if (!chunk) continue
        if (chunk.type === 'text-delta') out += chunk.text || ''
        else if (chunk.type === 'finish') finishError = chunk.error || chunk.result || chunk
      }
      if (out.trim()) return out
      lastErr = new Error('LLM 无输出' + (finishError ? `：${JSON.stringify(finishError).slice(0, 300)}` : ''))
    } catch (err) {
      lastErr = err
    }
    if (attempt < 2) await new Promise((r) => setTimeout(r, 3000 * (attempt + 1)))
  }
  throw lastErr || new Error('LLM 调用失败')
}

function parseModelOutput(text) {
  let body = String(text || '').trim()
  const fence = /^```(?:json)?\s*([\s\S]*?)```$/.exec(body)
  if (fence) body = fence[1].trim()
  const normalize = (obj) => ({
    summary_md: obj.summary_md || '',
    tags_md: obj.tags_md || '',
    aliases: Array.isArray(obj.aliases)
      ? obj.aliases.filter((x) => typeof x === 'string' && x.trim()).map((x) => x.trim()).slice(0, 8)
      : [],
    keywords: Array.isArray(obj.keywords)
      ? obj.keywords.filter((x) => typeof x === 'string' && x.trim()).map((x) => x.trim()).slice(0, 12)
      : [],
    citekey: typeof obj.citekey === 'string' ? obj.citekey.trim() : '',
  })
  const tryJson = (s) => {
    try {
      const obj = JSON.parse(s)
      if (obj && (obj.summary_md || obj.tags_md)) return normalize(obj)
    } catch {
      /* ignore */
    }
    return null
  }
  let got = tryJson(body)
  if (!got) {
    const a = body.indexOf('{')
    const b = body.lastIndexOf('}')
    if (a >= 0 && b > a) got = tryJson(body.slice(a, b + 1))
  }
  if (got && got.summary_md) return got
  // 模型没按 JSON 输出：按「- 标签」标题切分
  const m = /\n#\s+[^\n]*?标签[^\n]*\n/.exec(body)
  if (m && body.includes('一句话总结')) {
    return { summary_md: body.slice(0, m.index).trim(), tags_md: body.slice(m.index).trim(), aliases: [], keywords: [], citekey: '' }
  }
  throw new Error('无法解析模型输出（预期 JSON{summary_md,tags_md,aliases,keywords,citekey}）')
}

function canonicalTags(cfg) {
  const out = {}
  for (const cat of ['领域', '方法', '应用', '仪器']) {
    try {
      const obj = JSON.parse(fs.readFileSync(path.join(cfg.pipelineConfigDir, `tagmap_${cat}.json`), 'utf8'))
      out[cat] = [...new Set(Object.values(obj.mapping || {}))].sort()
    } catch {
      out[cat] = []
    }
  }
  return out
}

async function summarizeOne(job, cfg, host, dir) {
  if (!fs.existsSync(path.join(cfg.vault, '1-Papers', dir, 'index.md'))) {
    throw new Error('条目目录不存在或缺少 index.md：' + dir)
  }
  // digest 落在 cache/digests/<条目>.digest.md，跑完保留，方便查看“模型到底读了什么”
  fs.mkdirSync(cfg.digestDir, { recursive: true })
  const startedAt = Date.now()
  const code = await runCommand(
    job,
    cfg.python,
    [path.join(cfg.toolsDir, 'make_digest.py'), '--vault', cfg.vault, '--only', dir, '--out', cfg.digestDir],
    cfg.workspaceRoot,
  )
  if (code !== 0) throw new Error('make_digest 失败')
  const files = fs
    .readdirSync(cfg.digestDir)
    .map((f) => ({ f, m: fs.statSync(path.join(cfg.digestDir, f)).mtimeMs }))
    .filter((x) => x.f.endsWith('.digest.md'))
  let candidates = files.filter((x) => x.m >= startedAt - 3000).sort((a, b) => b.m - a.m)
  if (!candidates.length) {
    // 某些文件系统 mtime 粒度/时钟问题会导致过滤为空，退回到「最新的一份 digest」
    candidates = files.sort((a, b) => b.m - a.m)
  }
  if (!candidates.length) throw new Error('没有生成 digest（目录里现有 ' + fs.readdirSync(cfg.digestDir).length + ' 个文件）')
  const digestPath = path.join(cfg.digestDir, candidates[0].f)
  job.lines.push(`  📄 digest: ${digestPath}`)
  const digest = fs.readFileSync(digestPath, 'utf8')
  // Skill 优先：config/SKILL.md（给插件的 LLM 自己用），旧仓库回退到 SUMMARY_SPEC.md
  const skillPath = path.join(cfg.pipelineConfigDir, 'SKILL.md')
  const specPath = fs.existsSync(skillPath) ? skillPath : path.join(cfg.pipelineConfigDir, 'SUMMARY_SPEC.md')
  const spec = fs.readFileSync(specPath, 'utf8')
  const canon = canonicalTags(cfg)
  const vocab = ['领域', '方法', '应用', '仪器']
    .filter((c) => (canon[c] || []).length)
    .map((c) => `- ${c}：${canon[c].join('、')}`)
    .join('\n')
  const prompt = [
    spec,
    '',
    '---',
    '',
    '## 本次任务',
    '',
    `论文条目目录：${dir}`,
    '只输出一个 JSON 对象（不要代码围栏）：{"summary_md": "...", "tags_md": "...", "aliases": [...], "keywords": [...], "citekey": "..."}。',
    'summary_md：以 "# 📖 论文摘要" 开头的 Markdown，包含规范里的全部小节。',
    'tags_md：以 "# <论文标题> - 标签" 开头，含「研究领域 / 技术方法 / 应用场景 / 仪器设备」四个小节。',
    'aliases：2–6 个中英文别名（概念/项目/仪器/方法名，用于检索），没有就给空数组。',
    'keywords：5–10 个检索关键词（中文术语优先，可含英文），没有就给空数组。',
    'citekey：小写、无空格的引用键，格式「第一作者姓+年份+关键词」，例如 sun2023rapidfrd；没有作者信息就给空字符串。',
    'tags_md 里的每个标签**必须逐字取自下面的受控词表**（每类至少 2 个，不许自造新词）。',
    '所有数字必须能在下面的材料里找到；找不到就写定性结论，绝不编造。',
    '',
    '## 受控标签词表',
    vocab,
    '',
    '## 材料',
    '',
    digest,
  ].join('\n')
  job.lines.push(`  ⏳ ${cfg.provider}/${cfg.model} 生成中（材料 ${Math.round(digest.length / 1000)}k 字符）…`)
  const text = await callLlm(host, cfg, prompt)
  const { summary_md, tags_md, aliases = [], keywords = [], citekey = '' } = parseModelOutput(text)
  const entryDir = path.join(cfg.vault, '1-Papers', dir)
  const inlineList = (arr) => '[' + arr.map((s) => JSON.stringify(s)).join(', ') + ']'
  const summaryWithMeta = [
    '---',
    `aliases: ${inlineList(aliases)}`,
    `keywords: ${inlineList(keywords)}`,
    `citekey: ${JSON.stringify(citekey)}`,
    '---',
    '',
    summary_md,
  ].join('\n')
  fs.writeFileSync(path.join(entryDir, 'summary.md'), summaryWithMeta)
  fs.writeFileSync(path.join(entryDir, 'tags.md'), tags_md)
  job.lines.push('  ⏳ 合并进 index.md…')
  const code2 = await runCommand(
    job,
    cfg.python,
    [path.join(cfg.toolsDir, 'apply_summary.py'), '--vault', cfg.vault, '--entry', dir],
    cfg.workspaceRoot,
  )
  if (code2 !== 0) throw new Error('apply_summary 失败')
  job.lines.push('  ✅ 摘要 / 标签已写入 index.md')
  // 标签再走一次受控词表归一（幂等；把模型偶尔写出的别名映射回规范词）
  const code3 = await runCommand(
    job,
    cfg.python,
    [path.join(cfg.toolsDir, 'apply_tagmap.py'), '--vault', cfg.vault],
    cfg.workspaceRoot,
  )
  if (code3 !== 0) job.lines.push('  ⚠ apply_tagmap 未成功（不影响条目可用）')
  // 按 SKILL 契约校验（缺小节/标签不合规会报错；数字追溯只告警）
  const code4 = await runCommand(
    job,
    cfg.python,
    [path.join(cfg.toolsDir, 'validate_summary.py'), '--vault', cfg.vault, '--entry', dir],
    cfg.workspaceRoot,
  )
  if (code4 !== 0) job.lines.push('  ⚠ 摘要校验有不符合项（见上，条目仍可用；可手动重跑）')
  await runMakeNav(job, cfg)
}

function lastSlug(job) {
  for (let i = job.lines.length - 1; i >= 0; i--) {
    const m = /^✅\s+(.+)$/.exec(String(job.lines[i]).trim())
    if (m) return m[1].trim()
  }
  return ''
}

// 用系统默认处理器打开 URI（Obsidian 的 obsidian:// 只能在宿主进程侧拉起：
// 桌面版把 window.open / window.location 的自定义协议全部 deny 了）
function launchUri(uri) {
  return new Promise((resolve) => {
    let cmd
    let args
    if (process.platform === 'win32') {
      cmd = 'rundll32'
      args = ['url.dll,FileProtocolHandler', uri]
    } else if (process.platform === 'darwin') {
      cmd = 'open'
      args = [uri]
    } else {
      cmd = 'xdg-open'
      args = [uri]
    }
    let settled = false
    const done = (r) => {
      if (!settled) {
        settled = true
        resolve(r)
      }
    }
    try {
      const child = spawn(cmd, args, { windowsHide: true, windowsVerbatimArguments: false, detached: true, stdio: 'ignore' })
      child.on('error', (err) => done({ ok: false, error: String((err && err.message) || err) }))
      child.on('spawn', () => {
        // 拉起成功不等待退出（Obsidian 可能已在运行，只是聚焦窗口）
        child.unref()
        setTimeout(() => done({ ok: true }), 400)
      })
    } catch (err) {
      done({ ok: false, error: String((err && err.message) || err) })
    }
  })
}

async function runMakeNav(job, cfg) {
  const script = path.join(cfg.toolsDir, 'make_nav.py')
  if (!fs.existsSync(script)) return
  job.lines.push('  ⏳ 更新导航块 / 分类页…')
  const code = await runCommand(job, cfg.python, [script, '--vault', cfg.vault], cfg.workspaceRoot)
  if (code !== 0) job.lines.push('  ⚠ make_nav 未成功（导航/分类页可能未更新）')
}

async function runImport(pdfPath, cfg, host) {
  const st = jobState()
  const job = {
    id: Date.now().toString(36),
    kind: 'import',
    file: path.basename(pdfPath),
    state: 'running',
    lines: [`▶ 导入 ${path.basename(pdfPath)}`, `  库: ${cfg.vault}`],
    startedAt: new Date().toISOString(),
  }
  st.job = job
  const papersDir = path.join(cfg.vault, '1-Papers')
  const beforeDirs = new Set(listDirs(papersDir))
  const ingest = path.join(cfg.toolsDir, 'ingest.py')
  const code = await runCommand(job, cfg.python, [ingest, pdfPath, '--vault', cfg.vault, '--cache', cfg.mineruCache], cfg.workspaceRoot)
  job.exitCode = code
  if (code === 0 || code === 2) {
    // 用目录差集找新条目，比从日志里解析 slug 稳（日志格式/编码都可能变）
    const created = listDirs(papersDir).filter((d) => !beforeDirs.has(d))
    const slug = created.length ? created[created.length - 1] : lastSlug(job)
    if (slug) job.lines.push(`  新条目: ${slug}`)
    if (slug && cfg.autoSummarize && !cfg.dryRun) {
      try {
        job.lines.push('', '— 生成摘要与标签（LLM）—')
        await summarizeOne(job, cfg, host, slug)
      } catch (err) {
        job.lines.push(`⚠ 摘要失败：${err.message}（条目已入库，可在「论文」页手动重试）`)
      }
    } else if (slug) {
      job.lines.push('（autoSummarize=false，跳过摘要）')
    }
    job.lines.push('— 重建索引 —')
    const mk = path.join(cfg.toolsDir, 'make_index.py')
    const code2 = await runCommand(job, cfg.python, [mk, '--vault', cfg.vault], cfg.workspaceRoot)
    if (code2 !== 0) job.lines.push(`⚠ make_index 退出码 ${code2}`)
    // 新条目也要有导航块（概念/分类）；make_nav 幂等，已处理过的条目只会被确认
    await runMakeNav(job, cfg)
    job.state = 'done'
  } else if (code === -1) {
    job.state = 'error'
  } else {
    job.state = 'done'
    job.lines.push(`⚠ ingest 退出码 ${code}（部分失败请检查日志）`)
  }
  job.finishedAt = new Date().toISOString()
  statsCache = { at: 0, vault: '', data: null }
}

async function runReindex(cfg) {
  const st = jobState()
  const job = { id: Date.now().toString(36), kind: 'reindex', state: 'running', lines: ['▶ 重建索引'], startedAt: new Date().toISOString() }
  st.job = job
  const mk = path.join(cfg.toolsDir, 'make_index.py')
  const code = await runCommand(job, cfg.python, [mk, '--vault', cfg.vault], cfg.workspaceRoot)
  job.exitCode = code
  job.state = code === 0 ? 'done' : 'error'
  job.finishedAt = new Date().toISOString()
  statsCache = { at: 0, vault: '', data: null }
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    req.on('data', (c) => {
      size += c.length
      if (size > limit) {
        reject(new Error('文件过大'))
        req.destroy()
        return
      }
      chunks.push(c)
    })
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

function safeName(name) {
  const base = path.basename(String(name || 'upload.pdf')).replace(/[\\/:*?"<>|]/g, '_')
  return base.toLowerCase().endsWith('.pdf') ? base : base + '.pdf'
}

// ---------------- 工厂 ----------------

export function createHandler(cfg, host) {
  const homeRoot = cfg.homeRoot || defaultHomeRoot()
  const statePath = cfg.statePath || path.join(homeRoot, 'config', 'paperdepot.local.json')
  // 首次配置时写下的偏好优先（库路径 / 数据目录 / 流水线目录，都可以在面板里改）
  const localState = readJson(statePath)
  const configDir = cfg.configDir || localState.configDir || path.join(homeRoot, 'config')
  const dataRoot = cfg.dataRoot || localState.dataRoot || path.join(homeRoot, 'cache')
  const pipelineRoot =
    cfg.pipelineRoot ||
    localState.pipelineRoot ||
    (isRepoLayout(PACKAGE_ROOT) ? PACKAGE_ROOT : bundledPipelineRoot()) ||
    path.join(homeRoot, 'pipeline')
  const config = {
    homeRoot,
    configDir,
    dataRoot,
    pipelineRoot,
    pipelineConfigDir: path.join(pipelineRoot, 'config'),
    toolsDir: cfg.toolsDir || localState.toolsDir || path.join(pipelineRoot, 'tools'),
    workspaceRoot: homeRoot,
    vault: localState.vault || cfg.vault || DEFAULT_VAULT,
    python: cfg.python || 'python',
    inboxDir: cfg.inboxDir || path.join(dataRoot, 'inbox'),
    digestDir: cfg.digestDir || path.join(dataRoot, 'digests'),
    mineruCache: cfg.mineruCache || path.join(dataRoot, 'mineru'),
    secretsPath: cfg.secretsPath || path.join(configDir, 'secrets.local.json'),
    statePath,
    // 规则：禁止 deepseek-account；其它 provider 允许，默认 opencode-go
    provider: String(cfg.provider || '').includes('deepseek-account') ? 'opencode-go' : (cfg.provider || 'opencode-go'),
    model: String(cfg.provider || '').includes('deepseek-account') ? 'deepseek-v4.1-flash' : (cfg.model || 'deepseek-v4.1-flash'),
    autoSummarize: cfg.autoSummarize !== false,
    dryRun: !!cfg.dryRun,
  }

  return async function handle(req, res) {
    const url = new URL(req.url || '/', 'http://localhost')
    const p = url.pathname
    try {
      if (p === '/paperdepot/api/health') {
        return sendJson(res, 200, {
          ok: true,
          service: 'paperdepot',
          version: 3,
          pluginVersion: PLUGIN_VERSION,
          vault: config.vault,
          toolsDir: config.toolsDir,
          hasKey: !!currentKey(config).key,
        })
      }
      if (p === '/paperdepot/api/setup/status') {
        return sendJson(res, 200, setupStatus(config))
      }
      if (p === '/paperdepot/api/setup/key' && req.method === 'POST') {
        const raw = await readBody(req, 64 * 1024)
        let payload = {}
        try {
          payload = JSON.parse(raw.toString('utf8'))
        } catch {
          payload = { key: raw.toString('utf8').trim() }
        }
        const key = String(payload.key || '').trim()
        if (!/^sk-[A-Za-z0-9]{8,}$/.test(key)) {
          return sendJson(res, 400, { ok: false, error: 'key 格式不对：应以 sk- 开头，只含字母数字' })
        }
        const probe = await probeMineru(key)
        if (!probe.ok) return sendJson(res, 400, { ok: false, error: probe.message, probe })
        const cur = readJson(secretsPathOf(config))
        cur.mineru_api_key = key
        fs.mkdirSync(path.dirname(secretsPathOf(config)), { recursive: true })
        fs.writeFileSync(secretsPathOf(config), JSON.stringify(cur, null, 2) + '\n', 'utf8')
        return sendJson(res, 200, { ok: true, saved: true, probe, secretsPath: secretsPathOf(config) })
      }
      if (p === '/paperdepot/api/setup/vault' && req.method === 'POST') {
        const raw = await readBody(req, 64 * 1024)
        let payload = {}
        try {
          payload = JSON.parse(raw.toString('utf8'))
        } catch {
          payload = { vault: raw.toString('utf8').trim() }
        }
        const v = String(payload.vault || '').trim().replace(/[\\/]+$/, '')
        if (!v) return sendJson(res, 400, { ok: false, error: '路径为空' })
        if (!fs.existsSync(v)) return sendJson(res, 400, { ok: false, error: `目录不存在：${v}` })
        const cur = readJson(statePathOf(config))
        cur.vault = v
        fs.writeFileSync(statePathOf(config), JSON.stringify(cur, null, 2) + '\n', 'utf8')
        config.vault = v
        statsCache = { at: 0, vault: '', data: null }
        return sendJson(res, 200, { ok: true, saved: true, vault: v })
      }
      if (p === '/paperdepot/api/setup/paths' && req.method === 'POST') {
        const raw = await readBody(req, 64 * 1024)
        let payload = {}
        try {
          payload = JSON.parse(raw.toString('utf8'))
        } catch {
          return sendJson(res, 400, { ok: false, error: '请求体需要 JSON' })
        }
        const cur = readJson(statePathOf(config))
        let changed = 0
        if (payload.dataRoot) {
          const d = String(payload.dataRoot).trim().replace(/[\\/]+$/, '')
          if (!d) return sendJson(res, 400, { ok: false, error: '数据目录为空' })
          try {
            fs.mkdirSync(d, { recursive: true })
          } catch (err) {
            return sendJson(res, 400, { ok: false, error: '创建目录失败：' + String((err && err.message) || err) })
          }
          cur.dataRoot = d
          config.dataRoot = d
          config.inboxDir = path.join(d, 'inbox')
          config.digestDir = path.join(d, 'digests')
          config.mineruCache = path.join(d, 'mineru')
          changed += 1
        }
        if (payload.toolsDir) {
          const t = String(payload.toolsDir).trim().replace(/[\\/]+$/, '')
          if (!fs.existsSync(path.join(t, 'ingest.py'))) {
            return sendJson(res, 400, { ok: false, error: '这个目录里没有 ingest.py，不是论文库流水线：' + t })
          }
          cur.toolsDir = t
          config.toolsDir = t
          config.pipelineRoot = path.dirname(t)
          config.pipelineConfigDir = path.join(path.dirname(t), 'config')
          changed += 1
        }
        if (!changed) return sendJson(res, 400, { ok: false, error: '没有需要保存的字段' })
        fs.writeFileSync(statePathOf(config), JSON.stringify(cur, null, 2) + '\n', 'utf8')
        return sendJson(res, 200, { ok: true, saved: true, dataRoot: config.dataRoot, toolsDir: config.toolsDir })
      }
      if (p === '/paperdepot/api/stats') {
        return sendJson(res, 200, getStats(config.vault))
      }
      if (p === '/paperdepot/api/job') {
        const job = jobState().job
        return sendJson(res, 200, { ok: true, job })
      }
      if (p === '/paperdepot/api/open-obsidian' && req.method === 'POST') {
        const raw = await readBody(req, 64 * 1024)
        let payload = {}
        try {
          payload = JSON.parse(raw.toString('utf8'))
        } catch {
          return sendJson(res, 400, { ok: false, error: '请求体需要 JSON' })
        }
        const vault = config.vault
        const vaultName = path.basename(vault)
        let rel = ''
        if (payload.dir) {
          rel = `1-Papers/${payload.dir}/index.md`
          if (!fs.existsSync(path.join(vault, rel))) return sendJson(res, 404, { ok: false, error: '条目不存在：' + payload.dir })
        } else if (payload.concept) {
          rel = `2-Concepts/${payload.concept}.md`
          if (!fs.existsSync(path.join(vault, rel))) return sendJson(res, 404, { ok: false, error: '概念页不存在：' + payload.concept })
        } else if (payload.taxonomy) {
          rel = `3-Taxonomy/${payload.taxonomy}.md`
          if (!fs.existsSync(path.join(vault, rel))) return sendJson(res, 404, { ok: false, error: '分类页不存在：' + payload.taxonomy })
        }
        const uri = 'obsidian://open?vault=' + encodeURIComponent(vaultName) + (rel ? '&file=' + encodeURIComponent(rel) : '')
        const launched = await launchUri(uri)
        return sendJson(res, launched.ok ? 200 : 500, { ok: launched.ok, uri, error: launched.ok ? undefined : launched.error })
      }
      if (p === '/paperdepot/api/concepts') {
        return sendJson(res, 200, { ok: true, total: getConcepts(config.vault).length, items: getConcepts(config.vault) })
      }
      if (p === '/paperdepot/api/concept') {
        const name = url.searchParams.get('name') || ''
        const file = path.join(config.vault, '2-Concepts', name + '.md')
        if (!name || !fs.existsSync(file)) return sendJson(res, 404, { ok: false, error: '找不到概念页' })
        const c = parseConceptFile(file, name)
        const papers = c.papers
          .map((d) => {
            try {
              const e = parseEntry(path.join(config.vault, '1-Papers', d, 'index.md'))
              return { dir: d, title: e.title || d, year: e.year, journal: e.journal }
            } catch {
              return null
            }
          })
          .filter(Boolean)
        return sendJson(res, 200, { ok: true, markdown: fs.readFileSync(file, 'utf8'), ...c, papers })
      }
      if (p === '/paperdepot/api/graph') {
        return sendJson(res, 200, getGraph(config.vault))
      }
      if (p === '/paperdepot/api/papers') {
        const q = (url.searchParams.get('q') || '').toLowerCase()
        const tag = url.searchParams.get('tag') || ''
        const limit = Math.min(Number(url.searchParams.get('limit')) || 500, 1000)
        const dir = path.join(config.vault, '1-Papers')
        const items = []
        for (const name of listDirs(dir).filter((d) => !d.startsWith('_'))) {
          try {
            const e = parseEntry(path.join(dir, name, 'index.md'))
            if (q && !(`${e.title} ${e.year} ${e.journal}`.toLowerCase().includes(q))) continue
            if (tag && !e.tags.includes(tag)) continue
            items.push({ dir: name, title: e.title || name, year: e.year, journal: e.journal, pages: e.pages, tags: e.tags, summary: e.summary, pending: e.pending })
          } catch {
            /* ignore */
          }
          if (items.length >= limit) break
        }
        items.sort((a, b) => (b.year || '').localeCompare(a.year || '') || a.title.localeCompare(b.title, 'zh'))
        return sendJson(res, 200, { ok: true, total: items.length, items })
      }
      if (p === '/paperdepot/api/paper') {
        const name = url.searchParams.get('dir') || ''
        const dir = path.join(config.vault, '1-Papers', name)
        const file = path.join(dir, 'index.md')
        if (!name || !fs.existsSync(file)) return sendJson(res, 404, { ok: false, error: '找不到条目' })
        const index = fs.readFileSync(file, 'utf8')
        const hasFull = fs.existsSync(path.join(dir, 'full.md'))
        const pdf = path.join(dir, 'paper.pdf')
        let pending = false
        try {
          pending = parseEntry(file).pending
        } catch {
          /* ignore */
        }
        return sendJson(res, 200, {
          ok: true,
          dir: name,
          index,
          pending,
          concepts: paperConcepts(config.vault).get(name) || [],
          taxonomy: paperTaxonomy(config.vault).get(name) || [],
          hasFull,
          pdfBytes: fs.existsSync(pdf) ? fs.statSync(pdf).size : 0,
        })
      }
      if (p === '/paperdepot/api/rebuild-nav' && req.method === 'POST') {
        if (jobState().job && jobState().job.state === 'running') return sendJson(res, 409, { ok: false, error: '已有任务在跑' })
        const job = {
          id: Date.now().toString(36),
          kind: 'nav',
          state: 'running',
          lines: ['▶ 重建导航块 / 分类页'],
          startedAt: new Date().toISOString(),
        }
        jobState().job = job
        ;(async () => {
          try {
            await runMakeNav(job, config)
            const gscript = path.join(config.toolsDir, 'make_obsidian_graph.py')
            if (fs.existsSync(gscript)) {
              job.lines.push('  ⏳ 刷新图颜色分组…')
              const c = await runCommand(job, config.python, [gscript, '--vault', config.vault], config.workspaceRoot)
              if (c !== 0) job.lines.push('  ⚠ 图颜色分组未更新（不影响导航）')
            }
            job.state = 'done'
          } catch (err) {
            job.lines.push(`❌ ${err.message}`)
            job.state = 'error'
          }
          job.finishedAt = new Date().toISOString()
          statsCache = { at: 0, vault: '', data: null }
        })()
        return sendJson(res, 202, { ok: true, accepted: true })
      }
      if (p === '/paperdepot/api/reindex' && req.method === 'POST') {
        if (jobState().job && jobState().job.state === 'running') return sendJson(res, 409, { ok: false, error: '已有任务在跑' })
        runReindex(config).catch((e) => console.error('[paperdepot] reindex failed', e))
        return sendJson(res, 202, { ok: true, accepted: true })
      }
      if (p === '/paperdepot/api/import-path' && req.method === 'POST') {
        if (jobState().job && jobState().job.state === 'running') return sendJson(res, 409, { ok: false, error: '已有任务在跑，等它结束' })
        const raw = await readBody(req, 64 * 1024)
        let payload = {}
        try {
          payload = JSON.parse(raw.toString('utf8'))
        } catch {
          return sendJson(res, 400, { ok: false, error: '请求体需要 JSON：{ "path": "D:\\\\...\\\\paper.pdf" }' })
        }
        const src = String(payload.path || '').trim().replace(/^["']|["']$/g, '')
        if (!src) return sendJson(res, 400, { ok: false, error: '路径为空' })
        if (!/\.pdf$/i.test(src)) return sendJson(res, 400, { ok: false, error: '只支持 .pdf 文件' })
        let st
        try {
          st = fs.statSync(src)
        } catch {
          return sendJson(res, 404, { ok: false, error: '文件不存在或没有权限：' + src })
        }
        if (!st.isFile() || st.size === 0) return sendJson(res, 400, { ok: false, error: '不是有效文件：' + src })
        const head = Buffer.alloc(4)
        let fd = null
        try {
          fd = fs.openSync(src, 'r')
          fs.readSync(fd, head, 0, 4, 0)
        } catch {
          return sendJson(res, 400, { ok: false, error: '读不了这个文件：' + src })
        } finally {
          if (fd !== null) {
            try {
              fs.closeSync(fd)
            } catch {
              /* ignore */
            }
          }
        }
        if (!(head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46)) {
          return sendJson(res, 400, { ok: false, error: '不是 PDF（头部不是 %PDF）' })
        }
        fs.mkdirSync(config.inboxDir, { recursive: true })
        const name = safeName(path.basename(src))
        const dst = path.join(config.inboxDir, `${Date.now()}-${name}`)
        try {
          fs.copyFileSync(src, dst)
        } catch (err) {
          return sendJson(res, 400, { ok: false, error: '复制失败：' + String((err && err.message) || err) })
        }
        if (config.dryRun) {
          jobState().job = { id: 'dry', kind: 'import', file: name, state: 'done', lines: [`（dry-run）已接收 ${name}，${st.size} 字节`], startedAt: new Date().toISOString(), finishedAt: new Date().toISOString() }
          return sendJson(res, 202, { ok: true, file: name, bytes: st.size, dryRun: true })
        }
        runImport(dst, config, host).catch((e) => console.error('[paperdepot] import failed', e))
        return sendJson(res, 202, { ok: true, accepted: true, file: name, bytes: st.size })
      }
      if (p === '/paperdepot/api/import' && req.method === 'POST') {
        if (jobState().job && jobState().job.state === 'running') return sendJson(res, 409, { ok: false, error: '已有任务在跑，等它结束' })
        const name = safeName(url.searchParams.get('name') || req.headers['x-paperdepot-name'] || 'upload.pdf')
        const buf = await readBody(req, MAX_BODY)
        if (!buf.length) return sendJson(res, 400, { ok: false, error: '空文件' })
        if (!(buf[0] === 0x25 && buf[1] === 0x50 && buf[2] === 0x44 && buf[3] === 0x46)) return sendJson(res, 400, { ok: false, error: '不是 PDF（头部不是 %PDF）' })
        fs.mkdirSync(config.inboxDir, { recursive: true })
        const dst = path.join(config.inboxDir, `${Date.now()}-${name}`)
        fs.writeFileSync(dst, buf)
        if (config.dryRun) {
          jobState().job = { id: 'dry', kind: 'import', file: name, state: 'done', lines: [`（dry-run）已接收 ${name}，${buf.length} 字节`], startedAt: new Date().toISOString(), finishedAt: new Date().toISOString() }
          return sendJson(res, 202, { ok: true, file: name, bytes: buf.length, dryRun: true })
        }
        runImport(dst, config, host).catch((e) => console.error('[paperdepot] import failed', e))
        return sendJson(res, 202, { ok: true, accepted: true, file: name, bytes: buf.length })
      }
      if (p === '/paperdepot/api/providers') {
        try {
          const llm = getLlm(host)
          const list = llm && typeof llm.listProviders === 'function' ? llm.listProviders() : []
          return sendJson(res, 200, { ok: true, providers: list })
        } catch (err) {
          return sendJson(res, 500, { ok: false, error: String((err && err.message) || err) })
        }
      }
      if (p === '/paperdepot/api/summarize' && req.method === 'POST') {
        if (jobState().job && jobState().job.state === 'running') return sendJson(res, 409, { ok: false, error: '已有任务在跑，等它结束' })
        const name = url.searchParams.get('dir') || ''
        const entry = path.join(config.vault, '1-Papers', name)
        if (!name || !fs.existsSync(path.join(entry, 'index.md'))) return sendJson(res, 404, { ok: false, error: '找不到条目' })
        const job = {
          id: Date.now().toString(36),
          kind: 'summarize',
          file: name,
          state: 'running',
          lines: [`▶ 生成摘要：${name}`, `  模型: ${config.provider}/${config.model}`],
          startedAt: new Date().toISOString(),
        }
        jobState().job = job
        ;(async () => {
          try {
            await summarizeOne(job, config, host, name)
            job.state = 'done'
          } catch (err) {
            job.lines.push(`❌ ${err.message}`)
            job.state = 'error'
          }
          job.finishedAt = new Date().toISOString()
          statsCache = { at: 0, vault: '', data: null }
        })()
        return sendJson(res, 202, { ok: true, accepted: true, dir: name })
      }
      return sendJson(res, 404, { ok: false, error: 'not found', path: p })
    } catch (err) {
      return sendJson(res, 500, { ok: false, error: String((err && err.message) || err) })
    }
  }
}
