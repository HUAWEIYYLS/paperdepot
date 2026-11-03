// 生成 DSH 插件市场索引（format 1）：让用户把本仓库当作「发现」页的自定义索引源。
// 用法：node scripts/build-market-index.mjs
// 发布新版本后重跑一次并提交 market/index.json，索引里的 version / commit 才会跟上。
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))

const git = (args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim()
const commit = git(['rev-parse', 'HEAD'])
const publishTimestamp = Number(git(['log', '-1', '--format=%ct']))
const repoUrl = 'https://github.com/HUAWEIYYLS/paperdepot'

// 默认按 Git 源（固定提交）写索引；npm 发布之后用 --npm 切成 npm 源，装的是 registry 上的预打包 tarball。
const useNpm = process.argv.includes('--npm')
const versionSource = useNpm ? { type: 'npm' } : { type: 'git', url: repoUrl, commit }

if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error(`HEAD 不是 40 位提交号：${commit}`)

const index = {
  format: 1,
  title: {
    en: 'PaperDepot plugin market',
    'zh-cn': '论文库（PaperDepot）插件索引',
  },
  description: {
    en: 'Self-hosted DSH plugin market index for PaperDepot.',
    'zh-cn': 'PaperDepot 自建的 DSH 插件索引，只收录本插件。',
  },
  metadata: {
    categories: {
      papers: { title: { en: 'Papers & literature', 'zh-cn': '论文与文献' } },
    },
    labels: {
      dsh: { title: { en: 'DSH plugin', 'zh-cn': 'DSH 插件' } },
      obsidian: { title: { en: 'Obsidian', 'zh-cn': 'Obsidian' } },
      mineru: { title: { en: 'MinerU', 'zh-cn': 'MinerU' } },
    },
  },
  plugins: [
    {
      name: pkg.name,
      title: {
        en: 'PaperDepot (论文库)',
        'zh-cn': '论文库（PaperDepot）',
      },
      description: {
        en: 'Turn PDF papers into a searchable, readable, connected Obsidian paper library. DSH plugin.',
        'zh-cn': '把 PDF 论文变成可检索、可读、可连接的 Obsidian 论文库。DSH 插件，不依赖 Zotero。',
      },
      author: 'HUAWEIYYLS',
      homepage: `${repoUrl}#readme`,
      repository: { url: repoUrl },
      metadata: {
        category: 'papers',
        keywords: ['dsh', 'dsh-plugin', 'obsidian', 'paper', 'pdf', 'mineru', 'literature'],
        labels: ['dsh', 'obsidian', 'mineru'],
      },
      versions: [
        {
          version: pkg.version,
          publishTimestamp,
          source: versionSource,
          engines: { dsh: pkg.engines.dsh },
        },
      ],
    },
  ],
}

const outDir = path.join(root, 'market')
fs.mkdirSync(outDir, { recursive: true })
const outFile = path.join(outDir, 'index.json')
fs.writeFileSync(outFile, JSON.stringify(index, null, 2) + '\n', 'utf8')

// 与 DSH 校验器同规则的自检（不引入运行时依赖）。
const semver = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/
const problems = []
if (index.format !== 1) problems.push('format 必须为 1')
if (!index.title.en) problems.push('title 必须含 en')
if (!Array.isArray(index.plugins) || index.plugins.length === 0) problems.push('plugins 必须是非空数组')
for (const plugin of index.plugins) {
  if (!/^(?:@[a-z0-9][a-z0-9._~-]*\/)?[a-z0-9][a-z0-9._~-]*$/.test(plugin.name)) problems.push(`包名不合法：${plugin.name}`)
  if (!plugin.versions.length) problems.push(`${plugin.name} 没有版本`)
  for (const v of plugin.versions) {
    if (!semver.test(v.version)) problems.push(`版本不是 SemVer：${v.version}`)
    if (!Number.isInteger(v.publishTimestamp) || v.publishTimestamp < 0 || v.publishTimestamp >= 1e11) problems.push('publishTimestamp 不合法')
    if (v.source.type === 'git') {
      if (!/^[0-9a-f]{40}$/.test(v.source.commit)) problems.push('git commit 必须是 40 位小写十六进制')
      let url
      try {
        url = new URL(v.source.url)
      } catch {
        url = null
      }
      if (!url || url.protocol !== 'https:' || url.search || url.hash) problems.push('git url 必须是规范的 https 地址且不带查询/片段')
    }
  }
}
if (problems.length) {
  console.error('❌ 市场索引自检失败：')
  for (const p of problems) console.error('  - ' + p)
  process.exit(1)
}

console.log(`✅ 已生成 ${path.relative(root, outFile)}（${pkg.name}@${pkg.version} @ ${commit.slice(0, 7)}）`)
