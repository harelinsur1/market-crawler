"""Netiv HaChesed portal (app.netiv-hesed.com) - HTML table per day."""
import html
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://app.netiv-hesed.com"
_LINK = re.compile(r'href="(/Prices/Download\?fileName=(PriceFull[^"&]+))"')


class NetivHesed(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        page = self.get(BASE_URL + "/", params={"Date": day.strftime("%Y-%m-%d")}).text
        found = {}
        for href, name in _LINK.findall(page):
            found.setdefault(name, BASE_URL + html.unescape(href))
        return [self.make_file(name, url) for name, url in found.items()]
