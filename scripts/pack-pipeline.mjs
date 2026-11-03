// 打包前把仓库根目录的运行流水线复制进插件包 ./pipeline，
// 让 npm 安装的用户不需要额外 clone 仓库也能跑流水线。
// 由 npm 的 prepack hook 自动执行；产物 pipeline/ 不进 git。
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const pkg = path.resolve(here, '..')
const out = path.join(pkg, 'pipeline')

// 只打包运行时需要的脚本。开发脚本、Windows GUI 导入器、个人清单都不进包。
const TOOLS = [
  '_paths.py',
  'ingest.py',
  'mineru_parse.py',
  'fetch_metadata.py',
  'doi_from_pdf.py',
  'build_entry.py',
  'make_digest.py',
  'apply_summary.py',
  'apply_tagmap.py',
  'validate_summary.py',
  'make_index.py',
  'make_nav.py',
  'make_obsidian_graph.py',
  'verify_vault.py',
  'dedup.py',
  'repair_metadata.py',
  'make_concept_index.py',
  'make_concept_material.py',
  'verify_concepts.py',
  'make_mobile_reader.py',
]

const CONFIG = [
  'SKILL.md',
  'SUMMARY_SPEC.md',
  'CONCEPT_SPEC.md',
  'tagmap_领域.json',
  'tagmap_方法.json',
  'tagmap_应用.json',
  'tagmap_仪器.json',
  'secrets.example.json',
]

if (!fs.existsSync(path.join(pkg, 'tools', 'ingest.py'))) {
  console.error('[pack-pipeline] 找不到根目录 tools/ingest.py：请在 paperdepot 仓库根运行')
  process.exit(1)
}

fs.rmSync(out, { recursive: true, force: true })
fs.mkdirSync(out, { recursive: true })

const missing = []
function copyOne(srcDir, rel) {
  const src = path.join(srcDir, rel)
  if (!fs.existsSync(src)) {
    missing.push(path.join(path.basename(srcDir), rel))
    return
  }
  const dst = path.join(out, path.basename(srcDir), rel)
  fs.mkdirSync(path.dirname(dst), { recursive: true })
  fs.copyFileSync(src, dst)
}

for (const name of TOOLS) copyOne(path.join(pkg, 'tools'), name)
for (const name of CONFIG) copyOne(path.join(pkg, 'config'), name)

if (fs.existsSync(path.join(pkg, 'requirements.txt'))) {
  fs.copyFileSync(path.join(pkg, 'requirements.txt'), path.join(out, 'requirements.txt'))
} else {
  missing.push('requirements.txt')
}

if (missing.length) {
  console.error('[pack-pipeline] 缺少必要文件：')
  for (const m of missing) console.error('  - ' + m)
  process.exit(1)
}

fs.writeFileSync(
  path.join(out, 'README.md'),
  '# 内置流水线\n\n' +
    '本目录由 `scripts/pack-pipeline.mjs` 在 npm pack/publish 时生成，\n' +
    '包含论文库的 Python 流水线（`tools/`）与受控词表/提示词（`config/`）。\n\n' +
    '用户侧：数据写到 `~/.dsh/paperdepot/`（可用 `PAPERDEPOT_HOME` 覆盖），\n' +
    'Obsidian 库路径在插件面板里选。\n',
  'utf8',
)

console.log(`[pack-pipeline] 已生成 ${out}（${TOOLS.length} 个脚本 / ${CONFIG.length} 个配置）`)
