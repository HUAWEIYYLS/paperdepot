# 发布手册（维护者）

> 目标：任何维护者照此文档都能独立发一个版本；发布前不靠记忆。

## 0. 发布前检查

- [ ] `git status` 干净；在 `main` 上。
- [ ] `node scripts/selftest.mjs tests/fixture-vault` 通过。
- [ ] `node tests/check-package.mjs` 通过（无 `*.local.json` / 个人清单 / 缓存）。
- [ ] `node tests/check-paths.mjs` 通过（无个人路径 / 旧品牌 / 疑似 key）。
- [ ] `python -m pytest -q tests` 通过（含安装态 `pipeline/tools` 的 key 路径回归）。
- [ ] CI 在 Windows + Ubuntu 全绿；gitleaks 通过。
- [ ] 已轮换/确认 MinerU key：仓库历史、环境变量、日志里无真实 key。
- [ ] `README.md` 的安装步骤、截图、版本号与当前行为一致。
- [ ] 干净 Windows VM 能按 README 5 分钟跑通（至少每个 minor 做一次）。

## 1. 版本号与 CHANGELOG

```powershell
npm version patch   # 或 minor / major；不要在这里自动打 tag 前先确认
```

- 更新 `CHANGELOG.md`：把 `[Unreleased]` 改成 `[x.y.z] - YYYY-MM-DD`。
- 用户可见变更写清楚；配置/API 变更写「升级必读」。
- 提交：`chore: release vX.Y.Z`。

## 2. 打 tag 并推送

```powershell
git push origin main
git tag -a vX.Y.Z -m "PaperDepot vX.Y.Z"
git push origin vX.Y.Z
```

`release.yml` 会：

1. 校验 tag 与 `package.json` 版本一致。
2. 跑 selftest / package check / paths check。
3. `npm pack` 并把 `paperdepot-X.Y.Z.tgz` 作为 GitHub Release 附件（用 GitHub 自动生成的 release notes）。
4. `npm publish --access public --provenance`（使用仓库 secret `NPM_TOKEN`；未配置则跳过）。
   npm 步骤在 Release 之后：发布失败不会挡住 GitHub Release。

**发布后更新市场索引**（`market/index.json` 是「发现」页可添加的自定义索引源）：

```powershell
node scripts/build-market-index.mjs --npm
git add market/index.json
git commit -m "chore: 更新市场索引 vX.Y.Z"
git push origin main
```

`--npm` 让索引用 npm 源（装 registry 上的预打包 tarball，不触发构建脚本）；不带参数则用 Git 源
（固定到当前提交，但安装会要求批准 `prepare` 脚本）。索引里的 `version` 取 `package.json`、
`publishTimestamp` 取当前提交时间；脚本会按 DSH format 1 的规则自检。

> `NPM_TOKEN` 需要 **Granular Access Token**（Read and write / Publish，勾选 **Bypass 2FA**）；
> 账号开了 2FA 时普通 token 发布会被 403 拒绝。首次发布还要先在本机 `npm login`
> 或用 token 手工 `npm publish` 一次，把包名占住。

> 首次发布需在 npm 上创建包并配置 `NPM_TOKEN`（Automation token，勾选 publish 权限）。
> 若没有 npm 账号，可先只发 GitHub Release tarball：`release.yml` 在 `NPM_TOKEN` 为空时会
> 跳过 npm 发布步骤，其余步骤照常执行；npm/市场后续补。

## 3. 手工发布（CI 不可用时）

```powershell
npm publish --access public
npm pack
```

把生成的 `paperdepot-X.Y.Z.tgz` 上传到 GitHub Release，并在 Release 说明里写：

- 本版功能 / 修复。
- 安装方式（tarball / npm）。
- 已知限制 / 升级注意。
- 隐私提示（PDF 会传 MinerU）。

## 4. 发布后验证

- [ ] npm 页面显示正确版本、README、License。
- [ ] `pnpm add paperdepot` 在干净 profile 能安装并出现「论文库」面板。
- [ ] GitHub Release 附件可下载，tarball 安装可用。
- [ ] `https://github.com/HUAWEIYYLS/paperdepot/issues/new/choose` 模板正常。
- [ ] 市场条目（如已收录）版本/截图/描述正确。

## 5. 插件市场上架 / 更新

市场列表来自 `awesome-dsh-plugin`：在它的仓库里按条目格式提 PR（名称、仓库、npm 包、
一句话简介、标签、截图）。收录通常一天内生效；不要往市场应用仓库提条目。

## 6. 回滚

- npm：`npm deprecate paperdepot@X.Y.Z "reason"`；必要时 `npm unpublish`（谨慎，遵守 npm 规则）。
- GitHub：编辑/删除 Release 与 tag；发布一个修复版。
- 配置/数据：保留旧版本包；用户可回退 `pnpm add paperdepot@old`。

## 7. 密钥轮换

1. mineru.net 控制台删除旧 Token、创建新 Token。
2. 更新本机 `secrets.local.json` 或环境变量 `MINERU_API_KEY`。
3. 检查仓库历史 / CI 日志 / issue 中无旧 key。
4. 若 key 曾出现在公开处，立即轮换并在 release notes 说明（不要贴出 key）。

## 8. 兼容性

- `engines.dsh` 只写实际测试过的范围；DSH 升级后先跑 selftest + 手工面板。
- 每次发布更新 `docs/maintainer/compatibility.md` 的测试矩阵（P1 文档）。
- 0.x 阶段允许 minor 破坏性变更，但必须在 CHANGELOG 写迁移步骤。
