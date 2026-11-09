"""Hazi Hinam portal (shop.hazi-hinam.co.il/Prices) - paginated HTML table."""
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://shop.hazi-hinam.co.il/Prices"
PRICES_TYPE = "1"  # "מחירים" - both Price and PriceFull
MAX_PAGES = 200
_LINK = re.compile(r'href="(https?://[^"]+/(PriceFull[^"/]+))"')


class HaziHinam(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        found = {}
        for page in range(1, MAX_PAGES + 1):
            html = self.get(
                BASE_URL,
                params={"p": page, "s": "", "f": "", "t": PRICES_TYPE, "d": day.strftime("%Y-%m-%d")},
            ).text
            for url, name in _LINK.findall(html):
                found.setdefault(name, url)
            if 'href="?p=%d&' % (page + 1) not in html:
                break
        return [self.make_file(name, url) for name, url in found.items()]
