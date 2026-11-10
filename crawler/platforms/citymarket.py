"""City Market portal (www.citymarket-shops.co.il) - paged HTML table filtered by day."""
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://www.citymarket-shops.co.il/"
PRICES_TYPE = "1"  # ddlFileType: 1 = prices
FULL = "1"  # ddlFileIsFull: 1 = full
_ROW = re.compile(r'<td>\s*(PriceFull[^<\s]+)\s*</td>.*?href="(/downloadFile/[^"]+)"', re.S)
_PAGE = re.compile(r"\?p=(\d+)")


class CityMarket(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        files = []
        page = 1
        while True:
            html = self.get(BASE_URL, params={
                "p": page, "t": PRICES_TYPE, "f": FULL, "d": day.strftime("%Y-%m-%d"),
            }).text
            # Names are shown without an extension; the downloads are .xml.gz files.
            files.extend(self.make_file(name + ".xml.gz", BASE_URL + href.lstrip("/"))
                         for name, href in _ROW.findall(html))
            if page >= max((int(p) for p in _PAGE.findall(html)), default=1):
                return files
            page += 1
