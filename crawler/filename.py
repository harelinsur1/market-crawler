"""Parsing of price-transparency file names.

Example: PriceFull7290055700007-001-416-20261109-120011.gz
    PriceFull      -> file type
    7290055700007  -> chain (company) id
    001            -> sub chain
    416            -> store (branch) id
    20261109       -> date  (yyyymmdd)
    120011         -> time  (hhmmss, some chains publish hhmm)
"""
import re
from datetime import datetime
from typing import NamedTuple, Optional

_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z]+?)(?P<chain>\d{13})-(?P<sub>\d+)-(?P<store>\d+)-"
    r"(?P<date>\d{8})-?(?P<time>\d{4}(?:\d{2})?)",
)


class FileInfo(NamedTuple):
    file_type: str
    chain_id: str
    sub_chain: str
    store_id: str
    timestamp: datetime

    @property
    def store_key(self):
        return self.chain_id, self.sub_chain, self.store_id


def parse_filename(name: str) -> Optional[FileInfo]:
    match = _PATTERN.match(name.strip().rsplit("/", 1)[-1])
    if not match:
        return None
    time_part = match.group("time").ljust(6, "0")
    try:
        ts = datetime.strptime(match.group("date") + time_part, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return FileInfo(
        file_type=match.group("type"),
        chain_id=match.group("chain"),
        sub_chain=match.group("sub"),
        store_id=match.group("store"),
        timestamp=ts,
    )


def is_price_full(name: str) -> bool:
    info = parse_filename(name)
    return info is not None and info.file_type.lower() == "pricefull"
