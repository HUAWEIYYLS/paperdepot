// 校验 npm 包内容：只允许运行时文件，不允许个人配置/清单/缓存。
// 用法：node tests/check-package.mjs
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'))

const REQUIRED = [
  'package.json',
  'lib/index.js',
  'lib/host.js',
  'lib/impl.js',
  'lib/client.js',
  'cordis.patch.yml',
  'README.md',
  'LICENSE',
  'THIRD_PARTY_NOTICES.md',
  'requirements.txt',
  'pipeline/tools/ingest.py',
  'pipeline/tools/apply_summary.py',
  'pipeline/tools/validate_summary.py',
  'pipeline/config/SKILL.md',
  'pipeline/config/tagmap_领域.json',
  'pipeline/requirements.txt',
]

const FORBIDDEN = [
  /(^|\/)(secrets|paperdepot|wenshu)\.local\.json$/,
  /(^|\/)digest_manifest\.json$/,
  /(^|\/)summary_items\.json$/,
  /(^|\/)tags_[^/]*\.json$/,
  /(^|\/)archive\//,
  /(^|\/)cache\//,
  /(^|\/)__pycache__\//,
  /(^|\/)paperdepot_importer\.pyw$/,
  /\.pyc$/,
]

const out = execSync('npm pack --dry-run --json', {
  cwd: root,
  encoding: 'utf8',
  maxBuffer: 20 * 1024 * 1024,
  shell: true,
})
const start = out.indexOf('\n[\n')
if (start < 0) throw new Error('无法解析 npm pack --json 输出：\n' + out.slice(0, 800))
const parsed = JSON.parse(out.slice(start + 1))[0]
const files = parsed.files.map((f) => f.path)
const errors = []

for (const r of REQUIRED) if (!files.includes(r)) errors.push(`缺少文件：${r}`)
for (const f of files) {
  for (const re of FORBIDDEN) if (re.test(f)) errors.push(`禁止打包：${f}`)
  if (f.startsWith('docs/') || f.startsWith('tests/') || f.startsWith('examples/')) {
    errors.push(`不应打包开发/文档目录：${f}`)
  }
}
if (parsed.size > 2 * 1024 * 1024) errors.push(`包体积过大：${parsed.size} bytes`)
if (pkg.name !== 'paperdepot') errors.push(`package.json name 不是 paperdepot：${pkg.name}`)

if (errors.length) {
  console.error('❌ 包内容检查失败：')
  for (const e of errors) console.error('  - ' + e)
  process.exit(1)
}
console.log(`✅ 包内容检查通过：${files.length} 个文件，${parsed.size} bytes`)
