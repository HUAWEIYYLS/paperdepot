# 论文库（PaperDepot）

把 PDF 论文变成**可检索、可读、可连接**的 Obsidian 论文库。

论文库是一个 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（DSH）插件：
它负责「进件 + 组织」，Obsidian 只负责存储与阅读。

> **它不是 Obsidian 社区插件。** 它安装进 DSH，由 DSH 面板操作，写入你指定的 Obsidian 库。

```
PDF
 ├─ MinerU 解析        → full.md + images/ + layout.json
 ├─ 元数据获取          → 标题 / 作者 / 年份 / 期刊 / DOI
 ├─ 条目组装            → index.md + full.md + paper.pdf + images/figNN.jpg
 ├─ 摘要生成（LLM）     → 一句话总结 / 背景 / 方法 / 结果 / 结论 / 数据表
 └─ 标签生成（LLM）     → 四类分层标签，映射到受控词表
```

## 功能

- **拖 PDF 入库**：拖拽、选择文件或粘贴本地路径；同一 PDF 按指纹自动跳过。
- **自动元数据**：优先读 PDF 首页 DOI / arXiv 号，再走 Crossref / arXiv 精确查询。
- **结构化摘要与标签**：LLM 生成中文摘要和四类受控标签（领域 / 方法 / 应用 / 仪器），
  支持单篇补跑与「批量补摘要」（排队跑完待生成条目，可随时停止，再点会跳过已完成的继续）。
- **Obsidian 原生体验**：元数据写进 frontmatter，Properties / Dataview / 标签面板 / 双链 / Graph 直接可用。
- **总览 / 论文 / 概念**：面板内看统计、搜索条目、浏览概念页与相关论文。
- **阅读版式**：论文与概念详情按摘要排版（标题 / 列表 / 表格 / 行内公式 / 双链），
  不再显示原始 Markdown；概念页带引用数、别名与相关论文列表。
- **分类页与导航块**：自动生成 `3-Taxonomy/` 分类页和论文页导航块，幂等可重建。
- **手机只读导出**：整库导出 EPUB / DOCX / PDF，放到同步盘用手机阅读器看。
- **跨平台尽力而为**：Windows 一等支持；macOS / Linux 实验性（欢迎反馈）。

## 5 分钟快速开始

1. **准备 DSH + Obsidian**：安装 DSH 桌面版，并在 Obsidian 里新建或打开一个库（路径尽量短）。
2. **安装插件**：任选下面一种方式（已发布到 npm，推荐 `pnpm add paperdepot`；也可用 tarball 或
   DSH 的「添加插件」对话框）；
   不想手动敲命令，就把[一键安装提示词](https://github.com/HUAWEIYYLS/paperdepot/blob/main/docs/install-prompt.md)整段发给 DSH。
3. **申请 MinerU Token**：打开 <https://mineru.net> 注册 → 控制台 → API 管理 → 创建 Token。
4. **首次配置**：打开左侧栏「论文库」→ 配置卡里粘贴 Token → 保存并验证 → 选择 Obsidian 库路径。
5. **导入第一篇**：把 PDF 拖进面板 → 看实时日志 → 打开 Obsidian 的 `1-Papers/<标题>/index.md`。

> PDF 会发送到 MinerU 云端解析；摘要材料会发送给你在 DSH 中配置的模型。
> **涉密、未发表或不允许上传的稿件请不要导入。**

## 安装

> 完全不想手动操作？把[一键安装提示词](https://github.com/HUAWEIYYLS/paperdepot/blob/main/docs/install-prompt.md)
> 复制给 DSH，它会自己定位 profile、装包、写 `cordis.patch.yml`、装 Python 依赖并做安装后验证。

### 方式 A：npm 安装（推荐）

```powershell
cd "$env:USERPROFILE\.dsh\profiles\desktop"
pnpm add paperdepot
```

也可以在 DSH「插件 → 添加插件」对话框里直接填包名 `paperdepot`，它会自动装进 profile。

然后在 profile 的 `cordis.patch.yml` 末尾加上：

```yaml
- insert:
    - id: paperdepot
      name: paperdepot
      config:
        vault: 'C:\Users\<你>\Documents\ObsidianVault'
```

刷新 DSH（必要时重启）。

### 方式 B：DSH「发现」页 + 自建索引源

DSH 目前**没有官方插件市场**：开箱的「发现」页默认没有任何索引源。本仓库自带一个自建索引
（`market/index.json`，npm 源），启用后可在「发现」页搜索并一键安装：

1. DSH 侧栏 → **插件** → **实验性插件**旁的**更多** → 启用**自定义插件市场**；
2. 插件页 → **发现** → **添加索引源** → 粘贴：
   `https://raw.githubusercontent.com/HUAWEIYYLS/paperdepot/main/market/index.json`
3. 搜索「论文库」或 `paperdepot` → 安装。

### 方式 C：GitHub Release tarball（国内网络更稳）

从 Releases 下载 `paperdepot-<版本>.tgz`（如 `paperdepot-0.1.2.tgz`），然后：

```powershell
cd "$env:USERPROFILE\.dsh\profiles\desktop"
pnpm add "D:\downloads\paperdepot-0.1.2.tgz"
```

也可以把 tgz 的绝对路径填进 DSH「添加插件」对话框的输入框。

同样在 `cordis.patch.yml` 里加 `id: paperdepot / name: paperdepot` 的 insert。

### 方式 D：源码 link（开发 / 调试）

```powershell
git clone https://github.com/HUAWEIYYLS/paperdepot.git
cd "$env:USERPROFILE\.dsh\profiles\desktop"
pnpm add "link:D:\path\to\paperdepot"
```

`cordis.patch.yml` 同上。

> **重要**：profile 里的 `name:` 必须是包名 `paperdepot`，不能写 `paperdepot/host`。
> 写子路径会出现「host 正常、左侧栏没有论文库」。

## 首次配置

打开左侧栏「论文库」面板，第一次会看到配置卡：

1. **MinerU Token**：粘贴 → 「保存并验证」。插件会真的调一次 MinerU 接口验 key。
   Token 只写到本机配置文件，不会上传；也可以用环境变量 `MINERU_API_KEY`。
   安装态文件在 `~/.dsh/paperdepot/config/secrets.local.json`，插件启动 Python 流水线时
   会把同一份 key 与配置目录传进去（面板会显示「Python 流水线能读到同一个 key」）。
2. **Obsidian 库路径**：选择一个已存在的文件夹；空库也可以，第一次导入会创建 `1-Papers/`。
3. **Python 依赖**：需要 Python 3.10+ 和以下依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

   如果你是通过 npm 安装的，`requirements.txt` 在插件包的 `pipeline/` 目录里；
   面板的配置卡会显示当前流水线路径。

4. **摘要模型（可选）**：在 profile 的插件配置里设置 `provider` / `model`；
   不设置时使用宿主默认模型。没有可用模型也能入库，只是摘要/标签会处于「待生成」。

配置卡随时可以从右上角的「MinerU 已配置 / 未配置」按钮打开。

## 日常使用

| 动作 | 怎么做 |
|---|---|
| 导入单篇 | 把 PDF 拖进「论文库」面板，或点「选择 PDF」，或在输入框粘贴本地路径后回车 |
| 批量导入（CLI） | `python tools/ingest.py "D:\papers\*.pdf" --vault "<库路径>"` |
| 从 Zotero 批量导入 | 设置 `ZOTERO_STORAGE` 环境变量指向 Zotero storage，再 `python tools/ingest.py --from-storage --limit 20 --vault "<库路径>"` |
| 看统计 | 面板「总览」页 |
| 搜索条目 | 面板「论文」页；点开可看 `index.md` 原文、在 Obsidian 打开 |
| 补摘要 | 论文页里对「待生成」条目点「生成摘要与标签」 |
| 批量补摘要 | 顶栏「批量补摘要（N）」：把待生成条目排队跑完，底部显示进度、可「停止」；中断后再点会跳过已完成的继续（断点续跑） |
| 看概念 | 面板「概念」页；概念页是跨论文综合，由你或 LLM 维护 |
| 看关系图 | 在 Obsidian 里用原生 Graph / Local Graph；论文页导航块提供概念/分类边 |
| 重建分类页/导航 | 面板「重建导航」（幂等，可反复跑） |
| 手机阅读 | `python tools/make_mobile_reader.py --vault "<库路径>" --out "<输出目录>"`，把产物放到同步盘 |

## 数据位置

| 内容 | 开发态（源码运行） | 安装态（npm / 市场） |
|---|---|---|
| 配置 / 密钥 | `<仓库>/config/` | `~/.dsh/paperdepot/config/` |
| MinerU 缓存 / digest / 收件箱 | `<仓库>/cache/` | `~/.dsh/paperdepot/cache/` |
| 内置流水线 | `<仓库>/tools/` | `<插件包>/pipeline/tools/` |
| Obsidian 库 | 你选择 | 你选择 |

- `PAPERDEPOT_HOME` 可改安装态根目录。
- `config/secrets.local.json` 和 `config/paperdepot.local.json` 已在 `.gitignore` 里，不会进 git。
- 缓存可删可重建；MinerU 缓存带版本号，可整体搬移。

## 配置参考

| 字段 | 默认 | 说明 |
|---|---|---|
| `vault` | `~/Documents/ObsidianVault` | Obsidian 库根目录 |
| `homeRoot` | 仓库根 / `~/.dsh/paperdepot` | 配置与缓存根 |
| `dataRoot` | `<homeRoot>/cache` | 缓存 / digest / 收件箱 |
| `toolsDir` | `<仓库>/tools` 或 `<插件包>/pipeline/tools` | Python 流水线 |
| `python` | `python` | 跑流水的解释器；macOS/Linux 可填 `python3` |
| `provider` / `model` | 宿主默认 / `opencode-go` | 摘要模型路由 |
| `autoSummarize` | `true` | 导入后是否自动生成摘要/标签 |

环境变量：

- `MINERU_API_KEY`：MinerU Token（优先于本地文件）。
- `PAPERDEPOT_HOME`：安装态数据根。
- `PAPERDEPOT_CONFIG_DIR`：配置目录覆盖（默认 `<PAPERDEPOT_HOME>/config`）。安装态由插件在启动 Python 时自动注入；
  手动跑 `pipeline/tools/` 下的脚本时才需要自己设置。
- `PAPERDEPOT_VAULT`：默认库路径。
- `PAPERDEPOT_PYTHON`：Python 解释器。
- `ZOTERO_STORAGE`：Zotero storage 目录（仅 `--from-storage` 用）。

## 常见问题

**左侧栏没有「论文库」**
1. 检查 profile 的 `cordis.patch.yml`：`name:` 必须是 `paperdepot`，不能是子路径。
2. 检查 profile 的 `node_modules/paperdepot` 是否存在（link 或 npm 安装）。
3. 刷新页面；仍不行就重启 DSH。
4. `GET /paperdepot/api/health` 能通但面板不在，基本就是第 1 条。

**MinerU 报 401 / 403 / 429**
- 401/403：Token 无效或过期，重新申请并保存。
- 429：免费额度或频率限制，等一会儿或换自己的额度。

**面板显示「MinerU 已配置」，导入却报「未配置 MinerU key」**
- 0.1.2 及更早的安装态已知问题：面板（Node）把 key 写到 `~/.dsh/paperdepot/config/`，
  Python 流水线却去插件包的 `pipeline/config/` 找，两边路径不一致。
- 升级到含本修复的版本即可；临时绕过：给 DSH 进程设置环境变量 `MINERU_API_KEY` 后重启。
- 新版本配置卡会显示「Python 流水线能读到同一个 key」；如果显示读不到，按上面两条处理。

**导入成功但没有摘要**
- 没有配置可用模型，或模型调用失败。入库不受影响；之后在论文页补摘要即可。
- 开源前的旧条目不会自动补：顶栏「批量补摘要（N）」可一次排队跑完，跑长任务时可随时停止，下次再点跳过已完成的。
- 检查 profile 里的 `provider` / `model` 是否是宿主真实存在的路由。

**图片打不开 / 路径太长**
- 论文目录名限制 ≤120 字符，图片固定 `figNN.jpg`，PDF 固定 `paper.pdf`。
- Windows 上库根目录尽量短；长路径问题优先把库放到浅目录。

**怎么卸载**
1. DSH 设置 → 插件 → 卸载；或从 profile 里移除 `paperdepot` 并删除 `cordis.patch.yml` 对应行。
2. 删除 `~/.dsh/paperdepot/`（配置 + 缓存）。
3. Obsidian 库里的 `1-Papers/` 等是你自己的数据，按需保留或移走。
4. MinerU Token 可在 mineru.net 控制台删除。

**支持 macOS / Linux 吗**
- 本版 Windows 一等支持；macOS/Linux 已修 POSIX 长路径问题并跑基础自检，但未做完整手测，标记为实验性。

## 隐私与数据

| 数据 | 去哪里 |
|---|---|
| PDF 原文 | 上传到 MinerU 云端解析（第三方服务） |
| 论文节选（digest） | 发送给你在 DSH 中配置的 LLM provider |
| 标题 / DOI / arXiv 号 | 发送给 Crossref / arXiv 查询元数据 |
| MinerU Token | 只保存在本机配置文件 / 环境变量 |
| 使用统计 | **没有遥测**；插件不上报任何数据 |

不要导入涉密、未发表或不允许上传第三方的材料。

## 兼容性

| 项 | 要求 |
|---|---|
| DSH | `>=0.2.1-rc.1 <0.3.0` |
| Node.js | `>=20`（DSH 桌面版自带） |
| Python | `>=3.10`，需要 PyMuPDF、python-docx |
| Obsidian | 桌面版（移动端只读用导出文件） |
| 系统 | Windows 10/11 一等；macOS/Linux 实验性 |

## 路线图

后续计划（不承诺时间）：批量队列与断点续跑、provider / 本地模型设置界面、全库 lint、概念层半自动、中英双语、移动端编辑。

## 贡献

- Bug / 功能请求：GitHub Issues。
- 开发与提交规范：见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 安全问题：见 [SECURITY.md](SECURITY.md)，不要公开提 issue。
- 维护者发布/分诊手册：见 [docs/maintainer/](docs/maintainer/)。
- 行为准则：见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
- 提交代码即表示同意以 MIT 许可证贡献。

## 许可证

MIT。第三方依赖与商标声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
