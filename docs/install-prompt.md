# 一键提示词：让 DSH 帮你装好论文库

不想手动敲命令时，把下面的提示词整段复制给 **DSH 的对话**，让它按步骤装好插件、配好环境，
再把你需要点的地方列出来。

> 前提：已装 DSH Desktop、Obsidian 桌面版，并有一个 Obsidian 库（路径尽量短）；
> 已到 <https://mineru.net> 注册并拿到 Token（**不要把 Token 贴给 AI**，配置卡里自己填）。

## 极简版（三行，够用时）

```text
把 DSH 插件「论文库」装到我的 profile：pnpm add paperdepot（已发布 npm）；
在 cordis.patch.yml 里加 id: paperdepot / name: paperdepot；装 Python 依赖
（插件包 pipeline/requirements.txt）；完成后提醒我重启 DSH 并检查 /paperdepot/api/health。
```

---

## 安装提示词（复制整段）

```text
请帮我在本机安装 DSH 插件「论文库（PaperDepot）」，这是开源 DSH 插件：
https://github.com/HUAWEIYYLS/paperdepot

环境事实：我用 DSH Desktop，插件要装进 DSH 的 profile 目录
（Windows 默认 %USERPROFILE%\.dsh\profiles\desktop；macOS/Linux 默认 ~/.dsh/profiles/desktop）。

按下面步骤做，每步先确认再执行，失败就停下并把原始报错发我：

1. 定位 profile 目录：确认里面存在 package.json 和 cordis.patch.yml，并告诉我绝对路径。
2. 安装插件，优先从 npm 装（已发布为 paperdepot）：
   - 在 profile 目录执行：pnpm add paperdepot
   - 如果 registry 连不上，退回 GitHub Release 的 tarball：
     从 https://github.com/HUAWEIYYLS/paperdepot/releases/latest 下载 paperdepot-*.tgz，
     再执行 pnpm add "<该 tgz 的绝对路径>"
   - 再不行的兜底：git clone 仓库到本地（不要放进 Obsidian 库），pnpm add "link:<仓库绝对路径>"
3. 在 profile 的 cordis.patch.yml 末尾追加下面两项；文件里已有 id: paperdepot 就跳过，不要重复加：

   - insert:
       - id: paperdepot
         name: paperdepot

   注意 name 必须是裸包名 paperdepot，不能写成 paperdepot/host 之类的子路径。
4. 检查 Python：要求 >= 3.10；然后安装依赖：
   python -m pip install -r <插件包>/pipeline/requirements.txt
   （tarball/npm 安装时插件包在 profile 的 node_modules\paperdepot；link 安装时换成仓库根目录的 requirements.txt）
5. 以上完成后告诉我「请重启 DSH」。我重启后，你再用当前 DSH 的 Web GUI 地址检查：
   - GET <DSH地址>/paperdepot/api/health 应返回 ok:true、pluginVersion 有值
   - GET <DSH地址>/paperdepot/api/setup/status 看 hasKey、pythonKey.ok、vaultReady 是否正常
6. 引导我做第一次配置：打开左侧栏「论文库」→ 配置卡 → 粘贴 MinerU Token →「保存并验证」→
   选择 Obsidian 库路径。然后让我拖一个 PDF 进去试导一篇。

约束：
- 不要修改我 Obsidian 库里的任何已有文件（插件只在导入时新建条目）。
- 不要让我把 MinerU Token 贴进对话，也不要把它写进仓库或日志。
- 不要擅自改我的 pip 全局环境以外的系统设置；装依赖失败就报告。
- 全程用中文汇报，命令与路径用代码块给全。
```

## 装完之后：日常使用提示词

装好以后，下面这些可以直接发给 DSH 让它干活（它会调用「论文库」面板同一套流水线）：

```text
把这几个 PDF 导入论文库：D:\papers\a.pdf、D:\papers\b.pdf（导完告诉我落在哪个目录）
```

```text
论文库里标题含 "photonic lantern" 的条目，帮我补跑摘要和标签，并检查标签是否都在受控词表里。
```

```text
把论文库的分类页和导航块重建一遍（幂等，可反复跑），然后统计现在共有多少篇、多少篇还待生成摘要。
```

```text
把论文库导出成手机只读版（EPUB），产物放到 D:\output\mobile，导出完告诉我每个文件多大。
```

> 这些操作背后是 `tools/` 里的 Python 流水线；如果面板里能点，优先用面板，出问题时再看命令行。

## 排查

| 现象 | 先看 |
|---|---|
| 左侧栏没有「论文库」 | profile 的 `cordis.patch.yml` 里 `name:` 是否是裸包名 `paperdepot`；`node_modules\paperdepot` 是否存在；然后重启 DSH |
| health 通了但面板不在 | 同上，基本就是 `name` 写错 |
| 导入报 Python 相关错误 | `python --version` 是否 >= 3.10；`pip install -r requirements.txt` 是否装到了同一个解释器 |
| 面板显示 MinerU 已配置，导入却报未配置 key | 0.1.2 及更早安装态的已知路径 bug；升级到含修复版本，或给 DSH 进程设 `MINERU_API_KEY` 后重启。`setup/status` 的 `pythonKey.ok` 可直接看 Python 侧是否读到 |
| MinerU 401/403 | Token 失效或贴错，重新保存并验证 |
