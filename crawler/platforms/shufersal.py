"""Shufersal portal (prices.shufersal.co.il) - paginated HTML table, catID=2 is PriceFull.

The site is very slow (a single page can take ~2 minutes), so after the first page
reveals how many pages exist, the rest are fetched in parallel.
"""
import html as html_lib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://prices.shufersal.co.il/FileObject/UpdateCategory"
PRICE_FULL_CATEGORY = "2"
PAGE_TIMEOUT = (15, 400)  # (connect, read) seconds
PAGE_WORKERS = 8
_LINK = re.compile(r'href="(https?://[^"]+/(PriceFull[^"/?]+)[^"]*)"')
_PAGE = re.compile(r"[?&;]page=(\d+)")


class Shufersal(Platform):
    def _page(self, page: int) -> str:
        return self.get(
            BASE_URL,
            params={"catID": PRICE_FULL_CATEGORY, "storeId": "0", "page": page},
            timeout=PAGE_TIMEOUT,
        ).text

    def list_price_full(self, day: date) -> List[RemoteFile]:
        first = self._page(1)
        last_page = max([int(n) for n in _PAGE.findall(first)] + [1])
        pages = [first]
        if last_page > 1:
            with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
                pages.extend(pool.map(self._page, range(2, last_page + 1)))

        found = {}
        for html in pages:
            for url, name in _LINK.findall(html):
                found.setdefault(name, html_lib.unescape(url))
        return [self.make_file(name, url) for name, url in found.items()]
