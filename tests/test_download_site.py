"""Catch broken preview paths and accidentally published private links."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("download_site", Path(__file__).resolve().parents[1] / "tools/check_download_site.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class DownloadSiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.site = Path(self.temporary.name)
        (self.site / "apt/dists/ubuntu").mkdir(parents=True)
        (self.site / "apt/dists/ubuntu/InRelease").write_text("signature checked by the APT tests")
        (self.site / "apt/index.html").write_text("APT")

    def homepage(self, text):
        (self.site / "index.html").write_text(text)

    def test_project_relative_links_and_fragments(self):
        self.homepage('<a href="apt/">Install</a><a href="#downloads">Downloads</a><section id="downloads"></section>')
        checker.check(self.site)

    def test_root_relative_paths_would_break_project_preview(self):
        self.homepage('<a href="/apt/">Install</a>')
        with self.assertRaisesRegex(ValueError, "root-relative"):
            checker.check(self.site)

    def test_private_windows_preview_cannot_be_public_download(self):
        self.homepage('<a href="https://github.com/ayushxaw/filewink/releases/tag/preview">Download</a>')
        with self.assertRaisesRegex(ValueError, "private app"):
            checker.check(self.site)

    def test_missing_asset_and_section_are_reported(self):
        self.homepage('<img src="missing.png" alt="Filewink"><a href="#missing">Help</a>')
        with self.assertRaisesRegex(ValueError, "missing local target"):
            checker.check(self.site)


if __name__ == "__main__":
    unittest.main()
