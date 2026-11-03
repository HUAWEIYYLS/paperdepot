# Issue / PR 分诊手册

## 标签

| 标签 | 用途 |
|---|---|
| `bug` | 可复现的功能错误 |
| `needs-repro` | 缺复现步骤/日志，等待补充 |
| `enhancement` | 功能或体验改进 |
| `question` | 使用/配置问题（优先转 Discussions） |
| `docs` | 文档缺失或错误 |
| `good first issue` | 适合新贡献者 |
| `security` | 安全问题（不要公开细节，转私密 advisory） |
| `wontfix` | 明确不做，说明原因 |

## Issue 生命周期

1. 新 issue：确认模板字段；缺版本/OS/复现步骤的加 `needs-repro` 并请求补充。
2. 可复现：加 `bug`，尽量在 fixture / 干净 profile 复现；记录 DSH 版本。
3. 修复：关联 PR；PR 合并后关闭 issue，并在 CHANGELOG 记录用户可见变化。
4. 功能请求：判断是否在路线图；不做的说明原因并加 `wontfix`。
5. 60 天无回应且无法复现的，可关闭并说明「可随时重开」。

## 响应期望

- 尽力在 7 天内首次响应；安全/数据丢失问题优先。
- 这是社区项目，不承诺 SLA；但不要长期无回应。

## PR 审查

- 必须过 CI（Windows + Ubuntu、selftest、包检查、路径扫描、gitleaks）。
- 行为变更要有测试或 fixture 更新；用户可见变更要更新 README/CHANGELOG。
- 不合并包含密钥、个人路径、真实论文数据的 PR。
- UI 变更要求截图；跨平台相关变更说明测试环境。

## 安全

- 公开 issue 里出现漏洞细节：立即隐藏/删除敏感内容，引导到私密 advisory。
- 高危问题 7 天内出补丁；发布后在 Release notes 说明影响范围（不泄露利用细节）。
