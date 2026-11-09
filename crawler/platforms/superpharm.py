"""Super-Pharm portal (prices.super-pharm.co.il) - paginated MVC grid."""
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://prices.super-pharm.co.il"
MAX_PAGES = 500
_LINK = re.compile(r'href="(/Download/(PriceFull[^"?/]+)[^"]*)"')
_TOTAL = re.compile(r'data-total-rows="(\d+)"')
_PAGE_SIZE = re.compile(r'mvc-grid-pager-rows" type="hidden" value="(\d+)"')


class SuperPharm(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        found = {}
        last_page = MAX_PAGES
        for page in range(1, MAX_PAGES + 1):
            if page > last_page:
                break
            html = self.get(
                BASE_URL + "/",
                params={
                    "Category-equals": "PriceFull",
                    "Date-equals": day.strftime("%d/%m/%Y"),
                    "page": page,
                },
            ).text
            links = _LINK.findall(html)
            if not links:
                break
            for href, name in links:
                found.setdefault(name, BASE_URL + href.replace("&amp;", "&"))
            total, size = _TOTAL.search(html), _PAGE_SIZE.search(html)
            if total and size:
                last_page = -(-int(total.group(1)) // int(size.group(1)))
        return [self.make_file(name, url) for name, url in found.items()]
