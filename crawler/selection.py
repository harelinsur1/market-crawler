"""Pick, per store, the latest PriceFull file published at or before the cutoff."""
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple

from .filename import FileInfo, parse_filename
from .platforms import RemoteFile


def last_cutoff(now: datetime, hour: int = 11) -> datetime:
    """The most recent occurrence of `hour`:00 that is not in the future."""
    cutoff = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if cutoff > now:
        cutoff -= timedelta(days=1)
    return cutoff


def select_latest(
    files: Iterable[RemoteFile], cutoff: datetime
) -> List[Tuple[RemoteFile, FileInfo]]:
    best = {}  # type: Dict[Tuple[str, str, str], Tuple[RemoteFile, FileInfo]]
    for remote in files:
        info = parse_filename(remote.name)
        if info is None or info.file_type.lower() != "pricefull" or info.timestamp > cutoff:
            continue
        current = best.get(info.store_key)
        if current is None or info.timestamp > current[1].timestamp:
            best[info.store_key] = (remote, info)
    return sorted(best.values(), key=lambda item: item[1].store_key)
