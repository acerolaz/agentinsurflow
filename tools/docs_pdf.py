#!/usr/bin/env python3
"""Documentation en PDF balisé (critères 9.10, 11.9, 12.7, 13.9) : ``make docs-pdf``.

Markdown → HTML sémantique → Chrome sans interface, qui produit un PDF balisé (structure, langue,
titre, signets). Les schémas Mermaid restent en texte, suivis de leur légende écrite.
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
DOCUMENTS = (
    "agentic-cluster/README.md",  # C9
    "docs/securite-api.md",  # C9
    "docs/resultats-tests.md",  # C9, C10, C12
    "docs/observabilite-app-insights.md",  # C11
    "docs/exploitation.md",  # C11, C13
    "docs/ci-evals.md",  # C13
    "docs/secrets.md",  # C13
    ".claude/rules/testing-pyramid.md",  # C12
)
STYLE = """
body { font-family: Helvetica, Arial, sans-serif; color: #111; line-height: 1.45; font-size: 11pt; }
a { color: #0b4f9e; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 9.5pt; }
th, td { border: 1px solid #555; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #e8e8e8; }
pre { background: #f2f2f2; padding: 8px; white-space: pre-wrap; font-size: 9pt; }
code { font-family: Menlo, Consolas, monospace; }
tr { break-inside: avoid; }
h1, h2, h3 { break-after: avoid; }
"""


def titre_de(texte: str) -> str:
    trouve = re.search(r"^# +(.+)$", texte, re.M)
    return trouve[1].strip() if trouve else "Documentation AgentInsurFlow"


def page_html(texte: str) -> str:
    corps = MarkdownIt("commonmark").enable("table").render(texte)
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        f"<title>{html.escape(titre_de(texte))}</title><style>{STYLE}</style></head>"
        f"<body><main>{corps}</main></body></html>"
    )


def imprimer(source: Path, sortie: Path) -> None:
    with tempfile.TemporaryDirectory() as dossier:
        page = Path(dossier) / "page.html"
        page.write_text(page_html(source.read_text(encoding="utf-8")), encoding="utf-8")
        subprocess.run(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--generate-pdf-document-outline",
                f"--print-to-pdf={sortie.resolve()}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def main() -> int:
    dossier = Path("docs/pdf")
    dossier.mkdir(parents=True, exist_ok=True)
    for chemin in DOCUMENTS:
        source = Path(chemin)
        nom = source.parent.name if source.name == "README.md" else source.stem
        imprimer(source, dossier / f"{nom}.pdf")
        print(f"✔ docs/pdf/{nom}.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
