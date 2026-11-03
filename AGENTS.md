# AGENTS.md — PaperDepot 仓库规则

本仓库是 **论文库（PaperDepot）**：DeepSeek Harness（DSH）插件 + Python 流水线，
把 PDF 论文变成 Obsidian 论文库。

## 目录

| 路径 | 作用 |
|---|---|
| `lib/index.js` | 插件入口，转发到 `host.js` |
| `lib/host.js` | host 薄壳：注册 `/paperdepot/api`，按 mtime 热加载 `impl.js` |
| `lib/impl.js` | host 逻辑：统计 / 论文 / 导入 / 摘要 / 配置 |
| `lib/client.js` | 左侧栏面板（DSH `window.__ModuleLoader__` 格式，无构建步骤） |
| `tools/` | Python 流水线；`tools/_paths.py` 是跨平台路径工具 |
| `config/` | 受控词表、摘要/概念规范、密钥模板 |
| `tests/fixture-vault/` | 合成测试库（无真实论文） |
| `scripts/pack-pipeline.mjs` | 打包时把运行时 tools/config 复制进 `pipeline/` |
| `.github/workflows/ci.yml` | Windows + Ubuntu 自检 / 包检查 / 路径检查 / gitleaks |

## 常用命令

```powershell
node scripts/selftest.mjs tests/fixture-vault
node tests/check-package.mjs
node tests/check-paths.mjs
python -m compileall -q tools
python -m pip install -r requirements-dev.txt
```

## 铁律

1. **不提交密钥、真实库路径、个人绝对路径、论文原文/摘要。**
   `node tests/check-paths.mjs` 必须通过；`.gitignore` 已覆盖 `config/*.local.json`、`cache/`、`pipeline/`。
2. **写操作走 `tools/`**，插件不另写一套入库/摘要逻辑。
3. **不要手改 `pipeline/`**：它由 `scripts/pack-pipeline.mjs` 在打包时生成，不入 git。
4. **受控词表以 `config/tagmap_*.json` 为准**；新增标签走 PR，并更新 fixture 自检。
5. **用户可见变更**要更新 `README.md`、`README.en.md`（概述）和 `CHANGELOG.md`。
6. **JS 不引入构建链**：`lib/client.js` 直接可读；保持 2 空格、单引号、无分号。
7. **Python 路径操作**用 `tools/_paths.py` 的 `lp()`；不要在工具里写死 `\\?\` 或绝对路径。
8. **测试用合成数据**：不要用真实论文做 fixture；数字不得编造。
9. **发布前**跑 `tests/check-package.mjs`，确认 npm 包不含 `*.local.json`、个人清单、缓存。
10. **公开仓库不写个人模型规则**；模型/provider 由使用者在本机配置。

## 提交

- 建议 `feat:` / `fix:` / `docs:` / `test:` / `chore:` 前缀。
- 行为变更带测试；UI 变更带截图（PR 描述）。
- 提交代码即同意以 MIT 许可证贡献。
