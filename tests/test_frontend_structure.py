"""Arquivos publicos e contratos de caminhos sem navegador ou banco."""

from pathlib import Path
import unittest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


class FrontendStructureTests(unittest.TestCase):
    def test_every_page_loads_transport_before_ui(self):
        for page in (ROOT / "frontend").glob("*.html"):
            soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
            scripts = [
                s.get("src", "").split("?")[0] for s in soup.select("script[src]")
            ]
            self.assertLess(
                scripts.index("assets/js/api.js"),
                scripts.index("assets/js/ui.js"),
                page.name,
            )
            for path in scripts:
                if not path.startswith("http") and path != "runtime-config.js":
                    self.assertTrue((ROOT / "frontend" / path).is_file(), path)

    def test_legacy_asset_paths_map_to_frontend_only(self):
        from serve_frontend import FrontendHandler, FRONTEND

        handler = object.__new__(FrontendHandler)
        for url in (
            "/",
            "/buscar.html",
            "/ui.js",
            "/assets/js/api.js",
            "/imgfeature/product-placeholder.svg",
        ):
            path = Path(handler.translate_path(url))
            self.assertTrue(path.is_relative_to(FRONTEND))
            self.assertTrue(path.is_file())
