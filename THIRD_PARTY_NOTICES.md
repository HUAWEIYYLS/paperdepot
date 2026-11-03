# Third-Party Notices

PaperDepot itself is released under the MIT License (see `LICENSE`).

## Runtime dependencies (installed separately by the user)

| Dependency | License | How it is used |
|---|---|---|
| [PyMuPDF](https://pymupdf.readthedocs.io/) (`pymupdf`) | **AGPL-3.0** | First-page DOI extraction (`tools/doi_from_pdf.py`) and optional mobile PDF export (`tools/make_mobile_reader.py`). **Not bundled** with PaperDepot; installed from PyPI by the user. |
| [python-docx](https://python-docx.readthedocs.io/) | MIT | Optional mobile DOCX export (`tools/make_mobile_reader.py`). Not bundled. |

**Note on PyMuPDF/AGPL:** PaperDepot only calls PyMuPDF as a separately installed
dependency. If you redistribute a bundle that includes PyMuPDF itself, you must
comply with the AGPL-3.0 terms for that distribution. The safest option for
redistributors is to ship PaperDepot without PyMuPDF and let the user install it.

## External services

PaperDepot calls these services at the user's request; their terms and privacy
policies apply:

- [MinerU](https://mineru.net) — PDF parsing (the PDF is uploaded to MinerU).
- [Crossref](https://www.crossref.org/) — DOI metadata.
- [arXiv](https://arxiv.org/) — preprint metadata.

## Trademarks

- **Obsidian** is a trademark of Dynalist Inc. PaperDepot is not affiliated with
  or endorsed by Obsidian.
- **DeepSeek Harness** is a product of DeepSeek. PaperDepot is a community plugin
  and is not an official DeepSeek product.
