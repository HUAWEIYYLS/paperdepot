// 扫描公开树：个人路径、旧品牌、疑似密钥。CI 与本机都跑。
// 用法：node tests/check-paths.mjs
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SKIP_DIRS = new Set(['.git', 'cache', 'node_modules', 'pipeline', '__pycache__', '.venv', '_private'])
// 本文件与 check-package 故意包含要扫描的模式，跳过自身
const SKIP_FILES = new Set(['tests/check-paths.mjs', 'tests/check-package.mjs'])
const SKIP_EXT = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.docx', '.xlsx', '.zip',
  '.ico', '.woff', '.woff2', '.tgz', '.bundle', '.pyc',
])

// 本地配置文件（被 .gitignore 忽略）允许包含本机真实路径
const isLocalConfig = (p) => /\.local\.json$/i.test(p)

const RULES = [
  { name: '真实 Windows 用户目录', re: /C:\\Users\\(?!<)[^\\/"'\s]+/ },
  { name: '个人工作目录', re: /D:\\YHJwork/ },
  { name: '个人用户名', re: /83740/ },
  { name: '个人云盘路径', re: /Huawei cloud/i },
  { name: '旧沙盒库名', re: /_obsidian_sandbox_vault/ },
  { name: '旧品牌 dsh-wenshu', re: /dsh-wenshu/ },
  { name: '旧环境变量 WENSHU', re: /WENSHU/ },
  { name: '旧 API /wenshu/', re: /\/wenshu\// },
  { name: '旧中文名 文枢', re: /文枢/ },
  { name: '旧小写 wenshu', re: /wenshu/ },
  { name: '疑似 MinerU key', re: /sk-[A-Za-z0-9]{12,}/ },
  { name: '占位邮箱', re: /research@example\.com/ },
]

const hits = []
function walk(dir) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name)
    if (ent.isDirectory()) {
      if (SKIP_DIRS.has(ent.name)) continue
      walk(full)
      continue
    }
    if (!ent.isFile()) continue
    if (SKIP_FILES.has(path.relative(root, full).replace(/\\/g, '/'))) continue
    if (SKIP_EXT.has(path.extname(ent.name).toLowerCase())) continue
    if (isLocalConfig(full)) continue
    let txt
    try {
      txt = fs.readFileSync(full, 'utf8')
    } catch {
      continue
    }
    if (txt.includes('\u0000')) continue
    const lines = txt.split(/\r?\n/)
    for (let i = 0; i < lines.length; i++) {
      for (const rule of RULES) {
        if (rule.re.test(lines[i])) {
          hits.push(`${path.relative(root, full)}:${i + 1} [${rule.name}] ${lines[i].trim().slice(0, 160)}`)
        }
      }
    }
  }
}
walk(root)

if (hits.length) {
  console.error('❌ 发现个人路径 / 旧品牌 / 疑似密钥：')
  for (const h of hits) console.error('  - ' + h)
  process.exit(1)
}
console.log('✅ 路径/品牌/密钥扫描通过')
