"""Скрипт генерации сопроводительной документации в формате PDF (по разделу 5 ТЗ)."""

import os
import shutil
import subprocess
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

md_path = DOCS / "documentation.md"
html_path = DOCS / "documentation.html"
pdf_path = DOCS / "documentation.pdf"
pdf_tmp = DOCS / "documentation.tmp.pdf"
pdf_alt = DOCS / "documentation_updated.pdf"

text = md_path.read_text(encoding="utf-8")
body = markdown.markdown(text, extensions=["tables", "fenced_code"])

html_template = (
    """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Сопроводительная документация проекта «СтройКонтроль»</title>
<style>
  @page {
    size: A4 portrait;
    margin: 12mm 14mm 12mm 14mm;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial,
      sans-serif;
    line-height: 1.5;
    color: #1f2328;
    margin: 30px auto;
    max-width: 960px;
    padding: 0 20px;
    font-size: 13px;
  }
  h1, h2, h3, h4 {
    border-bottom: 1px solid #d8dee4;
    padding-bottom: .2em;
    margin-top: 18px;
    margin-bottom: 8px;
    font-weight: 600;
    color: #1f2328;
  }
  h1 { font-size: 20px; }
  h2 { font-size: 16px; margin-top: 22px; border-bottom: 2px solid #0969da; }
  h3 { font-size: 14px; }
  h4 { font-size: 13px; border-bottom: none; }
  p {
    margin-top: 4px;
    margin-bottom: 6px;
  }
  ul, ol {
    margin-top: 3px;
    margin-bottom: 8px;
    padding-left: 22px;
  }
  ul ul, ol ol, ul ol, ol ul {
    margin-top: 2px;
    margin-bottom: 3px;
    padding-left: 18px;
  }
  li {
    margin-bottom: 2px;
  }
  li > p {
    margin: 1px 0;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    max-width: 100%;
    margin-top: 6px;
    margin-bottom: 12px;
    font-size: 11px;
    line-height: 1.3;
    word-break: normal;
    overflow-wrap: break-word;
  }
  table, th, td {
    border: 1px solid #d0d7de;
  }
  th, td {
    padding: 5px 8px;
    text-align: left;
    vertical-align: top;
  }
  th {
    background-color: #f6f8fa;
    font-weight: 600;
  }
  code {
    background-color: #eff1f3;
    padding: .15em .35em;
    border-radius: 3px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 88%;
    color: #1f2328;
    word-break: break-word;
  }
  pre {
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 10px 12px;
    overflow-x: auto;
    line-height: 1.4;
    margin: 8px 0 14px 0;
  }
  pre code {
    background-color: transparent;
    padding: 0;
    font-size: 85%;
    display: block;
  }
  blockquote {
    padding: 5px 12px;
    color: #59636e;
    border-left: 4px solid #0969da;
    background-color: #f6f8fa;
    margin: 0 0 14px 0;
    border-radius: 0 4px 4px 0;
  }
  blockquote p {
    margin: 3px 0;
  }
  a {
    color: #0969da;
    text-decoration: underline;
    word-break: break-all;
  }
  hr {
    border: 0;
    height: 1px;
    background: #d8dee4;
    margin: 20px 0;
  }
  @media print {
    body {
      margin: 0;
      padding: 0;
      max-width: 100%;
      font-size: 10.5px;
      line-height: 1.35;
    }
    h1, h2, h3, h4 {
      page-break-after: avoid;
    }
    table {
      page-break-inside: auto;
      font-size: 9.5px;
      line-height: 1.25;
      margin-top: 6px;
      margin-bottom: 12px;
    }
    tr {
      page-break-inside: avoid;
    }
    thead {
      display: table-header-group;
    }
    pre {
      page-break-inside: avoid;
    }
    pre code {
      font-size: 9px;
    }
  }
</style>
</head>
<body>
"""
    + body
    + """
</body>
</html>"""
)

html_path.write_text(html_template, encoding="utf-8")

if pdf_tmp.exists():
    pdf_tmp.unlink()

# Браузер для печати в PDF: по умолчанию Edge на Windows, иначе путь из PDF_BROWSER.
edge_exe = os.environ.get(
    "PDF_BROWSER", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)
cmd = [
    edge_exe,
    "--headless",
    "--no-sandbox",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={pdf_tmp.resolve()}",
    str(html_path.resolve()),
]
subprocess.run(cmd, check=True)

if not pdf_tmp.exists() or pdf_tmp.stat().st_size == 0:
    raise RuntimeError(f"Edge did not produce PDF output at {pdf_tmp}")

# Попытка обновить целевой documentation.pdf
try:
    if pdf_path.exists():
        pdf_path.unlink()
    shutil.move(str(pdf_tmp), str(pdf_path))
    print(f"Generated PDF: {pdf_path} (size: {pdf_path.stat().st_size} bytes)")
except OSError as err:
    shutil.copy2(str(pdf_tmp), str(pdf_alt))
    msg = f"[ВНИМАНИЕ] Файл {pdf_path.name} заблокирован внешним приложением: {err}"
    print(msg)
    print(f"Свежий PDF успешно сохранен как: {pdf_alt} (size: {pdf_alt.stat().st_size} bytes)")
    print(f"Чтобы обновить {pdf_path.name}, закройте просмотрщик и перезапустите скрипт.")
