"""Wolt price feed (wm-gateway.wolt.com) - static HTML index per day."""
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://wm-gateway.wolt.com/isr-prices/public/v1/"
_LINK = re.compile(r'href="([^"]*?/(PriceFull[^"/]+))"')


class Wolt(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        html = self.get(BASE_URL + day.strftime("%Y-%m-%d") + ".html").text
        return [self.make_file(name, BASE_URL + href) for href, name in _LINK.findall(html)]
