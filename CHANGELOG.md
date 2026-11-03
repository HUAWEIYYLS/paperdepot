# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `docs/install-prompt.md`：一键安装提示词与日常使用提示词，可整段交给 DSH 自动完成安装与配置；
  README / README.en 增加入口。

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
