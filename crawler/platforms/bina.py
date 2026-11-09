"""Bina Projects portals (<chain>.binaprojects.com)."""
from datetime import date
from typing import List

from .base import Platform, RemoteFile

PRICE_FULL_TYPE = "4"


class Bina(Platform):
    def __init__(self, chain: str, subdomain: str):
        super().__init__(chain)
        self.base_url = "https://%s.binaprojects.com/" % subdomain

    def list_price_full(self, day: date) -> List[RemoteFile]:
        resp = self.post(
            self.base_url + "MainIO_Hok.aspx",
            data={"WStore": "", "WDate": day.strftime("%Y-%m-%d"), "WFileType": PRICE_FULL_TYPE},
        )
        return [
            self.make_file(item["FileNm"], self.base_url + "Download.aspx")
            for item in resp.json()
            if item.get("FileNm", "").startswith("PriceFull")
        ]

    def resolve_url(self, remote: RemoteFile) -> str:
        # Download.aspx returns JSON: [{"SPath": "<real file url>"}]
        resp = self.get(remote.url, params={"FileNm": remote.name})
        return resp.json()[0]["SPath"]
