# PaperDepot (论文库)

Turn PDF papers into a searchable, readable, connected Obsidian paper library.

PaperDepot is a [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (DSH) plugin.
It handles ingestion and organization; Obsidian only stores and reads.

> It is **not** an Obsidian community plugin. It installs into DSH and writes to the
> Obsidian vault you choose.

## What it does

- Import PDFs by drag-and-drop, file picker, or local path (deduplicated by fingerprint).
- Parse with MinerU, resolve metadata via Crossref / arXiv.
- Generate a structured Chinese summary and four controlled tag categories with an LLM.
- Write Obsidian-native frontmatter, `index.md`, `full.md`, `paper.pdf`, and `images/`.
- Browse overview / papers / concepts in the DSH sidebar panel.
- Generate taxonomy pages and paper navigation blocks; export a read-only mobile edition.

## Requirements

- DSH `>=0.2.1-rc.1 <0.3.0`
- Node.js 20+ (bundled with DSH Desktop)
- Python 3.10+ with `pymupdf` and `python-docx`
- Obsidian Desktop
- A MinerU API token (free tier available)

## Quick start

1. Install DSH Desktop and create/open an Obsidian vault (keep the path short).
2. Install the plugin (GitHub Release tarball, npm, or DSH plugin market when listed).
3. Get a MinerU token at <https://mineru.net>.
4. Open the **论文库** panel in DSH, paste the token, verify it, and choose your vault.
5. Drop a PDF into the panel and open the generated entry in Obsidian.

Full instructions (in Chinese): [README.md](README.md).

## Privacy

PDFs are uploaded to MinerU for parsing; digest excerpts are sent to the LLM provider
you configure. There is no telemetry. Do not import confidential material.

## License

MIT. Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
