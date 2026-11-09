import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DEFAULT_TIMEOUT = (15, 60)  # (connect, read) seconds

# Several chain portals serve broken/incomplete certificate chains.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class RemoteFile:
    """A file published by a chain, plus what is needed to download it."""

    chain: str
    name: str
    url: str
    platform: "Platform" = field(repr=False)


def _retry() -> Retry:
    kwargs = dict(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
    try:
        return Retry(allowed_methods=None, **kwargs)
    except TypeError:  # urllib3 < 1.26
        return Retry(method_whitelist=False, **kwargs)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.verify = False
    retry = _retry()
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class Platform:
    """Base class for a price portal. Subclasses list PriceFull files for a day."""

    def __init__(self, chain: str):
        self.chain = chain
        self.session = make_session()

    def list_price_full(self, day: date) -> List[RemoteFile]:
        raise NotImplementedError

    def resolve_url(self, remote: RemoteFile) -> str:
        return remote.url

    def get(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, url: str, data: Dict, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        resp = self.session.post(url, data=data, **kwargs)
        resp.raise_for_status()
        return resp

    def make_file(self, name: str, url: str) -> RemoteFile:
        return RemoteFile(chain=self.chain, name=name.strip(), url=url, platform=self)
