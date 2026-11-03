# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |
| < 0.1 | ❌（未发布） |

## Reporting a vulnerability

**不要公开提 issue。** 请通过 GitHub 的
[私密安全公告](https://github.com/OWNER/paperdepot/security/advisories/new)
报告，或发邮件到维护者邮箱（在 GitHub 个人资料里）。

请在报告里包含：

- 影响版本、DSH 版本、操作系统。
- 复现步骤或最小 PoC。
- 影响范围（例如：读取任意文件、泄露 key、远程执行）。
- 是否已在公开渠道披露。

我们会在 7 天内确认，并在修复后发布补丁版本。高危问题优先处理。

## 安全边界

论文库是**单用户本地插件**，请了解以下边界：

- 插件在本机启动 Python 流水线，并注册 `/paperdepot/api` HTTP 接口。
  **不要把 DSH Web 暴露到不可信网络**；接口没有额外的用户认证。
- `/paperdepot/api/import-path` 设计上可以读取本机任意 PDF 路径，用于桌面端拖拽失效时的兜底。
- MinerU Token 以明文保存在本机配置文件（或环境变量）。请保护你的用户目录权限；
  不要把 `secrets.local.json` 提交到 git。
- PDF 会发送到 MinerU 云端解析；论文节选会发送给你配置的 LLM provider。
  涉密/未发表材料不要导入。
- 插件本身没有遥测，不会主动上传使用数据。

## 依赖

- PyMuPDF 是 AGPL-3.0，由用户单独安装，不随本项目打包；详见 `THIRD_PARTY_NOTICES.md`。
- python-docx 是 MIT。
