// 论文库插件自检：不启动 DSH，直接验证 host impl / client 两半的契约
// 用法：node scripts/selftest.mjs [vault]
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import vm from 'node:vm'
import { EventEmitter } from 'node:events'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const vault = process.argv[2] || process.env.PAPERDEPOT_VAULT || path.join(root, 'tests', 'fixture-vault')

let failed = 0
const check = (name, ok, extra = '') => {
  console.log(`${ok ? '✅' : '❌'} ${name}${extra ? '  ' + extra : ''}`)
  if (!ok) failed += 1
}

// ---------- host impl ----------
const impl = await import(pathToFileURL(path.join(root, 'lib/impl.js')).href)
check('impl 导出 createHandler', typeof impl.createHandler === 'function')

const cfgRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'paperdepot-selftest-cfg-'))
const handler = impl.createHandler({
  vault,
  dryRun: true,
  inboxDir: path.join(cfgRoot, 'inbox'),
  secretsPath: path.join(cfgRoot, 'secrets.json'),
  statePath: path.join(cfgRoot, 'state.json'),
})

async function call(method, p, body) {
  const req = new EventEmitter()
  req.url = p
  req.method = method
  if (body) {
    Object.assign(req, { headers: {} })
    setTimeout(() => {
      req.emit('data', body)
      req.emit('end')
    }, 0)
  }
  const res = {
    status: 0,
    body: '',
    writeHead(c) { this.status = c },
    end(b) { this.body = String(b) },
  }
  await handler(req, res)
  let json = null
  try { json = JSON.parse(res.body) } catch { /* non-json */ }
  return { status: res.status, json, text: res.body }
}

const health = await call('GET', '/paperdepot/api/health')
check('GET /health v3', health.status === 200 && health.json.version === 3 && health.json.vault === vault)

const stats = await call('GET', '/paperdepot/api/stats')
check('GET /stats', stats.status === 200 && stats.json.ok === true && stats.json.papers >= 0, `papers=${stats.json.papers}`)

const papers = await call('GET', '/paperdepot/api/papers?limit=5')
check('GET /papers', papers.status === 200 && Array.isArray(papers.json.items), `items=${papers.json.items?.length}`)

const first = papers.json.items?.[0]
if (first) {
  const paper = await call('GET', '/paperdepot/api/paper?dir=' + encodeURIComponent(first.dir))
  check('GET /paper', paper.status === 200 && paper.json.index.includes('---'), `dir=${first.dir.slice(0, 40)}`)
  check('GET /paper 含概念/分类', Array.isArray(paper.json.concepts) && Array.isArray(paper.json.taxonomy), `concepts=${paper.json.concepts?.length} taxonomy=${paper.json.taxonomy?.length}`)
}

const concepts = await call('GET', '/paperdepot/api/concepts')
check('GET /concepts', concepts.status === 200 && Array.isArray(concepts.json.items), `total=${concepts.json.total}`)

const conceptName = concepts.json.items?.[0]?.name
if (conceptName) {
  const concept = await call('GET', '/paperdepot/api/concept?name=' + encodeURIComponent(conceptName))
  check('GET /concept', concept.status === 200 && concept.json.markdown.includes('---') && Array.isArray(concept.json.papers), `name=${conceptName}`)
}

const graph = await call('GET', '/paperdepot/api/graph')
check('GET /graph', graph.status === 200 && Array.isArray(graph.json.papers) && Array.isArray(graph.json.concepts) && Array.isArray(graph.json.edges), `nodes=${graph.json.papers.length}+${graph.json.concepts.length} edges=${graph.json.edges.length}`)
check('GET /graph 含分类节点', Array.isArray(graph.json.taxonomy) && Array.isArray(graph.json.taxEdges), `taxonomy=${graph.json.taxonomy?.length} taxEdges=${graph.json.taxEdges?.length}`)

const job0 = await call('GET', '/paperdepot/api/job')
check('GET /job', job0.status === 200 && job0.json.ok === true)

const pdf = Buffer.from('%PDF-1.4\n% selftest\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')
const imp = await call('POST', '/paperdepot/api/import?name=selftest.pdf', pdf)
check('POST /import（dry-run）', imp.status === 202 && imp.json.ok === true && imp.json.dryRun === true, JSON.stringify(imp.json))

const bad = await call('POST', '/paperdepot/api/import?name=x.pdf', Buffer.from('not a pdf'))
check('POST /import 拒绝非 PDF', bad.status === 400)

// 按本地路径导入（桌面端最稳的入口）
const pdfOnDisk = path.join(cfgRoot, 'path-import.pdf')
fs.writeFileSync(pdfOnDisk, pdf)
const byPath = await call('POST', '/paperdepot/api/import-path', Buffer.from(JSON.stringify({ path: pdfOnDisk })))
check('POST /import-path（dry-run）', byPath.status === 202 && byPath.json.ok === true && byPath.json.dryRun === true, JSON.stringify(byPath.json))
const byBadPath = await call('POST', '/paperdepot/api/import-path', Buffer.from(JSON.stringify({ path: path.join(cfgRoot, 'nope.pdf') })))
check('POST /import-path 拒绝不存在路径', byBadPath.status === 404, byBadPath.json && byBadPath.json.error)

// ---------- 首次配置（onboarding） ----------
const setup = await call('GET', '/paperdepot/api/setup/status')
check(
  'GET /setup/status',
  setup.status === 200 && setup.json.ok === true && typeof setup.json.hasKey === 'boolean' && !!setup.json.python,
  `hasKey=${setup.json.hasKey} python=${setup.json.python && setup.json.python.version}`,
)
const badKey = await call('POST', '/paperdepot/api/setup/key', Buffer.from('{"key":"abc"}'))
check('POST /setup/key 拒绝坏格式', badKey.status === 400, badKey.json && badKey.json.error)
const setVault = await call('POST', '/paperdepot/api/setup/vault', Buffer.from(JSON.stringify({ vault: cfgRoot })))
check('POST /setup/vault 保存', setVault.status === 200 && setVault.json.vault === cfgRoot)
const restore = await call('POST', '/paperdepot/api/setup/vault', Buffer.from(JSON.stringify({ vault })))
check('POST /setup/vault 恢复', restore.status === 200)

// ---------- P2：摘要（mock LLM，临时库） ----------
const tmpVault = fs.mkdtempSync(path.join(os.tmpdir(), 'paperdepot-selftest-'))
const srcPapers = path.join(vault, '1-Papers')
const anyEntry = fs
  .readdirSync(srcPapers, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !d.name.startsWith('_'))
  .map((d) => d.name)
  .find((name) => fs.existsSync(path.join(srcPapers, name, 'full.md')))

if (anyEntry) {
  const srcDir = path.join(srcPapers, anyEntry)
  const dstDir = path.join(tmpVault, '1-Papers', anyEntry)
  fs.mkdirSync(path.dirname(dstDir), { recursive: true })
  fs.cpSync(srcDir, dstDir, { recursive: true })
  // 把条目改回「导入骨架」状态（保留 frontmatter，正文只留占位）
  const idx = fs.readFileSync(path.join(dstDir, 'index.md'), 'utf8')
  const m = /^---\s*\n[\s\S]*?\n---\s*\n/.exec(idx)
  const fmBlock = m ? m[0] : '---\ntitle: "自检条目"\n---\n'
  fs.writeFileSync(path.join(dstDir, 'index.md'), fmBlock + '\n## 一句话总结\n\n> 待生成\n\n## 研究背景\n\n待生成\n')
  const pendingEntry = anyEntry

  const mockLLM = {
    async *stream() {
      yield { type: 'block-start', index: 0, blockType: 'text' }
      yield {
        type: 'text-delta',
        index: 0,
        text: JSON.stringify({
          summary_md: '# 📖 论文摘要\n\n## 一句话总结\n\n> 自检用的一句话总结。\n\n## 📈 论文结构\n\n1. 测试章节 — 说明\n',
          tags_md: '# 自检 - 标签\n\n## 研究领域\n- 天文仪器\n\n## 技术方法\n- 光纤定位\n\n## 应用场景\n- 光纤检测与焦面定位\n\n## 仪器设备\n- LAMOST\n',
        }),
      }
      yield { type: 'finish' }
    },
  }
  const host = { ctx: { get: (n) => (n === 'llm' ? mockLLM : null) } }
  const h2 = impl.createHandler(
    {
      vault: tmpVault,
      digestDir: path.join(tmpVault, 'digests'),
      statePath: path.join(tmpVault, 'state.json'),
      python: process.env.PAPERDEPOT_PYTHON || 'python',
    },
    host,
  )
  const call2 = async (method, p) => {
    const req = new EventEmitter()
    req.url = p
    req.method = method
    const res = { status: 0, body: '', writeHead(c) { this.status = c }, end(b) { this.body = String(b) } }
    await h2(req, res)
    let json = null
    try { json = JSON.parse(res.body) } catch { /* ignore */ }
    return { status: res.status, json }
  }
  const accepted = await call2('POST', '/paperdepot/api/summarize?dir=' + encodeURIComponent(pendingEntry))
  check('POST /summarize 受理', accepted.status === 202 && accepted.json.ok === true, JSON.stringify(accepted.json))

  let job = null
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 400))
    const j = await call2('GET', '/paperdepot/api/job')
    job = j.json.job
    if (job && job.state !== 'running') break
  }
  check('摘要任务完成', job && job.state === 'done', job ? `${job.state} / ${job.lines.slice(-2).join(' | ')}`.slice(0, 160) : 'no job')
  const newIndex = fs.readFileSync(path.join(tmpVault, '1-Papers', pendingEntry, 'index.md'), 'utf8')
  check('index.md 写入摘要', newIndex.includes('自检用的一句话总结'))
  check('index.md 写入分层标签', newIndex.includes('领域/天文仪器') && newIndex.includes('方法/光纤定位'))

  // 批量补摘要：把条目打回「待生成」，一次排队跑完，验证进度与断点续跑的关键字段
  const batchEntries = [pendingEntry]
  const otherEntry = fs
    .readdirSync(srcPapers, { withFileTypes: true })
    .filter((d) => d.isDirectory() && !d.name.startsWith('_') && d.name !== pendingEntry)
    .map((d) => d.name)
    .find((name) => fs.existsSync(path.join(srcPapers, name, 'full.md')))
  if (otherEntry) {
    fs.cpSync(path.join(srcPapers, otherEntry), path.join(tmpVault, '1-Papers', otherEntry), { recursive: true })
    batchEntries.push(otherEntry)
  } else {
    // 库里只有一篇时复制一份，保证批量至少跑两篇（验证循环而不是只跑一篇）
    const copyName = `${pendingEntry} 副本`
    fs.cpSync(path.join(tmpVault, '1-Papers', pendingEntry), path.join(tmpVault, '1-Papers', copyName), { recursive: true })
    batchEntries.push(copyName)
  }
  for (const name of batchEntries) {
    const dir = path.join(tmpVault, '1-Papers', name)
    const idx2 = fs.readFileSync(path.join(dir, 'index.md'), 'utf8')
    const fm2 = /^---\s*\n[\s\S]*?\n---\s*\n/.exec(idx2)
    fs.writeFileSync(path.join(dir, 'index.md'), (fm2 ? fm2[0] : '') + '\n## 一句话总结\n\n> 待生成\n\n## 研究背景\n\n待生成\n')
  }
  const batchAccepted = await call2('POST', '/paperdepot/api/summarize-pending')
  check(
    'POST /summarize-pending 受理',
    batchAccepted.status === 202 && batchAccepted.json.total === batchEntries.length,
    JSON.stringify(batchAccepted.json),
  )
  let batchJob = null
  for (let i = 0; i < 300; i++) {
    await new Promise((r) => setTimeout(r, 400))
    const j = await call2('GET', '/paperdepot/api/job')
    batchJob = j.json.job
    if (batchJob && batchJob.state !== 'running') break
  }
  check(
    '批量补摘要任务完成',
    batchJob && batchJob.kind === 'summarize-batch' && batchJob.state === 'done' && batchJob.done === batchEntries.length,
    batchJob ? `${batchJob.state} ${batchJob.done}/${batchJob.total} failed=${(batchJob.failed || []).length}` : 'no job',
  )
  check(
    '批量补摘要写入全部条目',
    batchEntries.every((n) => fs.readFileSync(path.join(tmpVault, '1-Papers', n, 'index.md'), 'utf8').includes('自检用的一句话总结')),
  )
  const noPending = await call2('POST', '/paperdepot/api/summarize-pending')
  check('POST /summarize-pending 无待生成时拒绝', noPending.status === 400, noPending.json && noPending.json.error)

  // apply_summary 重建 index.md 时必须保留 make_nav 写入的导航块
  const entryDir = path.join(tmpVault, '1-Papers', pendingEntry)
  fs.copyFileSync(path.join(srcDir, 'index.md'), path.join(entryDir, 'index.md'))
  fs.writeFileSync(path.join(entryDir, 'summary.md'), '---\ntitle: x\n---\n\n# 📖 论文摘要\n\n## 一句话总结\n\n> 测试。\n', 'utf8')
  fs.writeFileSync(path.join(entryDir, 'tags.md'), '# x - 标签\n\n## 研究领域\n- 天文仪器\n\n## 技术方法\n- 光纤定位\n\n## 应用场景\n- 光纤检测与焦面定位\n\n## 仪器设备\n- LAMOST\n', 'utf8')
  const { spawnSync } = await import('node:child_process')
  const py = process.env.PAPERDEPOT_PYTHON || 'python'
  const sr = spawnSync(py, [path.resolve(root, 'tools', 'apply_summary.py'), '--vault', tmpVault, '--entry', pendingEntry], { encoding: 'utf8' })
  const afterNav = fs.readFileSync(path.join(entryDir, 'index.md'), 'utf8')
  check('apply_summary 保留导航块', sr.status === 0 && afterNav.includes('paperdepot:nav:start'), (sr.stderr || '').slice(0, 80))
  fs.rmSync(tmpVault, { recursive: true, force: true })
} else {
  console.log('⚠ 库里没有「待生成」条目，跳过 P2 摘要自检')
}

// 缓存迁移离线自检：陈旧 out_dir 应命中并改写路径（不耗 MinerU API）
{
  const { spawnSync: spawnCache } = await import('node:child_process')
  const py = process.env.PAPERDEPOT_PYTHON || 'python'
  const cr = spawnCache(py, [path.resolve(root, 'tools', 'mineru_parse.py'), '--selftest-cache'], { encoding: 'utf8' })
  check('缓存迁移自检（陈旧 out_dir / 版本判定）', cr.status === 0 && (cr.stdout || '').includes('cache selftest ok'), (cr.stderr || '').slice(0, 100))
}

// ---------- client ----------
const clientSrc = fs.readFileSync(path.join(root, 'lib/client.js'), 'utf8')
const implSrc = fs.readFileSync(path.join(root, 'lib/impl.js'), 'utf8')
let loaded = null
vm.runInNewContext(clientSrc, { window: { __ModuleLoader__: { load: (def) => (loaded = def) } }, console }, { filename: 'client.js' })
check('client 使用 __ModuleLoader__.load', loaded && loaded.id === 'paperdepot')

let registered = []
const mod = loaded.factory((id) => {
  if (id === 'react') {
    return {
      createElement: () => null,
      useEffect: () => {},
      useState: (v) => [v, () => {}],
      useCallback: (f) => f,
      useRef: (v) => ({ current: v }),
      Component: class {
        constructor(props) {
          this.props = props
          this.state = {}
        }
        setState(s) {
          this.state = { ...this.state, ...s }
        }
      },
    }
  }
  return {}
})
check('client 导出 apply/inject', typeof mod.apply === 'function' && Array.isArray(mod.inject))
mod.apply({ slots: { inject: (k, cb) => cb(), register: (spec) => (registered.push(spec), () => {}) } })
const panelEntry = registered.find((s) => s.name === 'sidebar.panellist')
const mainEntry = registered.find((s) => s.name === 'main')
check('client 左侧栏注册论文库面板', panelEntry && panelEntry.id === 'paperdepot' && panelEntry.label() === '论文库')
check('client 注册 main 整页内容', mainEntry && mainEntry.key === 'paperdepot')
check('client 不再占用会话页签/输入区', !clientSrc.includes('conversation.view') && !clientSrc.includes('conversation.composer'))
check('client 代码含导入 UI', clientSrc.includes('/paperdepot/api/import') && clientSrc.includes('onDrop'))
check('client 含概念页签、无插件内关系图页签', clientSrc.includes("['concepts', '概念'") && !clientSrc.includes("['graph', '关系图'"))
check('client 含重建导航/打开 Obsidian', clientSrc.includes('/rebuild-nav') && clientSrc.includes('打开 Obsidian'))
check('client 含面板级拖拽/路径导入', clientSrc.includes('onDrop') && clientSrc.includes('/import-path'))
check('client 含错误边界', clientSrc.includes('getDerivedStateFromError'))
check('client 含 Obsidian 跳转（走宿主）', clientSrc.includes('/paperdepot/api/open-obsidian') && !clientSrc.includes("window.open('obsidian://"))
check('host 含 open-obsidian 路由', implSrc.includes('/paperdepot/api/open-obsidian') && implSrc.includes('FileProtocolHandler'))
check('client 含批量补摘要入口与进度条', clientSrc.includes('/summarize-pending') && clientSrc.includes('批量补摘要'))
check('host 含批量补摘要 / 停止任务路由', implSrc.includes('/paperdepot/api/summarize-pending') && implSrc.includes('/paperdepot/api/job-cancel'))

// SKILL 契约：配置文件存在、宿主读取它并跑校验器
{
  const skillPath = path.join(root, 'config', 'SKILL.md')
  check('config/SKILL.md 存在', fs.existsSync(skillPath))
  check('host 摘要读 SKILL 并跑校验', implSrc.includes("'SKILL.md'") && implSrc.includes('validate_summary.py'))
  const papersDir = path.join(vault, '1-Papers')
  const entries = fs.existsSync(papersDir)
    ? fs.readdirSync(papersDir).filter((d) => !d.startsWith('_') && fs.existsSync(path.join(papersDir, d, 'index.md')))
    : []
  if (entries.length) {
    const { spawnSync } = await import('node:child_process')
    const py = process.env.PAPERDEPOT_PYTHON || 'python'
    const vr = spawnSync(py, [path.resolve(root, 'tools', 'validate_summary.py'), '--vault', vault, '--entry', entries[0]], {
      encoding: 'utf8',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    })
    check('validate_summary 在真实条目上通过', vr.status === 0, (vr.stdout || vr.stderr || '').split('\n')[0].slice(0, 80))
  }
}

console.log(failed === 0 ? '\n全部通过 ✅' : `\n${failed} 项失败 ❌`)
process.exit(failed === 0 ? 0 : 1)
