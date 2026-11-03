# Contributing to 论文库 / PaperDepot

感谢你愿意贡献。这个项目是 DeepSeek Harness（DSH）插件 + 一套 Python 流水线，
目标是把 PDF 论文可靠地变成 Obsidian 论文库。

## 开发环境

- Node.js 20+
- Python 3.10+
- Obsidian（用于人工验收 UI）
- DSH 桌面版（用于加载插件）

```powershell
python -m pip install -r requirements-dev.txt
```

依赖说明：`pymupdf`（AGPL-3.0）用于 PDF 首页 DOI 提取，`python-docx` 用于可选 DOCX 导出；
两者都是用户自行安装的独立依赖，不随本项目打包。

## 目录地图

| 路径 | 作用 |
|---|---|
| `lib/index.js` | 插件入口，转发到 `host.js` |
| `lib/host.js` | host 薄壳：注册 `/paperdepot/api`，热加载 `impl.js` |
| `lib/impl.js` | host 逻辑：统计 / 论文 / 导入 / 摘要 / 配置 |
| `lib/client.js` | 左侧栏面板（DSH `window.__ModuleLoader__` 格式，无构建步骤） |
| `tools/` | Python 流水线；`tools/_paths.py` 是跨平台路径工具 |
| `config/` | 受控词表、摘要/概念规范、密钥模板 |
| `templates/vault-skeleton/` | 空库初始化模板（P1） |
| `tests/fixture-vault/` | 合成测试库，不包含真实论文 |
| `scripts/` | `selftest.mjs`、`pack-pipeline.mjs` |
| `.github/workflows/` | CI |
| `docs/` | 用户/维护者文档（`docs/maintainer/` 已有发布与分诊手册） |

## 跑测试

```powershell
# Node 契约自检（用合成 fixture 库）
node scripts/selftest.mjs tests/fixture-vault

# 包内容检查（会跑 npm pack --dry-run）
node tests/check-package.mjs

# 个人路径 / 旧品牌 / 疑似密钥扫描
node tests/check-paths.mjs
```

CI 在 Windows + Ubuntu 上跑同样三项，并跑 gitleaks。

## 代码风格

- JS：2 空格、单引号、无分号、ESM；不引入构建链，`lib/client.js` 直接可读。
- Python：4 空格、UTF-8、标准库优先；新增路径操作统一用 `tools/_paths.py` 的 `lp()`。
- 所有写入 Obsidian 的逻辑走 `tools/`，插件不另写一套。
- 不提交个人绝对路径、真实库路径、MinerU key 或论文原文。
- 用户可见文案用中文；代码注释中英均可。

## 提交与 PR

1. Fork 并从 `main` 开分支。
2. 行为变更必须带测试或至少更新 `tests/fixture-vault` / selftest。
3. 用户可见变更更新 `README.md` / `CHANGELOG.md`；配置/API 变更写迁移说明。
4. PR 描述写清：改了什么、为什么、怎么验证、是否有截图（UI 变更）。
5. 提交信息建议用 `feat:` / `fix:` / `docs:` / `test:` / `chore:` 前缀；中英文都可。

## 增加受控标签

标签词表是产品的一部分，改动请单独提 PR：

1. 编辑 `config/tagmap_<类别>.json` 的 `canonical`（四类：领域 / 方法 / 应用 / 仪器）。
2. 如果只是别名归并，改 `mapping`，把别名映射到已有的规范词。
3. 跑 `node scripts/selftest.mjs tests/fixture-vault`，确认 fixture 标签仍通过校验。
4. 在 PR 里说明为什么需要新词、影响哪些条目。

## 文档

- 面向用户：`README.md`、`docs/`。
- 面向维护者：`docs/maintainer/release.md`、`docs/maintainer/triage.md`。
- 行为准则：`CODE_OF_CONDUCT.md`。
- 不要把内部实验报告、个人库统计、真实论文标题/摘要放进公开仓库。

## 许可

提交代码即表示你同意以 MIT 许可证贡献，并确认你有权提交这些代码。
