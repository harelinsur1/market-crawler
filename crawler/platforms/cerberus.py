"""Cerberus web client (url.retail.publishedprices.co.il) - username login."""
import re
from datetime import date
from typing import List

from .base import Platform, RemoteFile

BASE_URL = "https://url.retail.publishedprices.co.il"
_CSRF = re.compile(r'name="csrftoken" content="([^"]+)"')


class Cerberus(Platform):
    def __init__(self, chain: str, username: str, password: str = ""):
        super().__init__(chain)
        self.username = username
        self.password = password

    def _csrf(self, html: str) -> str:
        match = _CSRF.search(html)
        if not match:
            raise RuntimeError("csrf token not found")
        return match.group(1)

    def _login(self) -> str:
        token = self._csrf(self.get(BASE_URL + "/login").text)
        resp = self.post(
            BASE_URL + "/login/user",
            data={
                "username": self.username,
                "password": self.password,
                "csrftoken": token,
                "Submit": "Sign in",
            },
        )
        if not resp.url.rstrip("/").endswith("/file"):
            raise RuntimeError("login failed for user %r" % self.username)
        return self._csrf(resp.text)

    def _list_dir(self, token: str, cd: str, search: str) -> list:
        resp = self.post(
            BASE_URL + "/file/json/dir",
            data={
                "sEcho": "1",
                "iDisplayStart": "0",
                "iDisplayLength": "100000",
                "sSearch": search,
                "mDataProp_1": "fname",
                "cd": cd,
                "csrftoken": token,
            },
        )
        return resp.json().get("aaData", [])

    def list_price_full(self, day: date) -> List[RemoteFile]:
        token = self._login()
        # Some accounts (e.g. Super Yuda) keep their files in a subfolder instead of the root.
        folders = [""] + [
            row["fname"]
            for row in self._list_dir(token, "/", "")
            if row.get("type") == "folder" and row.get("fname")
        ]
        files = []
        for folder in folders:
            prefix = folder + "/" if folder else ""
            for row in self._list_dir(token, "/" + folder, "PriceFull"):
                if row.get("type") == "file" and row.get("fname"):
                    files.append(
                        self.make_file(row["fname"], BASE_URL + "/file/d/" + prefix + row["fname"])
                    )
        return files
