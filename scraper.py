"""
Website mirror script for https://base44.com/
Downloads HTML pages, CSS, JS, images, fonts, and documents.
"""

import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from html.parser import HTMLParser

BASE_URL = "https://base44.com"
OUTPUT_DIR = Path(__file__).parent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
DELAY = 0.5  # seconds between requests

visited_urls = set()
assets_downloaded = set()
failed_urls = set()


class LinkParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []       # href links (pages)
        self.assets = []      # src/href assets

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "href" in attrs:
            url = attrs["href"]
            if url and not url.startswith(("#", "mailto:", "tel:", "javascript:")):
                full = urllib.parse.urljoin(self.base_url, url)
                if full.startswith(BASE_URL):
                    self.links.append(full.split("#")[0])

        for attr in ("src", "data-src"):
            if attr in attrs and attrs[attr]:
                full = urllib.parse.urljoin(self.base_url, attrs[attr])
                self.assets.append(full)

        if tag == "link" and attrs.get("rel") in ("stylesheet", ["stylesheet"]):
            href = attrs.get("href")
            if href:
                self.assets.append(urllib.parse.urljoin(self.base_url, href))

        if tag == "script" and "src" in attrs and attrs["src"]:
            self.assets.append(urllib.parse.urljoin(self.base_url, attrs["src"]))

        # Images with srcset
        if "srcset" in attrs:
            for part in attrs["srcset"].split(","):
                src = part.strip().split()[0]
                if src:
                    self.assets.append(urllib.parse.urljoin(self.base_url, src))


def safe_filename(url):
    """Convert a URL to a safe local file path."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lstrip("/") or "index.html"

    # Add index.html for directory paths
    if path.endswith("/") or "." not in Path(path).name:
        path = path.rstrip("/") + "/index.html"

    # Include query string in filename if present
    if parsed.query:
        ext = Path(path).suffix
        stem = path[: -len(ext)] if ext else path
        safe_q = re.sub(r"[^a-zA-Z0-9_\-]", "_", parsed.query)[:50]
        path = f"{stem}_{safe_q}{ext}"

    return OUTPUT_DIR / path


def fetch(url, binary=False):
    """Fetch a URL and return content, or None on failure."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception as e:
        print(f"  FAIL {url}: {e}")
        failed_urls.add(url)
        return None


def save(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def extract_css_urls(css_text: str, css_url: str) -> list:
    """Find url(...) references inside a CSS file."""
    pattern = re.compile(r'url\(["\']?([^)"\']+)["\']?\)')
    urls = []
    for match in pattern.finditer(css_text):
        ref = match.group(1)
        if ref.startswith("data:"):
            continue
        full = urllib.parse.urljoin(css_url, ref)
        urls.append(full)
    return urls


def download_asset(url):
    """Download a single asset (CSS/JS/image/font/doc)."""
    if url in assets_downloaded or not url.startswith("http"):
        return
    assets_downloaded.add(url)

    dest = safe_filename(url)
    if dest.exists():
        return

    print(f"  Asset: {url}")
    content = fetch(url, binary=True)
    if content is None:
        return
    save(dest, content)

    # If CSS, pull in its own url() references
    if url.endswith(".css") or "text/css" in url:
        try:
            css_text = content.decode("utf-8", errors="ignore")
            for sub_url in extract_css_urls(css_text, url):
                time.sleep(DELAY / 2)
                download_asset(sub_url)
        except Exception:
            pass


def crawl_page(url):
    """Download one HTML page and return all linked pages and assets."""
    if url in visited_urls:
        return [], []
    visited_urls.add(url)

    dest = safe_filename(url)
    print(f"\nPage: {url}")

    content = fetch(url)
    if content is None:
        return [], []

    save(dest, content)

    html = content.decode("utf-8", errors="ignore")
    parser = LinkParser(url)
    parser.feed(html)

    # Also find assets referenced inline in JS strings (common in SPAs)
    inline_assets = re.findall(
        r'["\']((?:https?://base44\.com)?/[^"\'?#\s]+\.(?:png|jpg|jpeg|gif|svg|webp|ico|woff2?|ttf|otf|eot|pdf|docx?|xlsx?|pptx?|zip))["\']',
        html,
    )
    for ref in inline_assets:
        parser.assets.append(urllib.parse.urljoin(url, ref))

    return list(set(parser.links)), list(set(parser.assets))


def run():
    print(f"Mirroring {BASE_URL} -> {OUTPUT_DIR}\n{'='*60}")

    queue = [BASE_URL + "/"]
    all_assets = []

    # BFS page crawl
    while queue:
        url = queue.pop(0)
        links, assets = crawl_page(url)
        all_assets.extend(assets)
        for link in links:
            if link not in visited_urls:
                queue.append(link)
        time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"Pages downloaded: {len(visited_urls)}")
    print(f"Assets to download: {len(set(all_assets))}")
    print(f"{'='*60}\n")

    # Download all assets
    for asset_url in set(all_assets):
        download_asset(asset_url)
        time.sleep(DELAY / 2)

    print(f"\n{'='*60}")
    print(f"Done! Pages: {len(visited_urls)}, Assets: {len(assets_downloaded)}")
    if failed_urls:
        print(f"Failed ({len(failed_urls)}):")
        for u in sorted(failed_urls):
            print(f"  {u}")
    print(f"Saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
