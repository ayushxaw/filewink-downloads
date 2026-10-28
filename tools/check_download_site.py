#!/usr/bin/env python3
"""Check the assembled download page without requiring a browser or credentials."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        for name in ("href", "src", "poster"):
            if attrs.get(name):
                self.links.append(attrs[name])
        if tag == "img":
            self.images.append(attrs)


def check(site):
    site = Path(site).resolve()
    homepage = site / "index.html"
    if not homepage.is_file():
        raise ValueError("The assembled site has no homepage.")
    pages = {}
    for path in site.rglob("*.html"):
        parser = Page()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path.resolve()] = parser
    failures = []
    count = 0
    for path, page in pages.items():
        for image in page.images:
            if "alt" not in image:
                failures.append(f"{path.name}: an image needs alt text")
        for link in page.links:
            count += 1
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                if parsed.scheme == "mailto":
                    continue
                if parsed.scheme != "https":
                    failures.append(f"{path.name}: insecure or unsupported link {link}")
                if parsed.hostname == "github.com" and parsed.path.startswith("/ayushxaw/filewink/"):
                    failures.append(f"{path.name}: private app repository link {link}")
                continue
            if parsed.path.startswith("/"):
                failures.append(f"{path.name}: root-relative link breaks the project preview: {link}")
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_relative_to(site):
                failures.append(f"{path.name}: link escapes the site: {link}")
                continue
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                failures.append(f"{path.name}: missing local target {link}")
            elif parsed.fragment and target.suffix == ".html" and unquote(parsed.fragment) not in pages[target].ids:
                failures.append(f"{path.name}: missing section {link}")
    if not (site / "apt/dists/ubuntu/InRelease").is_file():
        failures.append("The signed APT feed is missing.")
    if failures:
        raise ValueError("\n".join(failures))
    print(f"Checked {len(pages)} pages and {count} links; the signed APT feed is present.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, type=Path)
    args = parser.parse_args()
    try:
        check(args.site)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
