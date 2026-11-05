# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-05

### Changed

- **破坏性：npm 包名 / DSH 安装名由 `paperdepot` 改为 `dsh-paperdepot`**，与 DSH 社区插件
  命名习惯一致（awesome-dsh-plugin 中多数条目以 `dsh-` 开头）。新包从 0.2.0 起发布；
  旧包 `paperdepot@0.1.3` 不再更新，只做 deprecate 提示。
- **功能、API、数据全部不变**：HTTP 路由仍是 `/paperdepot/api/*`，配置/缓存仍在
  `~/.dsh/paperdepot/`，环境变量仍是 `PAPERDEPOT_*`，Obsidian 库、MinerU key 与面板状态
  都不需要迁移。本次只改安装名。

### 升级必读（0.1.x → 0.2.0）

```powershell
cd "$env:USERPROFILE\.dsh\profiles\desktop"
pnpm remove paperdepot
pnpm add dsh-paperdepot@0.2.0
```

然后把 profile `cordis.patch.yml` 里的 `name: paperdepot` 改成 `name: dsh-paperdepot`
（`id: paperdepot` 可以保留），重启 DSH。dshmarket 的自动更新按包名比对，改名后需要做一次
上面这次手动迁移，之后恢复一键更新。

## [0.1.3] - 2026-11-05

### Fixed

- **安装态 MinerU key 读不到（面板显示「已配置」，导入却报「未配置 MinerU key」）**：
  宿主把 key 写在 `~/.dsh/paperdepot/config/secrets.local.json`，而 Python 流水线
  （`pipeline/tools/mineru_parse.py`）只去插件包内 `config/` 找，两边各读各的路径。
  现在宿主启动 Python 子进程时会把 `PAPERDEPOT_HOME` / `PAPERDEPOT_CONFIG_DIR` /
  `MINERU_API_KEY` 一并传下去；`tools/_paths.py` 也会识别 `<插件包>/pipeline/tools`
  安装布局，把用户配置目录统一到 `~/.dsh/paperdepot/config/`；`mineru_parse.py`
  按「环境变量 → `PAPERDEPOT_CONFIG_DIR` → `PAPERDEPOT_HOME` → 用户配置目录 →
  旧插件包路径」依次查找。面板配置卡新增「Python 流水线能否读到同一个 key」自检，
  直接暴露这类不一致。
- 安装态直接运行 `python pipeline/tools/ingest.py`（不带 `--vault`）时，
  `_paths.default_vault()` 之前读的是插件包内 `config/`，现在读用户配置目录，
  能找到面板里设置的 Obsidian 库。

## [0.1.2] - 2026-11-03

### Added

- 批量补摘要：面板顶栏「批量补摘要（N）」把「待生成」条目排队跑完，底部进度条实时显示
  完成/失败数，可随时「停止」；中断后再点会跳过已完成的继续（断点续跑）。
  对应 host 新路由 `POST /paperdepot/api/summarize-pending`、`POST /paperdepot/api/job-cancel`。
  历史遗留（开源前入库、当时无模型）的条目不再需要逐篇手动补。

### Changed

- 论文 / 概念详情页改为阅读版式渲染：不再把 `index.md` 原始文本整段塞进 `<pre>`，
  而是去掉 frontmatter、导航块与重复的基础信息表，把标题、列表、表格、引用、行内公式
  与 wikilink 按论文排版显示；左栏列表重做为年份列 + 两行标题 + 待补标记，
  概念页增加引用数、别名、标签与相关论文列表。
- 统一分类语义色：`领域 / 方法 / 应用 / 仪器` 四类固定色 + 概念页独立色，用于论文与概念页的
  chip、列表里的领域识别点、总览的标签分布条形图与概念计数；正文里的概念 / 分类双链也按
  对应颜色显示。

### Fixed

- 面板底部增加固定安全区（等价 ArkUI 的 `Blank()`/bottom safe area）：在根 flex 容器末尾放一个
  不随内容滚动的占位块，把上方内容整体顶上去；同时修正总览页滚动容器缺 `box-sizing: border-box`
  导致 `padding-bottom` 被算到 100% 高度之外、跑到窗口下面的问题。滚动区底部留白同步收敛为
  72px（阅读区 / 总览）与 32px（列表），批量补摘要进度条距底 24px。

## [0.1.1] - 2026-11-03

### Added

- `docs/install-prompt.md`：一键安装提示词与日常使用提示词，可整段交给 DSH 自动完成安装与配置；
  README / README.en 增加入口。
- `market/index.json` + `scripts/build-market-index.mjs`：自建 DSH 插件市场索引（format 1），
  用户可在「发现」页添加索引源后搜索到并安装；README 增加「方式 E」。
- 发布到 npm registry：`paperdepot@0.1.1` 起可用 `pnpm add paperdepot` 安装，
  插件市场索引也切成 npm 源，安装不再需要下载 tarball。

### Fixed

- 从 Git 仓库地址直接安装时缺少 `pipeline/`（Python 流水线与受控词表）：新增 `prepare` 脚本在安装时生成。

## [0.1.0] - 2026-11-03

### Added

- 首个公开版本：DSH 左侧栏「论文库」面板。
- 拖拽 / 选择 / 路径导入 PDF，按 sha256 指纹去重。
- MinerU 解析 + Crossref / arXiv 元数据，组装 Obsidian 条目。
- LLM 生成结构化中文摘要与四类受控标签，支持单篇补跑。
- 总览 / 论文 / 概念页；分类页与导航块自动生成，幂等重建。
- Obsidian 原生 Properties / 标签 / 双链 / Graph 可用。
- 手机只读导出（EPUB / DOCX / PDF，需可选依赖）。
- 内置 Python 流水线打包，npm 安装用户无需另 clone 仓库。
- 本机验收：fixture 自检、包内容检查、个人路径/旧品牌/密钥扫描、CI。

### Security

- 不内置任何 MinerU key；key 只写本机配置文件或环境变量。
- 发布历史与包内容经过密钥 / 个人路径扫描。

### Notes

- Windows 10/11 一等支持；macOS / Linux 实验性。
- 摘要质量取决于所配置的模型；没有可用模型时条目仍可入库。
