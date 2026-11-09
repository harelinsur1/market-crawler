"""laibcatalog.co.il portals (<chain>/index.html) - JSON API per chain id."""
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://laibcatalog.co.il/webapi/"


class Laibcatalog(Platform):
    def __init__(self, chain: str, chain_id: str):
        super().__init__(chain)
        self.chain_id = chain_id

    def list_price_full(self, day: date) -> List[RemoteFile]:
        # The API ignores dates and returns the chain's whole current catalog.
        resp = self.get(BASE_URL + "api/getfiles", params={"edi": self.chain_id})
        return [
            self.make_file(item["fileName"], BASE_URL + self.chain_id + "/" + item["fileName"])
            for item in resp.json()
            if item.get("fileName", "").startswith("PriceFull")
        ]
