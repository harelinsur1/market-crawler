"""Shufersal portal (prices.shufersal.co.il) - paginated HTML table, catID=2 is PriceFull."""
import html as html_lib
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://prices.shufersal.co.il/FileObject/UpdateCategory"
PRICE_FULL_CATEGORY = "2"
MAX_PAGES = 200
_LINK = re.compile(r'href="(https?://[^"]+/(PriceFull[^"/?]+)[^"]*)"')


class Shufersal(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        found = {}
        for page in range(1, MAX_PAGES + 1):
            html = self.get(
                BASE_URL, params={"catID": PRICE_FULL_CATEGORY, "storeId": "0", "page": page}
            ).text
            links = _LINK.findall(html)
            if not links:
                break
            for url, name in links:
                found.setdefault(name, html_lib.unescape(url))
        return [self.make_file(name, url) for name, url in found.items()]
