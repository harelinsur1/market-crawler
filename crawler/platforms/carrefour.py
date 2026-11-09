"""Carrefour / Yeinot Bitan / Mega portal (prices.carrefour.co.il, by U-CODE)."""
import json
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://prices.carrefour.co.il/"
_PATH = re.compile(r"const path = '(\d{8})';")
_FILES = re.compile(r"const files = (\[.*?\]);", re.S)


class Carrefour(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        html = self.get(BASE_URL, params={"date": day.strftime("%Y%m%d")}).text
        path_match, files_match = _PATH.search(html), _FILES.search(html)
        if not path_match or not files_match:
            raise RuntimeError("could not find file list in page")
        path = path_match.group(1)
        return [
            self.make_file(item["name"], BASE_URL + path + "/" + item["name"])
            for item in json.loads(files_match.group(1))
            if item["name"].startswith("PriceFull")
        ]
