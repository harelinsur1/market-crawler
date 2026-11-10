"""KT - Mishnat Yosef feed (list-files.w5871031-kt.workers.dev) - one JSON list of all files."""
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://list-files.w5871031-kt.workers.dev/"


class KT(Platform):
    def list_price_full(self, day: date) -> List[RemoteFile]:
        # The feed ignores dates and returns every published file with a direct url.
        return [
            self.make_file(item["name"], item["url"])
            for item in self.get(BASE_URL).json()
            if item.get("type") == "PriceFull" and item.get("name") and item.get("url")
        ]
